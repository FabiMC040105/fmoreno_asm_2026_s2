"""CE1110 - Semana 12. Integrador no destructivo de modelo y capturas.

Se ejecuta desde la raiz de un repositorio con `semana12_asm/` y
`proyecto_grupal_1_reduccion_ruido/tarea1/` (ambas ramas integradas).

No modifica ni regenera las capturas originales del ESP32. La senal
limpia de simulacion NO es una referencia adquirida de hardware.

Ejemplos:
    python semana12_asm/python/prototipo_alto_nivel.py --solo-frecuencias
    python semana12_asm/python/prototipo_alto_nivel.py --completo
    python semana12_asm/python/prototipo_alto_nivel.py --completo --salida /ruta/resultados

Dependencias: numpy, matplotlib, scipy (este ultimo solo en --completo).
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path

import numpy as np

FS = 8192
N = 1024
TONOS = {1: (256,), 2: (1024,), 3: (256, 512, 1024),
         4: (256, 512, 1024, 1792), 5: (1792,)}
BASE_DIR = Path(__file__).resolve().parents[1]
ROOT = BASE_DIR.parent
TAREA1 = ROOT / 'proyecto_grupal_1_reduccion_ruido' / 'tarea1'


def validar_parametros() -> None:
    assert FS == 8192 and N == 1024
    assert FS / N == 8.0
    for valores in TONOS.values():
        assert max(valores) < FS / 2
        assert all(f % (FS / N) == 0 for f in valores)


def forma_emisor(modo: int) -> np.ndarray:
    """Prototipa la tabla de 32 puntos, pesos y redondeo del firmware.

    Esta es la muestra DIGITAL nominal del DAC de 8 bits; no modela la
    no linealidad del ADC, el tiempo real, ni el circuito analogico.
    """
    if modo not in TONOS:
        raise ValueError(f'Modo desconocido: {modo}')
    i = np.arange(32)
    s1 = np.sin(2 * np.pi * i / 32)
    s2 = np.sin(2 * np.pi * 2 * i / 32)
    s3 = np.sin(2 * np.pi * 4 * i / 32)
    s4 = np.sin(2 * np.pi * 7 * i / 32)
    v = {1: 70 * s1, 2: 70 * s3,
         3: 40 * s1 + 24 * s2 + 14 * s3,
         4: 40 * s1 + 24 * s2 + 14 * s3 + 14 * s4,
         5: 70 * s4}[modo]
    # lroundf del firmware: empate se aleja de cero (no redondeo par de NumPy).
    dac = np.floor(np.maximum(0, 128 + v) + 0.5).clip(0, 255).astype(np.uint8)
    return np.tile(dac, N // 32)


def espectro(x: np.ndarray, fs: int = FS) -> tuple[np.ndarray, np.ndarray]:
    """FFT real de un bloque, ventana Hann periodica y magnitud corregida."""
    a = np.asarray(x, dtype=np.float64)
    if len(a) != N or a.ndim != 1:
        raise ValueError('El bloque debe contener 1024 muestras')
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / N)
    z = np.fft.rfft((a - np.mean(a)) * w)
    magnitudes = 2 * np.abs(z) / w.sum()
    magnitudes[0] /= 2
    magnitudes[-1] /= 2
    return np.fft.rfftfreq(N, d=1 / fs), magnitudes


def amplitudes_esperadas(x: np.ndarray, frecuencias: tuple[int, ...]) -> dict[int, float]:
    f, a = espectro(x)
    return {hz: float(a[int(round(hz * N / FS))]) for hz in frecuencias}


def fig_modos(salida: Path) -> list[dict]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rows = []
    for modo, frecuencias in TONOS.items():
        dac = forma_emisor(modo)
        f, a = espectro(dac)
        valores = amplitudes_esperadas(dac, frecuencias)
        pico = int(np.argmax(a[1:]) + 1)
        for hz in frecuencias:
            k = int(round(hz * N / FS))
            if a[k] < max(2.0, a[pico] * 0.04):
                raise AssertionError(f'No aparece {hz} Hz en modo {modo}')
        rows.append({'modo': modo, 'frecuencias_hz': ';'.join(map(str, frecuencias)),
                     'pico_principal_hz': float(f[pico]), 'muestras': len(dac),
                     'adc_real': False, 'origen': 'SIMULACION DIGITAL DAC (NO MEDICION)'})
        with (salida / f'senal_modo{modo}.csv').open('w', newline='', encoding='utf-8') as fh:
            wr = csv.writer(fh)
            wr.writerow(['indice', 'dac_ideal_8bit'])
            wr.writerows(enumerate(dac.tolist()))
        fig, axs = plt.subplots(2, 1, figsize=(9.0, 6.0), layout='constrained')
        axs[0].plot(np.arange(128) / FS * 1000, dac[:128], lw=1)
        axs[0].set(title=f'Modo {modo}: señal digital nominal del DAC',
                   xlabel='Tiempo nominal (ms)', ylabel='Código DAC (0–255)')
        axs[0].grid(alpha=.3)
        axs[1].plot(f, a, lw=1.2)
        for hz in frecuencias:
            axs[1].axvline(hz, ls='--', lw=1, alpha=.7, label=f'{hz} Hz')
        axs[1].set(xlim=(0, 2500), xlabel='Frecuencia nominal (Hz)',
                   ylabel='Amplitud (códigos DAC)', title='FFT del modelo digital')
        axs[1].legend(fontsize=8)
        axs[1].grid(alpha=.3)
        fig.savefig(salida / f'modelo_modo{modo}.png', dpi=150)
        plt.close(fig)
    return rows


def guardar_csv(ruta: Path, filas: list[dict]) -> None:
    if not filas:
        return
    with ruta.open('w', newline='', encoding='utf-8-sig') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(filas[0]))
        wr.writeheader()
        wr.writerows(filas)


def revisar_capturas(salida: Path) -> list[dict]:
    """Reanaliza SOLO los CSV adquiridos; no mezcla medición con simulación."""
    origen = BASE_DIR / 'datos' / 'fisico_dos_placas'
    if not origen.exists():
        print('AVISO: carpeta fisica ausente, se omite contraste ADC.', file=sys.stderr)
        return []
    registros = []
    for modo in TONOS:
        csv_path = origen / f'captura_modo{modo}.csv'
        json_path = origen / f'reporte_modo{modo}.json'
        if not csv_path.exists() or not json_path.exists():
            raise FileNotFoundError(f'Faltan CSV/JSON físicos del modo {modo}')
        with csv_path.open(newline='', encoding='utf-8-sig') as fh:
            datos = list(csv.DictReader(fh))
        if len(datos) != N or any(int(v['indice']) != j for j, v in enumerate(datos)):
            raise AssertionError(f'Muestras/índices corruptos para modo {modo}')
        adc = np.array([int(v['adc_raw']) for v in datos], dtype=float)
        if np.any((adc < 0) | (adc > 4095)):
            raise AssertionError('Valores ADC fuera de rango')
        rep = json.loads(json_path.read_text(encoding='utf-8'))
        if rep.get('origen') != 'ADC FISICO DEL RECEPTOR':
            raise AssertionError(f'Origen no fisico: modo {modo}')
        f, a = espectro(adc)
        calc = [float(a[int(round(hz * N / FS))]) for hz in TONOS[modo]]
        reportadas = [float(v['amplitud_adc']) for v in rep['componentes']]
        if not np.allclose(calc, reportadas, rtol=0, atol=1e-3):
            raise AssertionError(f'El FFT nuevo no reproduce reporte de modo {modo}')
        if [v['frecuencia_esperada_hz'] for v in rep['componentes']] != list(TONOS[modo]):
            raise AssertionError(f'Frecuencias esperadas inconsistentes: modo {modo}')
        registros.append({'modo': modo, 'origen': rep['origen'],
                          'muestras': len(adc), 'fs_nominal_hz': FS,
                          'frecuencias_esperadas_hz': ';'.join(map(str, TONOS[modo])),
                          'amplitudes_adc': ';'.join(f'{v:.3f}' for v in calc),
                          'adc_min': int(min(adc)), 'adc_max': int(max(adc)),
                          'saturacion_registrada': bool(rep['saturacion_adc']),
                          'muestras_tardias': int(rep['muestras_tardias']),
                          'duracion_captura_us': int(rep['duracion_captura_us']),
                          'validacion_preliminar': bool(rep['validacion_preliminar'])})
    guardar_csv(salida / 'contraste_capturas_fisicas.csv', registros)
    return registros


def importar_tarea1():
    """IMPORTA los módulos originales de development; jamás los reescribe."""
    src = TAREA1 / 'src'
    necesarios = ['generacion_senales.py', 'filtros_temporales.py', 'filtrado_espectral.py']
    faltantes = [nombre for nombre in necesarios if not (src / nombre).is_file()]
    if faltantes:
        raise FileNotFoundError('Falta el código previo de Tarea 1: ' + ', '.join(faltantes)
                                + f'. Debe estar en {src}. Integre primero development '
                                  'y PruebasFisicas sin sobrescribir sus carpetas.')
    sys.path.insert(0, str(src))
    return (importlib.import_module('generacion_senales'),
            importlib.import_module('filtros_temporales'),
            importlib.import_module('filtrado_espectral'))


def potencia(z: np.ndarray) -> float:
    return float(np.mean(np.asarray(z, dtype=float) ** 2))


def metricas(s: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    err = potencia(s - y)
    snr = float(10 * np.log10(potencia(s) / err)) if err else float('inf')
    return err, snr


def simulaciones_con_filtros(salida: Path) -> list[dict]:
    """Reusa señales y filtros EXACTAMENTE de la Tarea 1 de development."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    generador, temporal, espectral = importar_tarea1()
    if generador.FS != FS or generador.N_BLOQUE != N:
        raise AssertionError('FS/N incompatibles con las pruebas físicas')
    limpia_original = generador.senal_util()
    ruidos = [(caso, generador.ajustar_snr(
        limpia_original, generador.ruido_bruto(caso), caso['snr_objetivo_db']))
        for caso in generador.CASOS]
    pico = max(float(np.max(np.abs(limpia_original + ruido))) for _, ruido in ruidos)
    gain = min(1.0, 0.95 / pico)
    limpia = limpia_original * gain
    sos = temporal.disenar_filtro(FS)['sos']
    rows = []
    for caso, r_base in ruidos:
        c = caso['id']
        mezcla = limpia + gain * r_base
        yt, _estado = temporal.filtrar_por_bloques(mezcla, sos, N)
        ye = espectral.reduccion_espectral_adaptativa(mezcla, N, 0.1)
        if not (len(yt) == len(ye) == len(limpia)):
            raise AssertionError('El filtrado pierde muestras')
        if not (np.all(np.isfinite(yt)) and np.all(np.isfinite(ye))):
            raise AssertionError('El filtro generó valores no finitos')
        e0, snr0 = metricas(limpia, mezcla)
        for nombre, signal in [('Contaminada', mezcla), ('IIR_temporal', yt),
                               ('FFT_IFFT_espectral', ye)]:
            mse, snr = metricas(limpia, signal)
            rows.append({'caso': c, 'metodo': nombre, 'fs_hz': FS,
                         'N': N, 'muestras': len(signal),
                         'SNR_entrada_db': round(snr0, 6),
                         'MSE': round(mse, 9),
                         'SNR_salida_db': round(snr, 6),
                         'mejora_SNR_db': round(snr - snr0, 6),
                         'origen': 'SIMULACION PYTHON (NO HARDWARE)'})
        # Todas las señales normalizadas usan una misma escala temporal.
        t = np.arange(400) / FS * 1000
        fig, axs = plt.subplots(2, 1, figsize=(9.1, 6.0), layout='constrained')
        for label, s in [('Limpia', limpia), ('Contaminada', mezcla),
                         ('IIR temporal', yt), ('FFT/IFFT', ye)]:
            axs[0].plot(t, s[:400], label=label, alpha=.8, lw=1)
        axs[0].set(xlabel='Tiempo (ms)', ylabel='Amplitud normalizada',
                   title=f'Caso {c}: señales y filtrado en Python')
        axs[0].grid(alpha=.25)
        axs[0].legend(fontsize=8, ncol=2)
        for label, s in [('Limpia', limpia), ('Contaminada', mezcla),
                         ('IIR temporal', yt), ('FFT/IFFT', ye)]:
            w = np.hanning(len(s))
            f = np.fft.rfftfreq(len(s), 1 / FS)
            a = 2 * np.abs(np.fft.rfft(s * w)) / np.sum(w)
            axs[1].plot(f, a, label=label, lw=1.1, alpha=.75)
        axs[1].set(xlim=(0, 2300), xlabel='Frecuencia (Hz)',
                   ylabel='Magnitud normalizada', title='FFT del registro')
        axs[1].grid(alpha=.25)
        fig.savefig(salida / f'simulacion_filtros_caso{c}.png', dpi=145)
        plt.close(fig)
    guardar_csv(salida / 'metricas_simulacion.csv', rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--solo-frecuencias', action='store_true', help='Modelo digital de cinco modos; sin Tarea 1')
    group.add_argument('--completo', action='store_true', help='Modelo + los filtros existentes de development')
    parser.add_argument('--salida', type=Path, default=BASE_DIR / 'resultados_integracion')
    parser.add_argument('--omitir-fisico', action='store_true', help='Omitir CSV de placas (sin falsificar datos)')
    args = parser.parse_args(argv)
    # Por defecto ejecuta el prototipo completo.
    completo = args.completo or not args.solo_frecuencias
    validar_parametros()
    salida = args.salida.resolve()
    salida.mkdir(parents=True, exist_ok=True)
    modos = fig_modos(salida)
    guardar_csv(salida / 'modos_prototipados.csv', modos)
    fisicos = [] if args.omitir_fisico else revisar_capturas(salida)
    simulaciones = simulaciones_con_filtros(salida) if completo else []
    (salida / 'resumen_ejecucion.json').write_text(json.dumps({
        'sistema': 'CE1110 Semana 12', 'fs_nominal_hz': FS, 'n': N,
        'delta_f_hz': FS / N, 'modos_generados': len(modos),
        'modos_con_captura_fisica': len(fisicos),
        'filas_metricas_simulacion': len(simulaciones),
        'advertencia': 'Las simulaciones y las capturas ADC son datos de distinto origen. '
                       'No se infieren MSE/SNR físicos sin referencia limpia.',
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Modos simulados: {len(modos)}; capturas físicas verificadas: {len(fisicos)}; '
          f'métricas simuladas: {len(simulaciones)}. Resultados: {salida}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
