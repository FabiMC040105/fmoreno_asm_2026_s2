#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Consolida Resultados_ASM (carpeta o ZIP) sin inventar MSE/SNR físicas.

Uso:
    python analizar_resultados_asm.py "Resultados_ASM"
    python analizar_resultados_asm.py "Resultados_ASM.zip" \
        --validacion-software "implementacion_embebida/nodo3_espectral_v2_validacion/datos_prueba"

Para MSE/SNR de capturas físicas, cada P*_rep* debe contener uno de:
    capturas_medidas.csv con columnas limpia,entrada,fir,fft
    senales_medidas.npz con limpia,entrada,fir,fft (también se admiten alias)
Las cuatro series deben proceder de mediciones alineadas de la misma prueba.
NO utiliza estimulo.wav como referencia física, ni infiere SNR desde RMS/energía.
"""

from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import sys
import zipfile
from collections import defaultdict

MTR_FIELDS = [
    'rms_entrada', 'rms_fir', 'rms_fft',
    'energia_total_fir_pct', 'energia_total_fft_pct',
    'atenuacion_tono_fir_db', 'atenuacion_tono_fft_db',
    'captura_adc_us', 'dsp_us', 'i2s_write_us',
    'heap_libre_bytes', 'heap_min_bytes', 'fft_reservada_bytes',
]
COUNTERS = ['errores_crc', 'errores_formato', 'saltos_secuencia', 'errores_dac']
RESULT_FIELDS = [
    'prueba', 'repeticion', 'fuente', 'archivo', 'estado', 'muestras',
    'desfase_fir_muestras', 'desfase_fft_muestras',
    'mse_entrada', 'mse_fir', 'mse_fft',
    'snr_entrada_db', 'snr_fir_db', 'snr_fft_db',
    'delta_snr_fir_db', 'delta_snr_fft_db', 'advertencias',
]
ALIAS = {
    'limpia': ['limpia', 'referencia_limpia', 'limpia_nodo1', 'referencia', 'senal_limpia'],
    'entrada': ['entrada', 'entrada_nodo1', 'senal_contaminada', 'contaminada'],
    'fir': ['fir', 'salida_fir', 'filtrada_fir'],
    'fft': ['fft', 'salida_fft', 'salida_fft_v2', 'filtrada_fft'],
}


class Source:
    """Lector de archivos tanto de carpetas como de ZIP, sin extraer nada."""
    def __init__(self, path: Path):
        self.path = path
        if path.is_file() and path.suffix.lower() == '.zip':
            self.archive = zipfile.ZipFile(path)
            self.names = [n for n in self.archive.namelist() if not n.endswith('/')]
        elif path.is_dir():
            self.archive = None
            self.names = [p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file()]
        else:
            raise ValueError(f'No encuentro una carpeta o ZIP válido: {path}')

    def read(self, name: str) -> bytes:
        return self.archive.read(name) if self.archive else (self.path / name).read_bytes()

    def close(self):
        if self.archive:
            self.archive.close()


def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def mean(values):
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def std(values):
    vals = [v for v in values if v is not None]
    return statistics.stdev(vals) if len(vals) > 1 else None


def parse_label(name):
    for part in reversed(PurePosixPath(name).parts):
        m = re.fullmatch(r'(P[1-6])_rep(\d+)', part, re.I)
        if m:
            return m.group(1).upper(), int(m.group(2))
    # En datos_prueba de la simulación, el identificador está en el nombre.
    m = re.search(r'caso_(\d+)_rep_(\d+)_senales\.npz$', name, re.I)
    if m:
        return f'P{m.group(1)}', int(m.group(2))
    return '', ''


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '' if row.get(k) is None else row.get(k) for k in fields})


def summarize_telemetry(src: Source):
    trials = []
    for name in sorted(src.names):
        if PurePosixPath(name).name.lower() != 'telemetria.csv':
            continue
        p, rep = parse_label(name)
        if not p:
            continue
        try:
            txt = src.read(name).decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(txt)))
        except (OSError, UnicodeError, csv.Error) as err:
            print(f'AVISO: no se pudo leer {name}: {err}', file=sys.stderr)
            continue
        metrics = [r for r in rows if r.get('fuente', '').strip().upper() == 'MTR']
        if not metrics:
            print(f'AVISO: {name} no tiene filas de tipo MTR', file=sys.stderr)
        row = {'prueba': p, 'repeticion': rep, 'archivo': name,
               'registros_mtr': len(metrics), 'filas_totales': len(rows)}
        for field in MTR_FIELDS:
            row[field + '_media'] = mean([number(r.get(field)) for r in metrics])
        for field in COUNTERS:
            values = [number(r.get(field)) for r in metrics]
            values = [v for v in values if v is not None]
            row[field + '_max'] = max(values) if values else None
            row[field + '_ultimo'] = values[-1] if values else None
        tonos = [number(r.get('tono_hz')) for r in metrics]
        tonos = [v for v in tonos if v is not None]
        row['tono_hz'] = tonos[0] if tonos and all(v == tonos[0] for v in tonos) else None
        trials.append(row)
    return trials


def per_condition(trials):
    groups = defaultdict(list)
    for trial in trials:
        groups[trial['prueba']].append(trial)
    summary = []
    for p in sorted(groups):
        rows = groups[p]
        out = {'prueba': p, 'repeticiones': len(rows),
               'repeticiones_ids': ','.join(str(x['repeticion']) for x in rows)}
        for k in MTR_FIELDS:
            numbers = [x[k + '_media'] for x in rows]
            out[k+'_promedio'] = mean(numbers)
            out[k+'_desv_entre_reps'] = std(numbers)
        for k in COUNTERS:
            values = [x[k+'_max'] for x in rows if x[k+'_max'] is not None]
            out[k+'_max'] = max(values) if values else None
        summary.append(out)
    return summary


def get_numpy():
    try:
        import numpy as np
        return np
    except ImportError as err:
        raise RuntimeError('Para procesar capturas de muestras se necesita NumPy: python -m pip install numpy') from err


def read_series_bytes(content: bytes, suffix: str):
    np = get_numpy()
    if suffix == '.npz':
        with np.load(io.BytesIO(content), allow_pickle=False) as pack:
            arrays = {k: np.asarray(pack[k], dtype=np.float64).ravel() for k in pack.files}
    elif suffix == '.csv':
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        columns = {key: [] for key in (reader.fieldnames or [])}
        for row in reader:
            for k in columns:
                columns[k].append(row.get(k, ''))
        arrays = {k: np.array(v, dtype=np.float64) for k,v in columns.items()}
    else:
        raise ValueError('Extensión no soportada')
    selected = {}
    for canonical, possibilities in ALIAS.items():
        key = next((k for k in possibilities if k in arrays), None)
        if key is None:
            raise ValueError(f'Falta serie {canonical}: se acepta una de {possibilities}')
        selected[canonical] = arrays[key]
    return selected


def evaluate_series(arrays, lag_fir=0, lag_fft=0):
    """lag positivo: salida retrasada respecto a la referencia (índice i+lag)."""
    np = get_numpy()
    ref, inp, fir, fft = (arrays[k] for k in ('limpia', 'entrada', 'fir', 'fft'))
    if any(len(a) < 32 for a in (ref, inp, fir, fft)):
        raise ValueError('Se requieren al menos 32 muestras por serie')
    idx = np.arange(min(len(ref), len(inp)), dtype=int)
    good = ((idx + lag_fir >= 0) & (idx + lag_fir < len(fir)) &
            (idx + lag_fft >= 0) & (idx + lag_fft < len(fft)))
    idx = idx[good]
    if len(idx) < 32:
        raise ValueError('No hay suficientes muestras comunes tras compensar desfases')
    s, x, yfir, yfft = ref[idx], inp[idx], fir[idx + lag_fir], fft[idx + lag_fft]
    for arr in (s, x, yfir, yfft):
        if not np.isfinite(arr).all():
            raise ValueError('Hay muestras NaN o infinitas')
    if float(np.dot(s, s)) <= 1e-12:
        raise ValueError('La referencia limpia tiene energía nula')
    def metrics(y):
        diff = s - y
        err = float(np.dot(diff, diff))
        mse = err/len(s)
        snr = 10*math.log10(float(np.dot(s,s))/err) if err > 0 else math.inf
        return mse, snr
    mse_in, snr_in = metrics(x)
    mse_fir, snr_fir = metrics(yfir)
    mse_fft, snr_fft = metrics(yfft)
    return {
        'muestras': len(idx), 'desfase_fir_muestras': lag_fir,
        'desfase_fft_muestras': lag_fft,
        'mse_entrada': mse_in, 'mse_fir': mse_fir, 'mse_fft': mse_fft,
        'snr_entrada_db': snr_in, 'snr_fir_db': snr_fir, 'snr_fft_db': snr_fft,
        'delta_snr_fir_db': snr_fir-snr_in,
        'delta_snr_fft_db': snr_fft-snr_in,
    }


def find_measured_series(src, trial_name):
    parent = PurePosixPath(trial_name).parent
    choices = [str(parent / 'senales_medidas.npz'), str(parent / 'capturas_medidas.csv')]
    return next((x for x in choices if x in src.names), None)


def metricas_fisicas(src: Source, trials, lag_fir=0, lag_fft=0):
    rows = []
    for t in trials:
        p, rep, origin = t['prueba'], t['repeticion'], t['archivo']
        matched = find_measured_series(src, origin)
        base = {'prueba': p, 'repeticion': rep, 'fuente': 'CAPTURAS_MEDIDAS',
                'archivo': matched or '', 'estado': 'NO_CALCULABLE_SIN_MUESTRAS',
                'advertencias': 'telemetria.csv y estimulo.wav NO contienen las salidas medidas; no hay MSE/SNR fisicos'}
        if matched:
            try:
                arrs = read_series_bytes(src.read(matched), PurePosixPath(matched).suffix.lower())
                values = evaluate_series(arrs, lag_fir, lag_fft)
                base.update(values)
                base['estado'] = 'CALCULADO_DE_MUESTRAS_SUMINISTRADAS'
                base['advertencias'] = ('Verificar que sean mediciones físicas de la misma prueba, '
                                        'sincronizadas, misma escala y con latencia corregida. '
                                        'El cálculo NO verifica esto automáticamente.')
            except Exception as err:
                base['estado'] = 'ERROR_EN_MUESTRAS'
                base['advertencias'] = str(err)
        rows.append(base)
    return rows


def metricas_simuladas(src: Source, lag_fir=0, lag_fft=0):
    rows = []
    for name in sorted(src.names):
        if not re.search(r'caso_\d+_rep_\d+_senales\.npz$', name, re.I):
            continue
        p, rep = parse_label(name)
        row = {'prueba': p, 'repeticion': rep, 'fuente': 'VALIDACION_SOFTWARE',
               'archivo': name, 'estado': 'ERROR_EN_MUESTRAS',
               'advertencias': ''}
        try:
            arrs = read_series_bytes(src.read(name), '.npz')
            row.update(evaluate_series(arrs, lag_fir, lag_fft))
            row['estado'] = 'CALCULADO_SIMULACION'
            row['advertencias'] = 'NO es una medicion fisica del ADC ni de las salidas DAC.'
        except Exception as err:
            row['advertencias'] = str(err)
        rows.append(row)
    return rows


def text_fmt(v, unit='', digits=3):
    if v is None:
        return 'N/D'
    return f'{v:.{digits}f}{unit}'


def report(trials, summary, measured, sim):
    lines = [
        '# Informe automático — CE1110', '',
        '## Alcance de las métricas', '',
        '**ADVERTENCIA:** `estimulo.wav` es el estímulo digital de la PC, NO una grabación '
        'del audio capturado por el micrófono ni de las salidas físicas. Los archivos '
        '`telemetria.csv` únicamente registran telemetría. Por ello, no es posible '
        'reconstruir MSE ni SNR físicas a partir de ellos.', '',
        f'- Ejecuciones con telemetría: **{len(trials)}**',
        f'- Ejecuciones con MSE/SNR calculadas de series proporcionadas: **{sum(r["estado"]=="CALCULADO_DE_MUESTRAS_SUMINISTRADAS" for r in measured)}**',
        f'- Casos con referencia de software: **{sum(r["estado"]=="CALCULADO_SIMULACION" for r in sim)}**', '',
        '## Resumen de mediciones embebidas (promedio de repeticiones)', '',
        '| Prueba | Reps | RMS entrada | Energía total FIR (%) | Energía total FFT (%) | '
        'Atenuación tonal FIR (dB) | Atenuación tonal FFT (dB) | CRC máx. | gaps máx. |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for t in summary:
        lines.append('| ' + ' | '.join([
            t['prueba'], str(t['repeticiones']),
            text_fmt(t.get('rms_entrada_promedio'), digits=5),
            text_fmt(t.get('energia_total_fir_pct_promedio'),digits=2),
            text_fmt(t.get('energia_total_fft_pct_promedio'),digits=2),
            text_fmt(t.get('atenuacion_tono_fir_db_promedio'),digits=2),
            text_fmt(t.get('atenuacion_tono_fft_db_promedio'),digits=2),
            str(t.get('errores_crc_max') if t.get('errores_crc_max') is not None else 'N/D'),
            str(t.get('saltos_secuencia_max') if t.get('saltos_secuencia_max') is not None else 'N/D'),
        ]) + ' |')
    lines += [
        '', '**Interpretación:** energía total relativa no equivale a energía útil conservada. '
        'Las atenuaciones `NaN` del origen se tratan como no disponibles. '
        'Cada `MTR` no cuenta como repetición independiente: las estadísticas entre '
        'repeticiones utilizan el promedio de cada ejecución.', '',
        '## MSE / SNR obtenidas de formas de onda', '',
        '| Prueba | Rep | Origen | MSE FIR | MSE FFT | SNR entrada | SNR FIR | SNR FFT | ΔSNR FIR | ΔSNR FFT |',
        '|---|---:|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    found=[r for r in measured+sim if r['estado'].startswith('CALCULADO_')]
    for r in found:
        lines.append('| ' + ' | '.join([
            str(r['prueba']), str(r['repeticion']),
            'Medidas (procedencia por verificar)' if r['fuente']=='CAPTURAS_MEDIDAS' else 'Solo software',
            text_fmt(r.get('mse_fir'), digits=7), text_fmt(r.get('mse_fft'), digits=7),
            text_fmt(r.get('snr_entrada_db'),digits=2),text_fmt(r.get('snr_fir_db'),digits=2),
            text_fmt(r.get('snr_fft_db'),digits=2),text_fmt(r.get('delta_snr_fir_db'),digits=2),
            text_fmt(r.get('delta_snr_fft_db'),digits=2),
        ]) + ' |')
    if not found:
        lines.append('| — | — | No se dispone de series limpias y salidas | — | — | — | — | — | — | — |')
    lines += ['',
        '## Para obtener MSE y SNR de las ESP32', '',
        'En cada subcarpeta `P*_rep*` guardar `capturas_medidas.csv` '
        '(columnas `limpia,entrada,fir,fft`) o `senales_medidas.npz` con las mismas cuatro series. '
        'Debe tratarse de una **referencia limpia realmente correspondiente a esa adquisición** '
        'y dos salidas medidas, sincronizadas y expresadas en la misma escala.', '',
        'El cálculo supone muestras a una cadencia común y ya alineadas; si se midió un retardo, '
        'puede indicarse con `--desfase-fir` y `--desfase-fft` (muestras). '
        'El retardo debe determinarse experimentalmente, no elegirse para maximizar artificialmente la SNR.', '',
        'Las fórmulas son MSE=mean((s-y)^2), SNR=10log10(sum(s²)/sum((s-y)²)) '
        'y ΔSNR=SNR_sal-SNR_ent. La computadora aquí puede consolidar datos de laboratorio; '
        'para la demostración en vivo, respetar la instrucción del profesor de calcular el '
        'procesamiento y métricas operativas dentro de los microcontroladores.', '',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Consolida pruebas ASM y calcula MSE/SNR solo con señales completas y referencia limpia.')
    parser.add_argument('resultados', type=Path, help='Carpeta Resultados_ASM o su archivo ZIP')
    parser.add_argument('--validacion-software', type=Path, default=None, help='Carpeta/ZIP con caso_N_rep_N_senales.npz')
    parser.add_argument('--salida', type=Path, default=None, help='Directorio donde guardar los informes CSV/Markdown')
    parser.add_argument('--desfase-fir', type=int, default=0, help='Retardo FIR conocido en muestras; positivo significa salida tardía')
    parser.add_argument('--desfase-fft', type=int, default=0, help='Retardo FFT conocido en muestras; positivo significa salida tardía')
    args = parser.parse_args()
    out = args.salida or ((args.resultados / 'Reporte_metricas') if args.resultados.is_dir()
                          else args.resultados.with_name('Reporte_metricas_' + args.resultados.stem))
    out.mkdir(parents=True, exist_ok=True)
    src = Source(args.resultados)
    try:
        trials = summarize_telemetry(src)
        summary = per_condition(trials)
        measured = metricas_fisicas(src, trials, args.desfase_fir, args.desfase_fft)
    finally:
        src.close()
    if not trials:
        print('AVISO: no se encontraron archivos P*_rep*/telemetria.csv', file=sys.stderr)
    sims = []
    if args.validacion_software:
        simsrc = Source(args.validacion_software)
        try:
            sims = metricas_simuladas(simsrc, args.desfase_fir, args.desfase_fft)
        finally:
            simsrc.close()
    trial_fields = ['prueba','repeticion','archivo','registros_mtr','filas_totales','tono_hz']
    trial_fields += [k+'_media' for k in MTR_FIELDS]
    for k in COUNTERS:
        trial_fields += [k+'_max',k+'_ultimo']
    summary_fields=['prueba','repeticiones','repeticiones_ids']
    for k in MTR_FIELDS:
        summary_fields += [k+'_promedio',k+'_desv_entre_reps']
    summary_fields += [k+'_max' for k in COUNTERS]
    write_csv(out/'telemetria_por_repeticion.csv', trials, trial_fields)
    write_csv(out/'telemetria_por_prueba.csv', summary, summary_fields)
    write_csv(out/'mse_snr_capturas_fisicas.csv', measured, RESULT_FIELDS)
    if args.validacion_software:
        write_csv(out/'mse_snr_validacion_software.csv', sims, RESULT_FIELDS)
    (out/'reporte_metricas.md').write_text(report(trials, summary, measured, sims),encoding='utf-8')
    print(f'Reporte generado en: {out.resolve()}')
    print(f'Ejecuciones con telemetría: {len(trials)}')
    print(f'MSE/SNR con series medidas proporcionadas: {sum(r["estado"]=="CALCULADO_DE_MUESTRAS_SUMINISTRADAS" for r in measured)}')
    print(f'MSE/SNR de validación de software: {sum(r["estado"]=="CALCULADO_SIMULACION" for r in sims)}')
    if not any(r['estado']=='CALCULADO_DE_MUESTRAS_SUMINISTRADAS' for r in measured):
        print('IMPORTANTE: MSE/SNR físicas no calculables con telemetria.csv y estimulo.wav solamente.')


if __name__=='__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
