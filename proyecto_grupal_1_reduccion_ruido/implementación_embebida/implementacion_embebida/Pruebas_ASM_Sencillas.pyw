#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Banco simple P1-P6 para Windows. 1 archivo; sin cambios al firmware ESP32.
Necesita pyserial. El PC reproduce estimulos; la ESP32 procesa el audio.
No mide la salida analogica ni calcula SNR/MSE fisicos sin referencia limpia.
"""
import csv
import html
import math
import queue
import random
import re
import statistics
import struct
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import winsound
except ImportError:
    winsound = None
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

BAUD = 115200
FS_WAV = 48000
FIELDS = [
    'seq','adc_flags','bloques_ok','errores_crc','errores_formato',
    'saltos_secuencia','errores_dac','captura_adc_us','dsp_us','i2s_write_us',
    'heap_libre_bytes','heap_min_bytes','fft_reservada_bytes',
    'rms_entrada','rms_fir','rms_fft','energia_total_fir_pct',
    'energia_total_fft_pct','tono_hz','atenuacion_tono_fir_db',
    'atenuacion_tono_fft_db'
]
OUTPUT_FIELDS = ['fecha_pc','segundos','fuente'] + FIELDS
PATTERN = re.compile(
    r'Bloques=(\d+)\s*\|\s*DSP\+DAC pack=(\d+) us\s*\|\s*'
    r'I2S write=(\d+) us\s*\|\s*FFT frames=(\d+)\s*\|\s*'
    r'flags_N1=([0-9a-fA-F]+)\s*\|\s*CRC errores=(\d+)\s*\|\s*gaps=(\d+)'
)


def parse_line(line, elapsed):
    """Admite tanto receptor original como receptor instrumentado."""
    row = dict.fromkeys(OUTPUT_FIELDS, '')
    row['fecha_pc'] = datetime.now().isoformat(timespec='seconds')
    row['segundos'] = f'{elapsed:.3f}'
    if line.startswith('MTR,'):
        parts = line.split(',')[1:]
        if len(parts) != len(FIELDS):
            return None
        row['fuente'] = 'MTR'
        for k, v in zip(FIELDS, parts):
            try:
                x = float(v)
                if math.isfinite(x):
                    row[k] = v
            except (ValueError, OverflowError):
                pass
        return row
    match = PATTERN.search(line)
    if match:
        row['fuente'] = 'BLOQUES'
        (row['bloques_ok'], row['dsp_us'], row['i2s_write_us'], _, flags,
         row['errores_crc'], row['saltos_secuencia']) = match.groups()
        row['adc_flags'] = str(int(flags, 16))
        return row
    return None


def make_wav(path, prueba, repeticion, segundos, input_wav=''):
    """Genera estímulos DIGITALES. No son muestras del micrófono ni del DAC."""
    if prueba == 'P6':
        return None
    if prueba == 'P3':
        if not input_wav:
            raise ValueError('P3 requiere elegir un archivo WAV de audio útil.')
        with wave.open(input_wav, 'rb') as f:
            nchan, sw, hz = f.getnchannels(), f.getsampwidth(), f.getframerate()
            if sw != 2 or nchan not in (1, 2) or f.getcomptype() != 'NONE':
                raise ValueError('Para P3 elegí un WAV PCM16, mono o estéreo.')
            data = f.readframes(f.getnframes())
        # Preservamos frecuencia y duración original del WAV para P3.
        samples = struct.unpack('<' + 'h' * (len(data)//2), data)
        rng = random.Random(20261106 + repeticion)
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(hz)
            pcm = bytearray()
            for i in range(0, len(samples), nchan):
                clean = sum(samples[i:i+nchan]) / (32768.0 * nchan)
                val = 0.6 * clean + 0.12 * rng.uniform(-1, 1)
                pcm.extend(struct.pack('<h', int(max(-1, min(1, val))*32767)))
            out.writeframes(pcm)
        return path

    n = int(FS_WAV * segundos)
    rng = random.Random(20261106 + repeticion + int(prueba[1:])*100)
    # Prefijar fases y frecuencias para comparar repeticiones reproduciblemente.
    band_freqs = [rng.uniform(850, 1300) for _ in range(14)]
    band_phases = [rng.uniform(0, 2*math.pi) for _ in band_freqs]
    high_freqs = [rng.uniform(1700, 3200) for _ in range(14)]
    high_phases = [rng.uniform(0, 2*math.pi) for _ in high_freqs]
    frames = bytearray()
    for i in range(n):
        t = i / FS_WAV
        useful = 0.0
        noise = 0.0
        if prueba == 'P1':
            useful = 0.32 * math.sin(2*math.pi*512*t)
            noise = 0.18 * math.sin(2*math.pi*1792*t)
        elif prueba == 'P2':
            useful = sum(0.12 * math.sin(2*math.pi*f*t) for f in (256,512,1024))
            noise = sum(0.012 * math.sin(2*math.pi*f*t+p) for f,p in zip(high_freqs, high_phases))
        elif prueba == 'P4':
            useful = 0.30 * math.sin(2*math.pi*512*t) * (1 if (t % 0.8) < 0.3 else 0)
            # Impulsos artificiales muy breves y de amplitud limitada.
            noise = 0.38 if i % max(1,int(.77*FS_WAV)) < 8 else 0
        elif prueba == 'P5':
            useful = sum(0.12 * math.sin(2*math.pi*f*t) for f in (256,512,1024))
            noise = sum(0.010 * math.sin(2*math.pi*f*t+p) for f,p in zip(band_freqs, band_phases))
        val = max(-0.85, min(0.85, useful + noise))
        frames.extend(struct.pack('<h', int(val * 32767)))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(FS_WAV)
        out.writeframes(frames)
    return path


def svg_plot(path, rows, keys, title):
    # Gráfica SVG sin instalar matplotlib, directamente abrible en navegador.
    present = []
    for key, label, color in keys:
        points = []
        for row in rows:
            try:
                x, y = float(row['segundos']), float(row[key])
                if math.isfinite(x) and math.isfinite(y):
                    points.append((x, y))
            except (ValueError, TypeError, KeyError):
                pass
        if points:
            present.append((label, color, points))
    if not present:
        return False
    xs = [x for _, _, ps in present for x, _ in ps]
    ys = [y for _, _, ps in present for _, y in ps]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax <= xmin: xmax = xmin + 1
    if ymax <= ymin: ymax = ymin + 1
    pad = 0.1*(ymax-ymin)
    ymin, ymax = ymin-pad, ymax+pad
    w,h = 880,410
    left, right, top, bottom = 85, 25, 50, 70
    pw, ph = w-left-right, h-top-bottom
    xpx = lambda x: left + (x-xmin)/(xmax-xmin)*pw
    ypx = lambda y: top + (ymax-y)/(ymax-ymin)*ph
    items = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{left}" y="28" font-family="Arial" font-size="19" font-weight="bold">{html.escape(title)}</text>']
    for j in range(5):
        yy = top + ph*j/4
        val = ymax - (ymax-ymin)*j/4
        items.append(f'<line x1="{left}" x2="{left+pw}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e5e7eb"/>')
        items.append(f'<text x="{left-9}" y="{yy+4:.1f}" text-anchor="end" font-family="Arial" font-size="12" fill="#374151">{val:.2f}</text>')
    items.append(f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#334155"/>')
    items.append(f'<text x="{left+pw/2:.0f}" y="{h-18}" text-anchor="middle" font-family="Arial" font-size="13">Tiempo desde inicio (s)</text>')
    for i,(label,color,points) in enumerate(present):
        coords = ' '.join(f'{xpx(x):.1f},{ypx(y):.1f}' for x,y in points)
        items.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        lx, ly = left+i*220, h-43
        items.append(f'<line x1="{lx}" x2="{lx+20}" y1="{ly}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        items.append(f'<text x="{lx+26}" y="{ly+4}" font-family="Arial" font-size="12">{html.escape(label)}</text>')
    items.append('</svg>')
    path.write_text('\n'.join(items),encoding='utf-8')
    return True


def save_results(folder, rows, log, test, rep, wav_path, duration):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'telemetria.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=OUTPUT_FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    (folder/'monitor_serial.log').write_text('\n'.join(log)+'\n',encoding='utf-8')
    charts = [
        ('tiempos.svg', [('captura_adc_us','ADC (us)','#7c3aed'),('dsp_us','DSP (us)','#0d9488'),('i2s_write_us','I2S (us)','#e87800')], 'Tiempos reportados por firmware (microsegundos)'),
        ('errores.svg', [('errores_crc','CRC','#dc2626'),('saltos_secuencia','Secuencia','#9333ea'),('errores_dac','DAC','#ca8a04')], 'Contadores acumulados de errores'),
        ('memoria.svg', [('heap_libre_bytes','Heap libre (B)','#2563eb'),('heap_min_bytes','Heap mínimo (B)','#16a34a')], 'Memoria libre reportada por receptor'),
        ('energia.svg', [('energia_total_fir_pct','Energía FIR %','#ea580c'),('energia_total_fft_pct','Energía FFT %','#0284c7')], 'Energía TOTAL relativa (no energía útil)'),
        ('atenuacion.svg', [('atenuacion_tono_fir_db','FIR (dB)','#ea580c'),('atenuacion_tono_fft_db','FFT (dB)','#0284c7')], 'Atenuación estimada de tono configurado'),
    ]
    generated=[]
    for name, cols, title in charts:
        if svg_plot(folder/name,rows,cols,title):generated.append(name)
    max_block = max((int(float(r['bloques_ok'])) for r in rows if r.get('bloques_ok')),default=0)
    summary=[f'Prueba {test}, repetición {rep}', f'Duración de captura solicitada: {duration} s',
             f'Filas válidas: {len(rows)}',f'Bloque máximo observado: {max_block}',
             f'Estímulo digital: {wav_path.name if wav_path else "externo/no generado"}',
             'Los valores provienen del receptor y NO constituyen una captura del sonido DAC.',
             'MSE, SNR, energía ÚTIL y latencia física: no calculables con estos registros.']
    for col in ('dsp_us','i2s_write_us','errores_crc','saltos_secuencia','heap_libre_bytes'):
        vals=[]
        for row in rows:
            try:vals.append(float(row[col]))
            except (ValueError,TypeError,KeyError):pass
        if vals:summary.append(f'{col}: media={statistics.mean(vals):.2f}; último={vals[-1]:.2f}')
    (folder/'resumen.txt').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    return generated, len(rows)


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Pruebas ASM — Captura simple P1–P6')
        self.root.geometry('760x430')
        self.root.resizable(False, False)
        self.port = tk.StringVar()
        self.test = tk.StringVar(value='P1')
        self.reps = tk.IntVar(value=1)
        self.duration = tk.StringVar(value='15')
        self.wav = tk.StringVar()
        self.folder = tk.StringVar(value=str(Path.home()/'Desktop'/'Resultados_ASM'))
        self.sound = tk.BooleanVar(value=True)
        self.busy = False
        self.cancel = threading.Event()
        self.events = queue.Queue()
        box=ttk.Frame(root,padding=16)
        box.pack(fill='both',expand=True)
        ttk.Label(box,text='Banco sencillo P1–P6',font=('Segoe UI',16,'bold')).grid(row=0,column=0,columnspan=4,sticky='w',pady=(0,12))
        ttk.Label(box,text='Puerto COM receptor:').grid(row=1,column=0,sticky='w')
        self.ports=ttk.Combobox(box,textvariable=self.port,width=16)
        self.ports.grid(row=1,column=1,sticky='w')
        ttk.Button(box,text='Actualizar puertos',command=self.refresh_ports).grid(row=1,column=2,sticky='w',padx=9)
        ttk.Label(box,text='115200 baud').grid(row=1,column=3,sticky='w')
        ttk.Label(box,text='Prueba:').grid(row=2,column=0,sticky='w',pady=10)
        ttk.Combobox(box,textvariable=self.test,values=['P1','P2','P3','P4','P5','P6'],state='readonly',width=7).grid(row=2,column=1,sticky='w')
        ttk.Label(box,text='Repeticiones:').grid(row=2,column=2,sticky='e')
        tk.Spinbox(box,from_=1,to=10,textvariable=self.reps,width=5).grid(row=2,column=3,sticky='w',padx=9)
        ttk.Label(box,text='Segundos por repetición:').grid(row=3,column=0,sticky='w')
        ttk.Entry(box,textvariable=self.duration,width=9).grid(row=3,column=1,sticky='w')
        ttk.Checkbutton(box,text='Reproducir estímulo por altavoces PC (P1–P5)',variable=self.sound).grid(row=3,column=2,columnspan=2,sticky='w')
        ttk.Label(box,text='WAV útil para P3:').grid(row=4,column=0,sticky='w',pady=10)
        ttk.Entry(box,textvariable=self.wav,width=39).grid(row=4,column=1,columnspan=2,sticky='we')
        ttk.Button(box,text='Elegir WAV',command=self.choose_wav).grid(row=4,column=3,sticky='w',padx=8)
        ttk.Label(box,text='Guardar en:').grid(row=5,column=0,sticky='w')
        ttk.Entry(box,textvariable=self.folder,width=42).grid(row=5,column=1,columnspan=2,sticky='we')
        ttk.Button(box,text='Elegir carpeta',command=self.choose_folder).grid(row=5,column=3,sticky='w',padx=8)
        self.start_btn=ttk.Button(box,text='INICIAR PRUEBA',command=self.start)
        self.start_btn.grid(row=6,column=0,columnspan=2,sticky='we',pady=15)
        self.stop_btn=ttk.Button(box,text='Detener',command=self.stop,state='disabled')
        self.stop_btn.grid(row=6,column=2,sticky='we')
        self.status=tk.StringVar(value='Listo. Cerrar Monitor Serial antes de iniciar.')
        ttk.Label(box,textvariable=self.status,foreground='#0b6b57',wraplength=650).grid(row=7,column=0,columnspan=4,sticky='w')
        self.log=tk.Text(box,height=6,width=82,wrap='word',font=('Consolas',9))
        self.log.grid(row=8,column=0,columnspan=4,sticky='we',pady=10)
        ttk.Label(box,text='El firmware sigue filtrando en las ESP32. Este programa no mide SNR/MSE ni captura muestras de audio.',
                  foreground='#555').grid(row=9,column=0,columnspan=4,sticky='w')
        self.refresh_ports()
        self.root.after(120,self.poll)

    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()] if list_ports else []
        self.ports['values']=ports
        if ports and self.port.get() not in ports:self.port.set(ports[0])
    def choose_folder(self):
        path=filedialog.askdirectory(initialdir=self.folder.get() if Path(self.folder.get()).exists() else str(Path.home()))
        if path:self.folder.set(path)
    def choose_wav(self):
        path=filedialog.askopenfilename(filetypes=[('Audio WAV','*.wav')])
        if path:self.wav.set(path)
    def event(self,what,value=''):
        self.events.put((what,value))
    def start(self):
        if self.busy:return
        if serial is None:
            messagebox.showerror('Falta pyserial','Instalá pyserial una sola vez: Python -m pip install pyserial.\nSi ya instalaste el panel anterior, probablemente esté disponible.')
            return
        try:
            dur=float(self.duration.get().replace(',','.'))
            reps=int(self.reps.get())
            if dur<=0 or dur>600 or reps<1 or reps>10:raise ValueError
        except ValueError:
            messagebox.showerror('Valores inválidos','Usá 1–600 segundos y 1–10 repeticiones.');return
        if not self.port.get().strip():messagebox.showerror('Falta puerto','Elegí el puerto COM del receptor.');return
        test=self.test.get()
        if test=='P3' and self.sound.get() and not Path(self.wav.get()).is_file():
            messagebox.showerror('Falta WAV','P3 necesita un WAV PCM16 mono/estéreo o desactivar Reproducir estímulo.');return
        self.busy=True
        self.cancel.clear()
        self.start_btn['state']='disabled';self.stop_btn['state']='normal'
        self.log.delete('1.0','end')
        cfg=(self.port.get(),test,reps,dur,Path(self.folder.get()),self.sound.get(),self.wav.get())
        threading.Thread(target=self.worker,args=(cfg,),daemon=True).start()
    def stop(self):
        self.cancel.set()
        self.status.set('Deteniendo la captura de forma segura...')
    def worker(self,cfg):
        port,test,reps,dur,root,play,wav=cfg
        try:
            session=root/('Sesion_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
            session.mkdir(parents=True,exist_ok=True)
            self.event('log',f'Guardando todo en: {session}\n')
            for rep in range(1,reps+1):
                if self.cancel.is_set():break
                folder=session/f'{test}_rep{rep}'
                folder.mkdir(parents=True,exist_ok=True)
                wav_path=None
                if play and test!='P6':
                    self.event('log',f'Preparando estímulo digital {test}/{rep}...')
                    wav_path=make_wav(folder/'estimulo.wav',test,rep,dur,wav)
                self.event('status',f'Abriendo {port} para {test}, repetición {rep}/{reps}...')
                rows=[];raw=[]
                # Abrir puerto puede reiniciar la ESP32. Se deja arranque inicial.
                with serial.Serial(port,BAUD,timeout=.2) as device:
                    boot_end=time.monotonic()+1.8
                    while time.monotonic()<boot_end and not self.cancel.is_set():
                        device.readline()
                    if self.cancel.is_set():break
                    self.event('status',f'Capturando {test}, repetición {rep}/{reps} ({dur:g} s).')
                    if play and wav_path and winsound:
                        winsound.PlaySound(str(wav_path),winsound.SND_FILENAME|winsound.SND_ASYNC)
                    elif play and wav_path and not winsound:
                        self.event('log','AVISO: reproducción automática solo disponible en Windows.')
                    started=time.monotonic()
                    while time.monotonic()-started<dur and not self.cancel.is_set():
                        line=device.readline().decode('utf-8','replace').strip()
                        if not line:continue
                        elapsed=time.monotonic()-started
                        raw.append(f'{elapsed:.3f} | {line}')
                        row=parse_line(line,elapsed)
                        if row:
                            rows.append(row)
                            if len(rows)%4==0:self.event('status',f'{test}/{rep}: {len(rows)} filas recibidas. Último bloque: {row.get("bloques_ok")}')
                    if play and wav_path and winsound:
                        winsound.PlaySound(None,0)
                generated,count=save_results(folder,rows,raw,test,rep,wav_path,dur)
                self.event('log',f'{test}/{rep}: {count} filas, {len(generated)} gráficas. Carpeta: {folder.name}')
                if not count:self.event('log','AVISO: sin filas: revisar COM correcto, serial cerrado y conexión N1B2.')
                if rep<reps and not self.cancel.is_set():
                    self.event('status','Repetición completada. Pausa de 1 segundo...')
                    time.sleep(1)
            self.event('status',f'Terminado. Archivos en: {session}')
            self.event('log',f'FIN. Podés abrir la carpeta de resultados: {session}')
        except serial.SerialException as exc:
            self.event('error',f'No se pudo abrir o leer {port}. Cerrá el Monitor Serial de Arduino y otras aplicaciones.\n{exc}')
        except Exception as exc:
            self.event('error',f'No se pudo completar: {type(exc).__name__}: {exc}')
        finally:
            if winsound:
                try:winsound.PlaySound(None,0)
                except Exception:pass
            self.event('finished')
    def poll(self):
        try:
            while True:
                what,value=self.events.get_nowait()
                if what=='status':self.status.set(value)
                elif what=='log':
                    self.log.insert('end',value+'\n');self.log.see('end')
                elif what=='error':messagebox.showerror('Error de captura',value);self.status.set('Error. Ver detalles en el aviso.')
                elif what=='finished':
                    self.busy=False
                    self.start_btn['state']='normal';self.stop_btn['state']='disabled'
        except queue.Empty:
            pass
        self.root.after(120,self.poll)


if __name__=='__main__':
    app=tk.Tk()
    MainApp(app)
    app.mainloop()
