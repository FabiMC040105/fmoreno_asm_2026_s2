"""Sección 2.2 - Generación y caracterización reproducible de tres señales.

Ejecución desde cualquier carpeta:
    python proyecto_grupal_1_reduccion_ruido/tarea1/src/generacion_senales.py

Dependencias: numpy, scipy, matplotlib. El generador no utiliza fuentes externas.
Se almacenan WAV float32 para intercambio y NPY float64 para validación numérica.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # reproducible en equipos sin entorno gráfico
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, find_peaks, sosfiltfilt, welch

ROOT = Path(__file__).resolve().parents[1]
FS = 8192
N_BLOQUE = 1024
DURACION = 2.0
L = int(FS * DURACION)
TONOS_HZ = [256.0, 512.0, 1024.0]
AMPLITUDES = [0.40, 0.25, 0.15]
FASES_RAD = [0.0, 0.4, 0.9]
BANDAS_HZ = [0, 400, 700, 900, 1150, 1450, 2100, FS / 2]
CASOS = [
    {"id": 1, "semilla": 20261021, "snr_objetivo_db": 5.0,
     "tipo_ruido": "Interferencia sinusoidal separada", "interferencia_hz": 1792.0},
    {"id": 2, "semilla": 20261022, "snr_objetivo_db": 3.0,
     "tipo_ruido": "Ruido blanco gaussiano"},
    {"id": 3, "semilla": 20261023, "snr_objetivo_db": 0.0,
     "tipo_ruido": "Ruido aleatorio limitado a 850-1300 Hz", "banda_ruido_hz": [850.0, 1300.0]},
]


def senal_util() -> np.ndarray:
    """Misma referencia limpia multitono para los tres experimentos."""
    tiempo = np.arange(L, dtype=np.float64) / FS
    s = np.zeros(L, dtype=np.float64)
    for amplitud, frecuencia, fase in zip(AMPLITUDES, TONOS_HZ, FASES_RAD):
        s += amplitud * np.sin(2 * np.pi * frecuencia * tiempo + fase)
    return s


def ruido_bruto(caso: dict) -> np.ndarray:
    """Ruido sin escalar. RNG local asegura semillas independientes."""
    rng = np.random.default_rng(caso["semilla"])
    n = np.arange(L, dtype=np.float64)
    if caso["id"] == 1:
        # La semilla define la fase; la frecuencia es fija solo en la GENERACIÓN.
        fase = rng.uniform(-np.pi, np.pi)
        ruido = np.sin(2 * np.pi * caso["interferencia_hz"] * n / FS + fase)
    elif caso["id"] == 2:
        ruido = rng.standard_normal(L)
    elif caso["id"] == 3:
        bajo, alto = caso["banda_ruido_hz"]
        sos = butter(6, [bajo, alto], btype="bandpass", fs=FS, output="sos")
        # El filtrado no causal se usa SOLO para sintetizar el ruido de prueba;
        # NO implica que los algoritmos embebidos deban utilizar sosfiltfilt.
        ruido = sosfiltfilt(sos, rng.standard_normal(L))
    else:
        raise ValueError(f"Caso desconocido: {caso['id']}")
    return ruido - np.mean(ruido)


def ajustar_snr(senal: np.ndarray, ruido: np.ndarray, objetivo_db: float) -> np.ndarray:
    """Ajusta la potencia de ruido a Ps / 10^(SNR/10), sin usar potencia de mezcla."""
    ps = float(np.mean(np.square(senal)))
    pr = float(np.mean(np.square(ruido)))
    if ps <= 0 or pr <= 0:
        raise ValueError("Señal o ruido con potencia no positiva")
    objetivo_ruido = ps / (10 ** (objetivo_db / 10))
    return ruido * np.sqrt(objetivo_ruido / pr)


def snr_db(limpia: np.ndarray, medida: np.ndarray) -> float:
    """SNR referida a s[n], NO al cuadrado de la mezcla."""
    error = medida - limpia
    return float(10.0 * np.log10(np.sum(limpia ** 2) / np.sum(error ** 2)))


def energia_por_bandas(x: np.ndarray) -> np.ndarray:
    """Distribuye energía por Parseval usando FFT real: escala 2 interiores."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) % 2 != 0:
        raise ValueError("La señal debe tener longitud par")
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), d=1.0 / FS)
    energia_bin = np.abs(X) ** 2 / len(x)
    energia_bin[1:-1] *= 2.0
    energias = []
    for i, (fmin, fmax) in enumerate(zip(BANDAS_HZ[:-1], BANDAS_HZ[1:])):
        dentro = (f >= fmin) & ((f < fmax) if i < len(BANDAS_HZ) - 2 else (f <= fmax))
        energias.append(float(np.sum(energia_bin[dentro])))
    energias = np.array(energias)
    if not np.isclose(energias.sum(), np.sum(x ** 2), rtol=1e-10, atol=1e-10):
        raise AssertionError("No se conserva la energía de Parseval")
    return 100.0 * energias / np.sum(energias)


