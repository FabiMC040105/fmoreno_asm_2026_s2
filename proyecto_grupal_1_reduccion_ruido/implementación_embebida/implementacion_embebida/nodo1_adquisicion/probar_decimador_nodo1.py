#!/usr/bin/env python3
"""Pruebas offline del filtro antialias y la decimacion 24576 -> 8192 Hz."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import signal

from decimador_nodo1 import (
    FS_ADC, FS_OUTPUT, RAW_BLOCK, OUTPUT_BLOCK, DECIMATION,
    GROUP_DELAY_RAW_SAMPLES, GROUP_DELAY_OUTPUT_SAMPLES,
    coefficients, Decimator3, remove_dc_per_block,
)

OUT = Path(__file__).resolve().parent / "resultados_v2"


def main():
    b = coefficients()
    f, h = signal.freqz(b, worN=131072, fs=FS_ADC)
    mag_db = 20.0 * np.log10(np.maximum(np.abs(h), 1e-14))
    passband = mag_db[f <= 1350.0]
    stopband = mag_db[(f >= FS_OUTPUT / 2.0) & (f <= FS_ADC / 2.0)]

    # Señal sintética en ADC a 24576 Hz: DC + tres tonos útiles + interferencia
    # por encima de Nyquist de la señal final (debe desaparecer antes del decimado).
    duration = 2.0
    n = int(FS_ADC * duration)
    t = np.arange(n, dtype=np.float64) / FS_ADC
    x = 2048.0 + 500.0 * np.sin(2*np.pi*256.0*t) \
        + 310.0 * np.sin(2*np.pi*512.0*t + 0.4) \
        + 180.0 * np.sin(2*np.pi*1024.0*t + 0.9) \
        + 160.0 * np.sin(2*np.pi*5000.0*t + 0.2)

    decimator = Decimator3()
    pieces = []
    for start in range(0, len(x), RAW_BLOCK):
        raw = x[start:start + RAW_BLOCK]
        if len(raw) != RAW_BLOCK:
            raise AssertionError("El registro de prueba debe cerrar en bloques completos.")
        y = decimator.process(raw)
        if len(y) != OUTPUT_BLOCK:
            raise AssertionError(f"Se esperaban 1024 salidas, se recibieron {len(y)}.")
        pieces.append(y)
    y_raw = np.concatenate(pieces)
    y = remove_dc_per_block(y_raw)

    # Estimación de amplitud de los tonos tras descartar el arranque FIR.
    discard = 100
    samples = y[discard:]
    tt = np.arange(len(y), dtype=np.float64) / FS_OUTPUT
    freq_summary = {}
    for tone in (256.0, 512.0, 1024.0):
        idx = np.arange(discard, len(y))
        phase = 2.0 * np.pi * tone * tt[idx]
        design = np.column_stack((np.sin(phase), np.cos(phase)))
        coef, *_ = np.linalg.lstsq(design, y[idx], rcond=None)
        amplitude = float(np.hypot(coef[0], coef[1]))
        freq_summary[str(int(tone))] = amplitude

    # Cuantifica el rechazo del tono de 5000 Hz antes de que aliasara a 3192 Hz.
    # Comparamos un decimador ideal sin filtro con el decimador antialias.
    raw_no_filter = x[::DECIMATION]
    raw_no_filter = remove_dc_per_block(raw_no_filter)
    idx = np.arange(discard, len(y), dtype=np.float64)
    phase = 2.0 * np.pi * (FS_OUTPUT - 5000.0) * idx / FS_OUTPUT
    fit = np.column_stack((np.sin(phase), np.cos(phase)))
    coef_filtered, *_ = np.linalg.lstsq(fit, y[discard:], rcond=None)
    coef_unfiltered, *_ = np.linalg.lstsq(fit, raw_no_filter[discard:], rcond=None)
    alias_amp_filtered = float(np.hypot(coef_filtered[0], coef_filtered[1]))
    alias_amp_unfiltered = float(np.hypot(coef_unfiltered[0], coef_unfiltered[1]))
    alias_attenuation_db = float(20*np.log10(max(alias_amp_filtered, 1e-15) / max(alias_amp_unfiltered, 1e-15)))

    # Continuidad: misma secuencia procesada en un bloque grande versus bloques.
    continuous = Decimator3()
    y_whole = continuous.process(x)
    err = float(np.max(np.abs(y_raw - y_whole)))

    report = {
        "fs_adc_configurada_hz": FS_ADC,
        "fs_salida_hz": FS_OUTPUT,
        "factor_decimacion": DECIMATION,
        "muestras_adc_por_bloque": RAW_BLOCK,
        "muestras_salida_por_bloque": OUTPUT_BLOCK,
        "duracion_bloque_ms": 1000.0*RAW_BLOCK/FS_ADC,
        "filtro": "FIR 61 taps Hamming",
        "corte_hz": 3000.0,
        "retardo_grupo_muestras_adc": GROUP_DELAY_RAW_SAMPLES,
        "retardo_grupo_muestras_salida": GROUP_DELAY_OUTPUT_SAMPLES,
        "retardo_grupo_ms": 1000.0*GROUP_DELAY_RAW_SAMPLES/FS_ADC,
        "perdida_maxima_0_1350_db": float(-np.min(passband)),
        "nivel_maximo_4096_hasta_nyquist_db": float(np.max(stopband)),
        "amplitud_tonos_salida_adc_counts": freq_summary,
        "amplitud_alias_3192_sin_antialias": alias_amp_unfiltered,
        "amplitud_alias_3192_con_antialias": alias_amp_filtered,
        "atenuacion_alias_5000_hz_db": alias_attenuation_db,
        "diferencia_max_bloques_vs_continuo": err,
        "bloques_generados": int(decimator.total_output/OUTPUT_BLOCK),
        "nota": "Simulacion Python; frecuencia real y respuesta ADC deben validarse con placa y señal conocida.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decimador_nodo1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    assert abs(decimator.total_output - 2*FS_OUTPUT) == 0
    assert err < 1e-9
    assert np.max(passband) < 0.1 and np.min(passband) > -0.2
    assert np.max(stopband) < -45.0


if __name__ == "__main__":
    main()
