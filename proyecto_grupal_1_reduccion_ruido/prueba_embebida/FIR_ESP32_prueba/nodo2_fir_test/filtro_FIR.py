import numpy as np
from scipy import signal


def disenar_fir(fs=8192):
    """Diseña el FIR pasa bajas original: 129 taps, Hamming, corte 1350 Hz."""
    return signal.firwin(
        numtaps=129,
        cutoff=1350.0,
        window="hamming",
        fs=fs,
    )


def filtrar_fir(entrada, fs=8192):
    """Referencia Python equivalente a scipy.signal.lfilter."""
    return signal.lfilter(
        disenar_fir(fs),
        [1.0],
        np.asarray(entrada, dtype=float),
    )
