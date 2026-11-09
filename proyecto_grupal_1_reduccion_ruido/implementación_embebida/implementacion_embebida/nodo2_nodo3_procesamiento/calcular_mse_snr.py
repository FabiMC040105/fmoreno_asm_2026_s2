
from pathlib import Path
import numpy as np

carpeta = Path("datos_prueba")

def mse(referencia, salida):
    return np.mean((referencia - salida) ** 2)

def snr(referencia, salida):
    energia = np.sum(referencia ** 2)
    error = np.sum((referencia - salida) ** 2)
    return 10 * np.log10(energia / error)

for caso in range(1, 6):
    for rep in range(1, 4):
        archivo = carpeta / f"caso_{caso}_rep_{rep}_senales.npz"

        datos = np.load(archivo)

        limpia = datos["limpia_nodo1"]
        entrada = datos["entrada_nodo1"]
        fir = datos["salida_fir"]
        fft = datos["salida_fft_v2"]

        snr_in = snr(limpia, entrada)
        snr_fir = snr(limpia, fir)
        snr_fft = snr(limpia, fft)

        print(f"\nCaso {caso} - Repeticion {rep}")
        print(f"MSE FIR: {mse(limpia, fir):.6f}")
        print(f"MSE FFT: {mse(limpia, fft):.6f}")
        print(f"SNR entrada: {snr_in:.2f} dB")
        print(f"SNR FIR: {snr_fir:.2f} dB")
        print(f"SNR FFT: {snr_fft:.2f} dB")
        print(f"Mejora FIR: {snr_fir - snr_in:+.2f} dB")
        print(f"Mejora FFT: {snr_fft - snr_in:+.2f} dB")
