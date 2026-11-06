import numpy as np
from scipy import signal


def disenar_fir(fs=8192):
    """
    Diseña un FIR pasa bajas candidato.
    La respuesta final debe verificarse antes de aceptarlo.
    """
    numero_coeficientes = 129
    frecuencia_corte = 1350.0

    b = signal.firwin(
        numtaps=numero_coeficientes,
        cutoff=frecuencia_corte,
        window="hamming",
        fs=fs
    )

    return b


def filtrar_fir(entrada, fs=8192):
    """Filtra una señal con el FIR candidato."""
    coeficientes = disenar_fir(fs)

    salida = signal.lfilter(
        coeficientes,
        [1.0],
        np.asarray(entrada, dtype=float)
    )

    return salida