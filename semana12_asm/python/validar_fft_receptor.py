"""CE1110, semana 12. Valida en PC una captura ADC del microcontrolador.

Dos modos:
    python python/validar_fft_receptor.py --simular --modo 4
    python python/validar_fft_receptor.py --puerto COM5 --modo 4

No requiere el codigo de la parte 1: utiliza el protocolo de los sketches
'01_loopback_una_placa' y '03_receptor_dos_placas'.

Dependencias: numpy, matplotlib; para puerto real, pyserial.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

EXPECTED = {
    1: [256],
    2: [1024],
    3: [256, 512, 1024],
    4: [256, 512, 1024, 1792],
    5: [1792],
}
FS = 8192
N = 1024


def construir_senal_simulada(modo: int, fs: int = FS, n: int = N) -> np.ndarray:
    """Aproximacion del DAC y ADC ideales con filtro RC y ruido reproducible.

    Solo permite comprobar el programa Python: NO es una medida experimental.
    """
    i = np.arange(n)
    z = np.zeros(n, dtype=np.float64)
    if modo == 1:
        z += 70 * np.sin(2 * np.pi * 256 * i / fs)
    elif modo == 2:
        z += 70 * np.sin(2 * np.pi * 1024 * i / fs)
    elif modo == 3 or modo == 4:
        for f, a in [(256, 40), (512, 24), (1024, 14)]:
            z += a * np.sin(2 * np.pi * f * i / fs)
        if modo == 4:
            z += 14 * np.sin(2 * np.pi * 1792 * i / fs)
    elif modo == 5:
        z += 70 * np.sin(2 * np.pi * 1792 * i / fs)
    else:
        raise ValueError("Modo no valido")
    dac = np.clip(np.rint(128 + z), 0, 255)
    # Modelo discreto de RC R=4.7k, C=10nF, sin pretender precision analogica.
    a = np.exp(-1 / (fs * 4700 * 10e-9))
    rc = np.empty_like(dac)
    prev = 128.
    for k, sample in enumerate(dac):
        prev = a * prev + (1 - a) * sample
        rc[k] = prev
    rng = np.random.default_rng(20261029 + modo)
    adc = np.clip(np.rint(rc * (4095 / 255) + rng.normal(0, 2, n)), 0, 4095)
    return adc.astype(np.uint16)


def leer_captura_serial(puerto: str, modo: int, baudios: int = 115200):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("Falta pyserial: python -m pip install pyserial") from exc
    import time

    with serial.Serial(puerto, baudrate=baudios, timeout=3, write_timeout=3) as conexion:
        # Abrir el puerto puede reiniciar la placa ESP32.
        time.sleep(1.5)
        conexion.reset_input_buffer()
        conexion.write(f"{modo}\n".encode("ascii"))
        conexion.flush()
        cabecera = None
        for _ in range(30):
            linea = conexion.readline().decode("ascii", errors="replace").strip()
            if linea.startswith("BEGIN,"):
                cabecera = linea
                break
        if cabecera is None:
            raise RuntimeError("No se recibio BEGIN. Revise puerto, cable, firmware y monitor serial cerrado.")
        partes = cabecera.split(",")
        if len(partes) != 4:
            raise RuntimeError(f"Cabecera inesperada: {cabecera}")
        total, fs, modo_enviado = map(int, partes[1:])
        if total != N or fs != FS or modo_enviado != modo:
            raise RuntimeError(f"Parametros inesperados: N={total}, fs={fs}, modo={modo_enviado}")
        datos = []
        for i in range(total):
            linea = conexion.readline().decode("ascii", errors="replace").strip()
            if not linea.isdigit():
                raise RuntimeError(f"Muestra {i} inesperada: {linea!r}")
            v = int(linea)
            if not 0 <= v <= 4095:
                raise RuntimeError(f"ADC fuera de rango: {v}")
            datos.append(v)
        fin = conexion.readline().decode("ascii", errors="replace").strip().split(",")
        if len(fin) != 3 or fin[0] != "END":
            raise RuntimeError(f"Fin de bloque inesperado: {fin}")
        return np.asarray(datos, dtype=np.uint16), int(fin[1]), int(fin[2])


def analizar(datos: np.ndarray, modo: int, fs: int = FS) -> dict:
    """Analiza un bloque real, no inventa otros componentes ni corrige fase."""
    if datos.ndim != 1 or len(datos) != N:
        raise ValueError(f"Se requieren {N} muestras")
    x = np.asarray(datos, dtype=np.float64)
    media = float(np.mean(x))
    centrada = x - media
    # Ventana periodica de Hann apropiada para analisis en bloques.
    ventana = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)
    espectro = np.fft.rfft(centrada * ventana)
    freqs = np.fft.rfftfreq(N, d=1 / fs)
    ampl = 2 * np.abs(espectro) / np.sum(ventana)  # ADC counts aprox.
    ampl[0] /= 2
    ampl[-1] /= 2
    indice_max = int(np.argmax(ampl[1:]) + 1)
    maximo = float(ampl[indice_max])
    amplitud_min = max(8.0, 0.07 * maximo)
    comprobaciones = []
    for f in EXPECTED[modo]:
        k = int(round(f * N / fs))
        lo, hi = max(1, k - 1), min(len(ampl), k + 2)
        best = int(np.argmax(ampl[lo:hi]) + lo)
        comprobaciones.append({
            "frecuencia_esperada_hz": f,
            "frecuencia_detectada_hz": float(freqs[best]),
            "amplitud_adc": float(ampl[best]),
            "detectada": bool(abs(freqs[best] - f) <= fs / N and ampl[best] >= amplitud_min),
        })
    return {
        "modo": modo, "fs_hz": fs, "N": N, "delta_f_hz": fs / N,
        "adc_media": media, "adc_min": int(np.min(datos)), "adc_max": int(np.max(datos)),
        "saturacion_adc": bool(np.any(datos <= 3) or np.any(datos >= 4092)),
        "frecuencia_pico_principal_hz": float(freqs[indice_max]),
        "amplitud_minima_deteccion_adc": amplitud_min,
        "componentes": comprobaciones,
        "todas_detectadas": bool(all(v["detectada"] for v in comprobaciones)),
    }


def guardar(datos: np.ndarray, resultado: dict, carpeta: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    carpeta.mkdir(parents=True, exist_ok=True)
    modo = resultado["modo"]
    with (carpeta / f"captura_modo{modo}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["indice", "adc_raw"])
        writer.writerows(enumerate(datos.tolist()))
    with (carpeta / f"reporte_modo{modo}.json").open("w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    fs = resultado["fs_hz"]
    N = len(datos)
    t = np.arange(N) / fs * 1000
    x = datos.astype(float) - float(np.mean(datos))
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)
    X = 2 * np.abs(np.fft.rfft(x * w)) / np.sum(w)
    hz = np.fft.rfftfreq(N, 1 / fs)
    fig, ax = plt.subplots(2, 1, figsize=(9, 7), constrained_layout=True)
    ax[0].plot(t[:min(320, N)], datos[:min(320, N)], lw=1)
    ax[0].set(xlabel="Tiempo (ms)", ylabel="ADC (cuentas)", title=f"Modo {modo}: captura temporal")
    ax[0].grid(alpha=.25)
    ax[1].plot(hz, X, lw=1)
    for componente in resultado["componentes"]:
        ax[1].axvline(componente["frecuencia_esperada_hz"], ls="--", alpha=.45)
    ax[1].set(xlabel="Frecuencia (Hz)", ylabel="Amplitud aprox. (cuentas ADC)",
              xlim=(0, 2500), title="FFT (ventana Hann)")
    ax[1].grid(alpha=.25)
    fig.savefig(carpeta / f"fft_modo{modo}.png", dpi=160)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validar emisor ESP32 con un bloque de 1024 muestras ADC")
    p.add_argument("--puerto", type=str, help="COM5, COM6... (obligatorio sin --simular)")
    p.add_argument("--modo", type=int, choices=list(EXPECTED), default=3)
    p.add_argument("--simular", action="store_true", help="Prueba de software, NO prueba fisica")
    p.add_argument("--salida", type=Path, default=Path("datos"))
    p.add_argument("--listar-puertos", action="store_true")
    args = p.parse_args(argv)
    if args.listar_puertos:
        try:
            from serial.tools import list_ports
        except ImportError:
            p.error("Instale pyserial: python -m pip install pyserial")
        for item in list_ports.comports():
            print(item.device, item.description)
        return 0
    if not args.simular and not args.puerto:
        p.error("Indique --puerto COMx o utilice --simular")
    try:
        if args.simular:
            datos, tardias, duracion_us = construir_senal_simulada(args.modo), None, None
        else:
            datos, tardias, duracion_us = leer_captura_serial(args.puerto, args.modo)
        resultado = analizar(datos, args.modo)
        resultado["origen"] = "SIMULACION (NO ES UNA MEDICION)" if args.simular else "ADC FISICO ESP32"
        resultado["muestras_tardias"] = tardias
        resultado["duracion_captura_us"] = duracion_us
        guardar(datos, resultado, args.salida)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Origen: {resultado['origen']}")
    print(f"Muestras: {N}, fs: {FS} Hz, bin FFT: {FS/N:.1f} Hz")
    print(f"ADC: min={resultado['adc_min']}, max={resultado['adc_max']}, "
          f"saturacion={resultado['saturacion_adc']}")
    for componente in resultado["componentes"]:
        print(f"  {componente['frecuencia_esperada_hz']:4.0f} Hz => "
              f"{componente['frecuencia_detectada_hz']:7.1f} Hz "
              f"amplitud={componente['amplitud_adc']:.2f} "
              f"{'OK' if componente['detectada'] else 'NO DETECTADO'}")
    if tardias is not None:
        print(f"Muestras con retraso >35 us: {tardias}/{N}; "
              f"duracion captura: {duracion_us} us")
        if tardias > 0.05 * N:
            print("ADVERTENCIA: retrasos de muestreo elevados; revisar temporizacion.")
    print(f"Guardado en: {args.salida.resolve()}")
    return 0 if resultado["todas_detectadas"] and not resultado["saturacion_adc"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
