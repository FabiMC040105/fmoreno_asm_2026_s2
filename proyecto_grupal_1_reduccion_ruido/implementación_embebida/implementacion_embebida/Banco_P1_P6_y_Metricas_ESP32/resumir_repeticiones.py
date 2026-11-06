#!/usr/bin/env python3
"""Promedios y variabilidad por prueba a partir de los CSV guardados por registrar_serial.py.
Uso: py resumir_repeticiones.py --carpeta resultados_p1_p6
"""
import argparse,csv,statistics
from collections import defaultdict
from pathlib import Path
METRICS=['captura_adc_us','dsp_us','i2s_write_us','heap_libre_bytes',
'rms_entrada','rms_fir','rms_fft','energia_total_fir_pct',
'energia_total_fft_pct','atenuacion_tono_fir_db','atenuacion_tono_fft_db']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--carpeta',default='resultados_p1_p6')
    p.add_argument('--salida',default='resumen_p1_p6.csv')
    a=p.parse_args();folder=Path(a.carpeta)
    reps=defaultdict(list)
    for fn in sorted(folder.glob('P[1-6]_rep*.csv')):
        with fn.open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        if not rows or 'dsp_us' not in rows[0]:continue
        test=rows[0]['prueba'];rep=rows[0]['repeticion']
        for metric in METRICS:
            values=[]
            for row in rows:
                try:values.append(float(row[metric]))
                except (TypeError, ValueError, KeyError):continue
            if values:
                reps[(test,metric)].append((rep,statistics.mean(values)))
    out=folder/a.salida
    with out.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['prueba','metrica','repeticiones_con_datos','media_entre_repeticiones','desviacion_estandar_entre_repeticiones','minimo_repeticion','maximo_repeticion','estado'])
        for (test,metric),observations in sorted(reps.items()):
            # agrupar ficheros por id de repeticion, tomar ultimo archivo por rep
            d=dict(observations);vals=list(d.values());n=len(vals)
            w.writerow([test,metric,n,statistics.mean(vals),
                        statistics.stdev(vals) if n>1 else '',min(vals),max(vals),
                        ('REVISAR: menos de 3 reps' if test!='P6' and n<3 else 'OK')])
    print('Guardado:',out,'; pruebas/metrica:',len(reps))
if __name__=='__main__':main()
