"""Referencia Python del antialias + decimacion 3:1 del Nodo 1.

ADC continuo ESP32 clasico configurado nominalmente a 24576 Hz.
Salida: 8192 Hz, bloques de 1024 muestras a partir de 3072 muestras ADC.
Filtro: FIR lineal de 61 taps, Hamming, corte 3000 Hz.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

FS_ADC = 24576
FS_OUTPUT = 8192
DECIMATION = 3
RAW_BLOCK = 3072
OUTPUT_BLOCK = 1024
FIR_TAPS = 61
FIR_CUTOFF_HZ = 3000.0
GROUP_DELAY_RAW_SAMPLES = (FIR_TAPS - 1) // 2
GROUP_DELAY_OUTPUT_SAMPLES = GROUP_DELAY_RAW_SAMPLES // DECIMATION


def coefficients() -> np.ndarray:
    return signal.firwin(
        numtaps=FIR_TAPS,
        cutoff=FIR_CUTOFF_HZ,
        window="hamming",
        fs=FS_ADC,
    ).astype(np.float64)


class Decimator3:
    """Decimador con estado FIR y fase de muestreo conservados entre bloques."""

    def __init__(self):
        self.b = coefficients()
        self.zi = None
        self.phase = 0
        self.total_input = 0
        self.total_output = 0

    def reset(self):
        self.zi = None
        self.phase = 0
        self.total_input = 0
        self.total_output = 0

    def process(self, raw_block: np.ndarray) -> np.ndarray:
        x = np.asarray(raw_block, dtype=np.float64)
        if x.ndim != 1 or x.size == 0:
            raise ValueError("El bloque ADC debe ser un vector 1D no vacio.")
        if not np.all(np.isfinite(x)):
            raise ValueError("El bloque ADC contiene valores no finitos.")
        if self.zi is None:
            # Inicializa el estado con el primer nivel DC para evitar un salto
            # artificial de cero a la polarizacion del ADC al arrancar.
            self.zi = signal.lfilter_zi(self.b, [1.0]) * x[0]

        filtered, self.zi = signal.lfilter(self.b, [1.0], x, zi=self.zi)
        first = (-self.phase) % DECIMATION
        output = filtered[first::DECIMATION]
        self.phase = (self.phase + len(x)) % DECIMATION
        self.total_input += len(x)
        self.total_output += len(output)
        return output


def remove_dc_per_block(x: np.ndarray, block_size: int = OUTPUT_BLOCK) -> np.ndarray:
    values = np.asarray(x, dtype=np.float64)
    if values.ndim != 1 or len(values) % block_size:
        raise ValueError("La entrada debe contener bloques completos.")
    blocks = values.reshape(-1, block_size)
    return (blocks - np.mean(blocks, axis=1, keepdims=True)).reshape(-1)
