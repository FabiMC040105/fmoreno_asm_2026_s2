#!/usr/bin/env python3
"""Genera WAV limpios, ruido y mezcla para P1-P5, 3 repeticiones por caso.
Solo genera estimulos: NO equivale a haber probado las dos ESP32.
Requiere numpy: py -m pip install numpy
Ejemplo: py generar_estímulos_p1_p5.py --segundos 10 --reps 3
"""
from pathlib import Path
import argparse, json, wave
import numpy as np

FS=48000

def writewav(path, signal):
    vals=(np.clip(signal,-.999,.999)*32767).astype('<i2')
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(FS)
        wav.writeframes(vals.tobytes())

def bandnoise(rng,n,lo,hi):
    z=rng.standard_normal(n)
    freqs=np.fft.rfftfreq(n,1.0/FS)
    Z=np.fft.rfft(z)
    Z[(freqs<lo)|(freqs>hi)]=0
    y=np.fft.irfft(Z,n)
    std=float(np.std(y))
    return y/max(std,1e-12)

def synth(case,rep,secs):
    rng=np.random.default_rng(20261106+100*int(case[1:])+rep)
    n=int(FS*secs);t=np.arange(n)/FS
    fade=np.minimum(1,np.arange(n)/(0.05*FS+1))
    fade*=np.minimum(1,(n-1-np.arange(n))/(0.05*FS+1))
    if case=='P1':
        clean=.38*np.sin(2*np.pi*512*t)
        noise=np.sin(2*np.pi*1792*t)
        target=5.0
        description='Tono limpio 512 Hz + interferencia 1792 Hz'
    elif case=='P2':
        clean=.24*np.sin(2*np.pi*256*t)+.20*np.sin(2*np.pi*512*t)+.20*np.sin(2*np.pi*1024*t)
        noise=bandnoise(rng,n,1650,2850)
        target=5.0
        description='Tres tonos 256/512/1024 + ruido alto 1650-2850 Hz'
    elif case=='P3':
        # Senal arbitraria sintetica. Para audio del profesor usar su fuente real.
        phase=2*np.pi*(260*t+(1190-260)/(2*secs)*t*t)
        clean=.40*np.sin(phase)*(0.5+0.5*np.sin(2*np.pi*2.3*t)**2)
        noise=rng.standard_normal(n)
        target=3.0
        description='Barrido arbitrario + ruido blanco; sustituir por audio indicado por profesor cuando aplique'
    elif case=='P4':
        clean=np.zeros(n)
        for tm in np.arange(.7,secs-.2,1.6):
            clean+=.42*np.exp(-.5*((t-tm)/.012)**2)
        noise=np.zeros(n)
        for tm in np.arange(1.1,secs-.1,.82):
            idx=int((tm+rng.uniform(-.045,.045))*FS)
            if 0<=idx<n:
                width=min(int(.0015*FS),n-idx)
                noise[idx:idx+width]+=rng.choice([-1,1])*rng.uniform(.5,1.0)
        noise+=.03*rng.standard_normal(n)
        target=3.0
        description='Pulsos transitorios + ruido impulsivo'
    elif case=='P5':
        clean=.24*np.sin(2*np.pi*256*t)+.18*np.sin(2*np.pi*512*t)+.18*np.sin(2*np.pi*1024*t)
        noise=bandnoise(rng,n,850,1300)
        target=0.0
        description='Tres tonos + ruido 850-1300 Hz, banda parcialmente superpuesta'
    else:raise ValueError(case)
    clean*=fade;noise*=fade
    power_clean=np.mean(clean**2);power_noise=np.mean(noise**2)
    gain=np.sqrt(power_clean/max(power_noise,1e-14))*10**(-target/20.0)
    noise=noise*gain
    mix=clean+noise
    global_scale=.90/max(.90,float(np.max(np.abs(mix))),float(np.max(np.abs(clean))))
    return clean*global_scale,noise*global_scale,mix*global_scale,description,target

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--segundos',type=float,default=10)
    parser.add_argument('--reps',type=int,default=3)
    parser.add_argument('--salida',default='estimulos_p1_p5')
    a=parser.parse_args()
    if a.segundos<2 or a.reps<1:parser.error('segundos>=2, reps>=1')
    out=Path(a.salida);out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for case in ['P1','P2','P3','P4','P5']:
        for rep in range(1,a.reps+1):
            clean,noise,mix,desc,snr=synth(case,rep,a.segundos)
            for tag,signal in [('limpia',clean),('ruido',noise),('mezcla',mix)]:
                writewav(out/f'{case}_rep{rep}_{tag}.wav',signal)
            manifest.append({'prueba':case,'repeticion':rep,'descripcion':desc,
                             'fs_wav_hz':FS,'duracion_s':a.segundos,
                             'snr_digital_objetivo_db':snr,
                             'nota':'La SNR acustica real en el microfono NO es necesariamente la del WAV'})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    print('Generados',len(manifest)*3,'WAV + manifest.json en',out)
    print('P6 NO se genera: el profesor debe definir la condicion desconocida.')
if __name__=='__main__':main()
