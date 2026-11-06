#!/usr/bin/env python3
"""Metricas cuantitativas SOLO cuando existen senal limpia y capturas alineables.
Entrada CSV: columnas clean,input,fir,fft a Fs=8192 nominales, igual reloj/alineacion.
Uso: py calcular_metricas_referencia.py datos.csv --prueba P1 --repeticion 1 --tono 1792
Opciones: --lag-input 0 --lag-fir 512 --lag-fft 512 (valores EJEMPLO, medirlos).
Requiere numpy: py -m pip install numpy
"""
import argparse,csv,math
import numpy as np
from pathlib import Path

def snr(clean,estimate):
    e=float(np.dot(clean,clean));err=float(np.dot(clean-estimate,clean-estimate))
    return 10*math.log10(e/err) if e>1e-15 and err>1e-15 else float('nan')

def energy_retained(clean,estimate):
    # Cuadrado de la proyeccion sobre la referencia limpia; puede exceder 100.
    e=float(np.dot(clean,clean))
    if e<=1e-15:return float('nan')
    projection=float(np.dot(estimate,clean))/e
    return 100*projection*projection

def dft_amplitude(samples,tone,fs):
    t=np.arange(len(samples),dtype=float)
    return abs(np.sum(samples*np.exp(-2j*np.pi*tone*t/fs)))/len(samples)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('csv',help='CSV con clean,input,fir,fft, muestras alineables')
    p.add_argument('--prueba',required=True)
    p.add_argument('--repeticion',type=int,required=True)
    p.add_argument('--fs',type=float,default=8192)
    p.add_argument('--tono',type=float,default=None)
    p.add_argument('--lag-input',type=int,default=0)
    p.add_argument('--lag-fir',type=int,default=0)
    p.add_argument('--lag-fft',type=int,default=0)
    p.add_argument('--salida',default='metricas_con_referencia.csv')
    a=p.parse_args()
    data=np.genfromtxt(a.csv,delimiter=',',names=True,dtype=float)
    if any(name not in data.dtype.names for name in ('clean','input','fir','fft')):
        p.error('El CSV debe tener columnas: clean,input,fir,fft')
    series={k:np.atleast_1d(data[k]) for k in ('clean','input','fir','fft')}
    shifts={'input':a.lag_input,'fir':a.lag_fir,'fft':a.lag_fft}
    # Comparamos SOLO el intervalo comun: y[n+lag] corresponde a clean[n].
    indices=np.arange(len(series['clean']))
    mask=np.isfinite(series['clean'])
    for k,lag in shifts.items():
        at=indices+lag
        mask &= (at>=0)&(at<len(series[k]))
    common=indices[mask]
    if len(common)<512: p.error('Muy pocas muestras comunes; revise lags')
    x=series['clean'][common]
    aligned={k:series[k][common+lag] for k,lag in shifts.items()}
    finite=np.isfinite(x)
    for v in aligned.values():finite &= np.isfinite(v)
    x=x[finite];aligned={k:v[finite] for k,v in aligned.items()}
    if len(x)<512:p.error('Muestras no finitas o alineacion invalida')
    sin=snr(x,aligned['input'])
    result={'prueba':a.prueba,'repeticion':a.repeticion,'N':len(x),'fs_hz':a.fs,
            'lag_input':a.lag_input,'lag_fir':a.lag_fir,'lag_fft':a.lag_fft,
            'snr_entrada_db':sin}
    for route in ('fir','fft'):
        y=aligned[route]
        sout=snr(x,y)
        result[f'mse_{route}']=float(np.mean((x-y)**2))
        result[f'snr_{route}_db']=sout
        result[f'delta_snr_{route}_db']=sout-sin
        result[f'energia_util_{route}_pct']=energy_retained(x,y)
        result[f'energia_total_{route}_pct']=100*float(np.dot(y,y))/max(1e-15,float(np.dot(aligned['input'],aligned['input'])))
        result[f'atenuacion_tono_{route}_db']=''
        if a.tono is not None:
            u=dft_amplitude(aligned['input'],a.tono,a.fs)
            v=dft_amplitude(y,a.tono,a.fs)
            if u>1e-6:result[f'atenuacion_tono_{route}_db']=20*math.log10(u/max(v,1e-12))
    output=Path(a.salida);new=not output.exists()
    with output.open('a',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(result));
        if new: writer.writeheader()
        writer.writerow(result)
    for k,v in result.items():print(f'{k}: {v}')
    print('Guardado:',output)
if __name__=='__main__':main()
