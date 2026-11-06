
from pathlib import Path
import sys
import csv
import json

import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

# Localizar la carpeta principal de tarea1
ROOT = Path(__file__).resolve().parents[1]

# Permitir importar los módulos de src
sys.path.insert(0, str(ROOT / "src"))

from filtro_FIR import disenar_fir, filtrar_fir


def potencia(x):
    return np.mean(np.asarray(x) ** 2)


def snr_db(senal, error):
    pe = potencia(error)
    if pe == 0:
        return float("inf")
    return 10 * np.log10(potencia(senal) / pe)


def main():

    # Leer frecuencia de muestreo
    config = json.loads(
        (ROOT / "metadatos" / "configuraciones.json")
        .read_text(encoding="utf-8")
    )

    fs = int(config["fs_hz"])

    # Diseñar FIR
    b = np.asarray(disenar_fir(fs), dtype=float)

    # Verificar que sea un FIR de fase lineal
    if not np.allclose(b, b[::-1], atol=1e-12):
        raise ValueError("Los coeficientes FIR no son simétricos.")

    # Retardo de grupo
    retardo = (len(b) - 1) // 2

    print("\nDISEÑO DEL FILTRO FIR")
    print("----------------------")
    print("Frecuencia de muestreo:", fs, "Hz")
    print("Número de coeficientes:", len(b))
    print("Retardo:", retardo, "muestras")
    print("Retardo temporal:", retardo / fs * 1000, "ms")

    # Crear carpeta de resultados
    carpeta = ROOT / "resultados" / "fir"
    carpeta.mkdir(parents=True, exist_ok=True)

    registros = []

    # Evaluar respuesta en frecuencia
    frecuencias, h = signal.freqz(
        b, worN=16384, fs=fs
    )

    magnitud_db = 20 * np.log10(
        np.maximum(np.abs(h), 1e-12)
    )

    plt.figure(figsize=(10, 5))
    plt.plot(frecuencias, magnitud_db)
    plt.axvline(1024, linestyle="--", label="Último tono útil", color="blue")
    plt.axvline(1350, linestyle="--", label="Frecuencia de corte", color="red")
    plt.axvline(1792, linestyle="--", label="Interferencia", color="green")
    plt.xlabel("Frecuencia (Hz)")
    plt.ylabel("Magnitud (dB)")
    plt.title("Respuesta en frecuencia del filtro FIR")
    plt.xlim(0, 2500)
    plt.ylim(-100, 5)
    plt.grid()
    plt.legend()
    plt.savefig(carpeta / "respuesta_frecuencia.png", dpi=150)
    plt.close()

    # Revisar ganancia en frecuencias importantes
    print("\nGANANCIA EN FRECUENCIAS IMPORTANTES")

    tonos = [256, 512, 1024, 1350, 1600, 1792]

    for f0 in tonos:
        _, H = signal.freqz(b, worN=np.array([f0]), fs=fs)
        ganancia = 20 * np.log10(max(abs(H[0]), 1e-12))
        print(f"{f0:6.0f} Hz : {ganancia:8.3f} dB")

    # Evaluar los tres casos
    for caso in (1, 2, 3):

        ruta = ROOT / "pruebas" / f"caso_{caso}"

        limpia = np.load(ruta / "limpia.npy")
        ruido = np.load(ruta / "ruido.npy")
        contaminada = np.load(ruta / "contaminada.npy")

        # Aplicar FIR a cada componente
        salida = filtrar_fir(contaminada, fs)
        limpia_fir = filtrar_fir(limpia, fs)
        ruido_fir = filtrar_fir(ruido, fs)

        # Eliminar bordes y compensar el retardo.
        # Guardar len(b)-1 muestras evita los transitorios de frontera.
        margen = len(b) - 1

        inicio = margen
        fin = len(limpia) - retardo - margen

        referencia = limpia[inicio:fin]

        salida_alineada = salida[
            inicio + retardo:fin + retardo
        ]

        limpia_alineada = limpia_fir[
            inicio + retardo:fin + retardo
        ]

        ruido_alineado = ruido[
            inicio:fin
        ]

        ruido_filtrado = ruido_fir[
            inicio + retardo:fin + retardo
        ]

        # Calcular métricas
        mse = potencia(referencia - salida_alineada)

        snr_entrada = 10 * np.log10(
            potencia(referencia) / potencia(ruido_alineado)
        )

        snr_salida = snr_db(
            referencia,
            referencia - salida_alineada
        )

        delta_snr = snr_salida - snr_entrada

        energia = 100 * (
            potencia(limpia_alineada) / potencia(referencia)
        )

        atenuacion = 10 * np.log10(
            potencia(ruido_alineado) /
            potencia(ruido_filtrado)
        )

        # Guardar salida
        np.save(
            carpeta / f"caso_{caso}_filtrada.npy",
            salida
        )

        registro = {
            "caso": caso,
            "MSE": mse,
            "SNR_entrada_dB": snr_entrada,
            "SNR_salida_dB": snr_salida,
            "Delta_SNR_dB": delta_snr,
            "Energia_util_pct": energia,
            "Atenuacion_ruido_dB": atenuacion
        }

        registros.append(registro)

        print(f"\nCASO {caso}")
        print("----------------------")
        print(f"MSE: {mse:.6f}")
        print(f"SNR entrada: {snr_entrada:.3f} dB")
        print(f"SNR salida: {snr_salida:.3f} dB")
        print(f"Mejora SNR: {delta_snr:+.3f} dB")
        print(f"Energia conservada: {energia:.2f} %")
        print(f"Atenuacion del ruido: {atenuacion:.3f} dB")

        # Gráfica temporal del caso
        inicio_grafica = int(0.4 * fs)
        fin_grafica = inicio_grafica + int(0.035 * fs)

        indices = np.arange(inicio_grafica, fin_grafica)
        tiempo = indices / fs * 1000

        plt.figure(figsize=(11, 5))

        plt.plot(
            tiempo,
            contaminada[indices],
            label="Contaminada",
            alpha=0.6
        )

        plt.plot(
            tiempo,
            limpia[indices],
            label="Limpia"
        )

        # Desplazar visualmente la salida para compensar el retardo
        plt.plot(
            tiempo,
            salida[indices + retardo],
            label="FIR filtrada"
        )

        plt.xlabel("Tiempo (ms)")
        plt.ylabel("Amplitud")
        plt.title(f"Comparación FIR - Caso {caso}")
        plt.grid()
        plt.legend()

        plt.savefig(
            carpeta / f"caso_{caso}_comparacion.png",
            dpi=150
        )

        plt.close()

    # Guardar tabla de métricas
    with open(
        carpeta / "metricas_fir.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as archivo:

        writer = csv.DictWriter(
            archivo,
            fieldnames=registros[0].keys()
        )

        writer.writeheader()
        writer.writerows(registros)

    print("\nResultados guardados en:", carpeta)


if __name__ == "__main__":
    main()