def espectro_magnitud(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """FFT de TODA la grabación; Hann para ilustración, no reemplaza FFT por bloques."""
    w = np.hanning(len(x))
    X = np.fft.rfft(x * w)
    f = np.fft.rfftfreq(len(x), d=1 / FS)
    magnitud = 2 * np.abs(X) / w.sum()
    magnitud[0] /= 2
    magnitud[-1] /= 2
    return f, X, magnitud


def figura_resumen(caso: dict, s: np.ndarray, r: np.ndarray, x: np.ndarray, salida: Path) -> None:
    tiempo = np.arange(L) / FS
    f, _, sx = espectro_magnitud(s)
    _, X, xx = espectro_magnitud(x)
    _, _, rx = espectro_magnitud(r)
    fig, ax = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    corto = tiempo < .035
    ax[0, 0].plot(tiempo[corto] * 1000, s[corto], label="Limpia", lw=1.5)
    ax[0, 0].plot(tiempo[corto] * 1000, x[corto], label="Contaminada", lw=.9, alpha=.8)
    ax[0, 0].set(xlabel="Tiempo (ms)", ylabel="Amplitud (escala relativa)", title="Dominio temporal: primeros 35 ms")
    ax[0, 0].legend(loc="upper right", fontsize=8)
    ax[0, 0].grid(alpha=.3)

    db = lambda a: 20 * np.log10(np.maximum(a, 1e-8))
    ax[0, 1].plot(f, db(sx), label="Limpia", lw=1.2)
    ax[0, 1].plot(f, db(rx), label="Ruido", lw=.8, alpha=.7)
    ax[0, 1].plot(f, db(xx), label="Contaminada", lw=.8, alpha=.75)
    ax[0, 1].set(xlabel="Frecuencia (Hz)", ylabel="Magnitud (dB ref. amplitud 1)", title="Espectro de magnitud (ventana Hann)", xlim=(0, FS / 2), ylim=(-120, 10))
    ax[0, 1].legend(loc="upper right", fontsize=8)
    ax[0, 1].grid(alpha=.3)

    # Fase solo en las componentes espectrales destacadas, evitando fase
    # arbitraria de bins con magnitud cercana a cero.
    peaks, _ = find_peaks(xx)
    if len(peaks) > 0:
        orden = peaks[np.argsort(xx[peaks])[::-1][:30]]
        indices = np.sort(orden)
        ax[1, 0].scatter(f[indices], np.angle(X[indices]), s=13, alpha=.8, label="Picos de la mezcla")
    for fp in TONOS_HZ:
        i = int(np.argmin(np.abs(f - fp)))
        ax[1, 0].scatter(f[i], np.angle(X[i]), marker="x", s=80, lw=1.7, color="tab:red")
    ax[1, 0].set(xlabel="Frecuencia (Hz)", ylabel="Fase (rad)", title="Fase: 30 máximos espectrales y tonos útiles", xlim=(0, FS / 2), ylim=(-np.pi-.2, np.pi+.2))
    ax[1, 0].grid(alpha=.3)

    nombres_bandas = [f"{int(a)}–{int(b)}" for a, b in zip(BANDAS_HZ[:-1], BANDAS_HZ[1:])]
    indices = np.arange(len(nombres_bandas))
    for despl, datos, label in [(-.26, s, "Limpia"), (0, r, "Ruido"), (.26, x, "Contaminada")]:
        ax[1, 1].bar(indices + despl, energia_por_bandas(datos), width=.26, label=label)
    ax[1, 1].set(xlabel="Banda de frecuencia (Hz)", ylabel="Energía de cada señal (%)", title="Distribución de energía por bandas", xticks=indices)
    ax[1, 1].set_xticklabels(nombres_bandas, rotation=28, ha="right", fontsize=8)
    ax[1, 1].legend(fontsize=8)
    ax[1, 1].grid(axis="y", alpha=.3)
    fig.suptitle(f"Caso {caso['id']}: {caso['tipo_ruido']} | SNR={snr_db(s, x):.6f} dB", fontsize=13)
    fig.savefig(salida, dpi=170)
    plt.close(fig)


def figura_psd(caso: dict, s: np.ndarray, r: np.ndarray, x: np.ndarray, salida: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    for y, label in ((s, "Limpia"), (r, "Ruido"), (x, "Contaminada")):
        f, psd = welch(y, fs=FS, window="hann", nperseg=N_BLOQUE, noverlap=N_BLOQUE//2,
                       detrend="constant", scaling="density")
        ax.plot(f, 10 * np.log10(np.maximum(psd, 1e-16)), label=label, lw=1)
    ax.set(xlabel="Frecuencia (Hz)", ylabel="Densidad espectral de potencia (dB/Hz)",
           title=f"Caso {caso['id']} - Estimación de Welch (bloques de {N_BLOQUE})", xlim=(0, FS / 2))
    ax.grid(alpha=.3)
    ax.legend()
    fig.savefig(salida, dpi=170)
    plt.close(fig)


def generar(base: Path = ROOT) -> list[dict]:
    datos_base = senal_util()
    sinteticos = []
    for caso in CASOS:
        ruido = ajustar_snr(datos_base, ruido_bruto(caso), caso["snr_objetivo_db"])
        sinteticos.append((caso, ruido))

    # Mismo factor de ganancia PARA TODOS LOS CASOS; evita recorte en WAV.
    pico = max(float(np.max(np.abs(datos_base + r))) for _, r in sinteticos)
    ganancia = min(1.0, 0.95 / pico)
    limpia = ganancia * datos_base
    rutas_resultados = base / "resultados"
    figuras = rutas_resultados / "figuras"
    metadatos = base / "metadatos"
    figuras.mkdir(parents=True, exist_ok=True)
    metadatos.mkdir(parents=True, exist_ok=True)

    resumen = []
    registros = []
    for caso, r_bruto in sinteticos:
        ruido = ganancia * r_bruto
        mezcla = limpia + ruido
        medido = snr_db(limpia, mezcla)
        assert abs(medido - caso["snr_objetivo_db"]) < 1e-10, "SNR fuera de tolerancia"
        assert np.max(np.abs(mezcla)) <= .95000000001, "WAV excede rango seguro"
        carpeta = base / "pruebas" / f"caso_{caso['id']}"
        carpeta.mkdir(parents=True, exist_ok=True)
        for nombre, valores in (("limpia", limpia), ("ruido", ruido), ("contaminada", mezcla)):
            np.save(carpeta / f"{nombre}.npy", valores)
            wavfile.write(carpeta / f"{nombre}.wav", FS, valores.astype("float32"))
        figura_resumen(caso, limpia, ruido, mezcla,
                      figuras / f"caso{caso['id']}_resumen.png")
        figura_psd(caso, limpia, ruido, mezcla,
                   figuras / f"caso{caso['id']}_psd.png")
        registro = {
            "caso": caso["id"], "semilla": caso["semilla"], "fs_hz": FS,
            "n_bloque": N_BLOQUE, "n_total": L, "duracion_s": DURACION,
            "snr_objetivo_db": caso["snr_objetivo_db"], "snr_obtenida_db": medido,
            "error_snr_db": medido - caso["snr_objetivo_db"],
            "potencia_limpia": float(np.mean(limpia ** 2)),
            "potencia_ruido": float(np.mean(ruido ** 2)),
            "pico_contaminada": float(np.max(np.abs(mezcla))),
            "tipo_ruido": caso["tipo_ruido"],
            "bandas_energia_ruido_pct": dict(zip([f"{int(a)}-{int(b)}Hz" for a,b in zip(BANDAS_HZ[:-1], BANDAS_HZ[1:])], energia_por_bandas(ruido).tolist())),
        }
        registros.append(registro)
        resumen.append({**caso, **registro, "rutas": {
            "limpia": f"pruebas/caso_{caso['id']}/limpia.wav",
            "ruido": f"pruebas/caso_{caso['id']}/ruido.wav",
            "contaminada": f"pruebas/caso_{caso['id']}/contaminada.wav",
            "npy_misma_base": True,
            "figura": f"resultados/figuras/caso{caso['id']}_resumen.png",
            "psd": f"resultados/figuras/caso{caso['id']}_psd.png"}})
        print(f"Caso {caso['id']}: objetivo={caso['snr_objetivo_db']:.3f} dB, "
              f"medida={medido:.12f} dB, pico={registro['pico_contaminada']:.4f}")

    conf = {
        "descripcion": "Tarea 1 CE1110 apartado 2.2; datos sintéticos reproducibles",
        "generador": "src/generacion_senales.py", "fs_hz": FS,
        "n_bloque": N_BLOQUE, "n_total": L, "duracion_s": DURACION,
        "resolucion_bloque_hz": FS/N_BLOQUE,
        "frecuencias_utiles_hz": TONOS_HZ,
        "amplitudes_originales": AMPLITUDES, "fases_utiles_rad": FASES_RAD,
        "ganancia_global_anticlip": ganancia,
        "amplitudes_efectivas": [a*ganancia for a in AMPLITUDES],
        "bandas_energia_hz": BANDAS_HZ,
        "wav": "IEEE float 32-bit mono; NPY float64 como referencia sin cuantizar",
        "condiciones": resumen,
        "versiones": {"numpy": np.__version__, "scipy": __import__("scipy").__version__, "matplotlib": matplotlib.__version__},
        "nota": "La referencia limpia no se presupone disponible al filtro: se reserva para evaluación y SNR. Las frecuencias conocidas son verdad de terreno, no entrada automática al estimador de ruido."
    }
    (metadatos / "configuraciones.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")
    with (rutas_resultados / "metricas_generacion.csv").open("w", newline="", encoding="utf-8") as fh:
        col = ["caso", "semilla", "fs_hz", "n_bloque", "n_total", "duracion_s", "snr_objetivo_db", "snr_obtenida_db", "error_snr_db", "potencia_limpia", "potencia_ruido", "pico_contaminada", "tipo_ruido"]
        escritor = csv.DictWriter(fh, fieldnames=col)
        escritor.writeheader()
        for row in registros:
            escritor.writerow({k: row[k] for k in col})
    return registros


if __name__ == "__main__":
    generar()
