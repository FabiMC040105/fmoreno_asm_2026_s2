#!/usr/bin/env python3
"""Guarda en PC la telemetria calculada por la ESP32 de nodos 2/3.
El procesamiento FIR y FFT sigue ocurriendo DENTRO de la ESP32.
Instalar: py -m pip install pyserial
Ejemplo: py registrar_serial.py --puerto COM8 --prueba P1 --repeticion 1 --segundos 15
"""
import argparse, csv, math, statistics, time
from datetime import datetime
from pathlib import Path
import serial

CAMPOS = [
    'seq','adc_flags','bloques_ok','errores_crc','errores_formato',
    'saltos_secuencia','errores_dac','captura_adc_us','dsp_us','i2s_write_us',
    'heap_libre_bytes','heap_min_bytes','fft_reservada_bytes',
    'rms_entrada','rms_fir','rms_fft','energia_total_fir_pct',
    'energia_total_fft_pct','tono_hz','atenuacion_tono_fir_db','atenuacion_tono_fft_db'
]
# Campos que NO pueden inferirse de entrada contaminada y salidas sin s[n] limpia.
REFERENCIA = [
    'mse_fir','mse_fft','snr_entrada_db','snr_fir_db','snr_fft_db',
    'delta_snr_fir_db','delta_snr_fft_db','energia_util_fir_pct',
    'energia_util_fft_pct','latencia_extremo_a_extremo_ms'
]

def main():
    a=argparse.ArgumentParser(description='Registro de telemetria de ESP32 en CSV')
    a.add_argument('--puerto', required=True, help='Ej: COM8')
    a.add_argument('--prueba', required=True, choices=['P1','P2','P3','P4','P5','P6'])
    a.add_argument('--repeticion', type=int, required=True)
    a.add_argument('--segundos', type=float, default=15)
    a.add_argument('--baud', type=int, default=115200)
    a.add_argument('--salida', default='resultados_p1_p6')
    args=a.parse_args()
    if args.repeticion<1 or args.segundos<=0: a.error('repeticion>0 y segundos>0')
    output=Path(args.salida);output.mkdir(parents=True,exist_ok=True)
    stem=f'{args.prueba}_rep{args.repeticion}_{datetime.now():%Y%m%d_%H%M%S}'
    path=output/(stem+'.csv'); log=output/(stem+'.log'); summary=output/(stem+'_resumen.txt')
    rows=[]
    with serial.Serial(args.puerto,args.baud,timeout=.5) as port, \
         path.open('w',newline='',encoding='utf-8') as f, \
         log.open('w',encoding='utf-8') as raw:
        writer=csv.DictWriter(f,fieldnames=['prueba','repeticion','fecha_pc']+CAMPOS+REFERENCIA)
        writer.writeheader()
        print('Registro abierto. La ESP32 puede reiniciarse al abrir el puerto.')
        print('Inicien el estimulo cuando se vea que llegan bloques. Ctrl+C para cerrar.')
        inicio=time.monotonic()
        try:
            while time.monotonic()-inicio<args.segundos:
                line=port.readline().decode('utf-8','replace').strip()
                if not line: continue
                raw.write(line+'\n')
                if not line.startswith('MTR,'):
                    print(line)
                    continue
                fields=line.split(',')[1:]
                if len(fields)!=len(CAMPOS):
                    print('Fila incompleta, ignorada:',line[:100]);continue
                record=dict(zip(CAMPOS,fields))
                # nan/inf -> vacio; evita falsas cifras en el informe.
                for k,v in record.items():
                    try:
                        if not math.isfinite(float(v)): record[k]=''
                    except ValueError:
                        record[k]=''
                record.update({'prueba':args.prueba,'repeticion':args.repeticion,
                               'fecha_pc':datetime.now().isoformat(timespec='seconds')})
                for k in REFERENCIA:record[k]=''
                writer.writerow(record);f.flush();rows.append(record)
                print(f"{args.prueba}/{args.repeticion}: bloque={record['bloques_ok']} "
                      f"DSP={record['dsp_us']}us heap={record['heap_libre_bytes']} "
                      f"CRC={record['errores_crc']}")
        except KeyboardInterrupt:
            pass
    with summary.open('w',encoding='utf-8') as f:
        f.write(f'{args.prueba} repeticion {args.repeticion}\nFilas MTR: {len(rows)}\n')
        for col in ['captura_adc_us','dsp_us','i2s_write_us','heap_libre_bytes',
                    'rms_entrada','rms_fir','rms_fft','energia_total_fir_pct',
                    'energia_total_fft_pct','atenuacion_tono_fir_db','atenuacion_tono_fft_db']:
            vals=[]
            for r in rows:
                try:vals.append(float(r[col]))
                except (ValueError,KeyError):pass
            if vals:
                f.write(f'{col}: media={statistics.mean(vals):.5f}; '
                        f'max={max(vals):.5f}; min={min(vals):.5f}\n')
        f.write('MSE/SNR/energia util: NO DISPONIBLES sin referencia limpia alineada.\n')
        f.write('Latencia extremo-a-extremo: NO medida por relojes de distintas placas.\n')
    print('Guardado:',path,'y',summary)
    if not rows: print('ADVERTENCIA: no llegaron filas MTR; revise que el receptor este ejecutando la version instrumentada.')
if __name__=='__main__':main()
