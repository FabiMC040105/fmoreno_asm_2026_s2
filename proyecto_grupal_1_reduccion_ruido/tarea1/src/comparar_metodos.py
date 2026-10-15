"""Genera resultados/metricas.csv reproducible para la seccion 2.5.

Se usan exclusivamente las tres mezclas del apartado 2.2 y los filtros
aportados por las personas 3 y 4 (con correccion OLA documentada).
Ejecutar: python src/comparar_metodos.py

IMPORTANTE: tiempos son medidas de Python/PC; no del microcontrolador.
"""
from __future__ import annotations
import csv
import json
import platform
import sys
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from filtros_temporales import disenar_filtro, filtrar_por_bloques
from filtrado_espectral import reduccion_espectral_adaptativa

RAIZ=Path(__file__).resolve().parents[1]


def potencia(s):
    return float(np.dot(s,s)/len(s))


def mse(s,y):
    return potencia(np.asarray(s)-np.asarray(y))


def snr(s,y):
    error=mse(s,y)
    return float(10*np.log10(potencia(s)/error)) if error>0 else float('inf')


def tiempo_por_bloque(funcion, n_bloques, repeticiones=5):
    """Cronometra todo el procesamiento, excluyendo lectura/escritura."""
    funcion() # calentamiento
    tiempos=[]
    for _ in range(repeticiones):
        inicio=perf_counter_ns()
        funcion()
        tiempos.append((perf_counter_ns()-inicio)/1e6/n_bloques)
    return float(np.median(tiempos)), float(np.min(tiempos)), float(np.max(tiempos))


def fila_metrica(caso,metodo,s,r,x,y,s_filtrada,ruido_filtrado,
                 tiempo_ms,memoria_bytes,n_bloques,fs,n_bloque,extra=None):
    snr_entrada=snr(s,x)
    snr_salida=snr(s,y)
    referencia_energia=potencia(s)
    # La referencia s se pasa por el mismo filtro, sin emplearla para detectar
    # ruido. En método espectral las máscaras fueron APRENDIDAS SOLO DE x.
    # Esto permite estimar qué fracción de la energía de la señal limpia
    # se habría conservado al procesarla con esas mismas máscaras.
    energia=100*potencia(s_filtrada)/referencia_energia
    # Atenuación de potencia del ruido INYECTADO (conocido en simulación).
    # Para el método adaptativo, y - s_filtrada es la componente de ruido
    # después del mismo conjunto de máscaras dependientes de x.
    ruido_in=potencia(r)
    ruido_out=potencia(ruido_filtrado)
    atenuacion=float(10*np.log10(ruido_in/ruido_out)) if ruido_out>0 else float('inf')
    d={
        'caso':caso,'metodo':metodo,
        'fs_hz':fs,'n_bloque':n_bloque,'muestras':len(s),
        'snr_entrada_db':snr_entrada,
        'mse':mse(s,y),'snr_salida_db':snr_salida,
        'mejora_snr_db':snr_salida-snr_entrada,
        'energia_util_conservada_pct':energia,
        'atenuacion_ruido_inyectado_db':atenuacion,
        'mse_senal_limpia_filtrada':mse(s,s_filtrada),
        'tiempo_por_bloque_ms':tiempo_ms,
        'memoria_aprox_bytes':memoria_bytes,
        'bloques_procesados':n_bloques,
        'periodo_disponible_por_bloque_ms':1000*(n_bloque/fs if metodo!='Espectral' else n_bloque/(2*fs))
    }
    if extra: d.update(extra)
    return d


def guardar_imagenes(casos,carpeta):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(3,2,figsize=(12,10),layout='constrained')
    for j,(num,s,x,yt,ye,_,_) in enumerate(casos):
        n=len(s);t=np.arange(n)/8192.
        margen=(t>=.4)&(t<.435)
        for dato,nombre in ((s,'Limpia'),(x,'Contaminada'),(yt,'Temporal'),(ye,'Espectral')):
            ax[j,0].plot(t[margen]*1000,dato[margen],label=nombre,lw=1.0,alpha=.8)
            f=np.fft.rfftfreq(n,1/8192.)
            a=2*np.abs(np.fft.rfft(dato*np.hanning(n)))/np.hanning(n).sum()
            ax[j,1].plot(f,20*np.log10(np.maximum(a,1e-8)),label=nombre,lw=1.0,alpha=.8)
        ax[j,0].set(xlabel='Tiempo (ms)',ylabel='Amplitud',title=f'Caso {num} — tiempo')
        ax[j,1].set(xlabel='Frecuencia (Hz)',ylabel='Amplitud (dB ref. 1)',xlim=(0,2200),ylim=(-100,5),title=f'Caso {num} — FFT')
        for a in ax[j]:a.grid(alpha=.2);a.legend(fontsize=7)
    fig.savefig(carpeta/'comparacion_metodos.png',dpi=155)
    plt.close(fig)


def generar_metricas(raiz=RAIZ,repeticiones=5,crear_figuras=True):
    raiz=Path(raiz)
    config=json.loads((raiz/'metadatos/configuraciones.json').read_text(encoding='utf-8'))
    fs=int(config['fs_hz']);n_bloque=int(config['n_bloque']); L=int(config['n_total'])
    if n_bloque & (n_bloque-1):raise ValueError('N debe ser potencia de dos')
    if not (L%n_bloque==0):raise ValueError('Esta prueba requiere registros de bloques enteros')
    sos=np.asarray(disenar_filtro(fs)['sos'],dtype=np.float64)
    if len(sos)!=6:raise AssertionError('Filtro temporal inesperado: distinto de 6 SOS')
    carpeta=raiz/'resultados'; carpeta.mkdir(exist_ok=True)
    registros=[]; trazas=[]
    for numero in (1,2,3):
        inp=raiz/'pruebas'/f'caso_{numero}'
        s=np.load(inp/'limpia.npy'); r=np.load(inp/'ruido.npy'); x=np.load(inp/'contaminada.npy')
        if s.shape!=r.shape or x.shape!=s.shape or len(s)!=L:
            raise ValueError(f'Caso {numero}: tamaños incompatibles')
        if not np.allclose(x,s+r,rtol=0,atol=1e-12):
            raise ValueError(f'Caso {numero}: mezcla no coincide con s+ruido')
        if abs(snr(s,x)-{1:5,2:3,3:0}[numero])>1e-8:
            raise AssertionError(f'Caso {numero}: SNR entrada incorrecta')
        sin_filtrar=fila_metrica(numero,'Sin filtrar',s,r,x,x,s,r,0,0,0,fs,n_bloque)
        registros.append(sin_filtrar)

        def filtrar_temporal(z):return filtrar_por_bloques(z,sos,n_bloque,dtype=np.float64)[0]
        yt=filtrar_temporal(x)
        ys=filtrar_temporal(s)
        yr=filtrar_temporal(r)
        assert np.allclose(yt,ys+yr,rtol=0,atol=2e-12)
        nb_t=L//n_bloque
        tiempo_t,mini_t,maxi_t=tiempo_por_bloque(lambda: filtrar_temporal(x),nb_t,repeticiones)
        # Estimación de buffers de un microcontrolador con float64:
        # coeficientes + estados SOS + entrada/salida de N muestras.
        mem_t=int((sos.size+len(sos)*4+2*n_bloque)*8)
        registros.append(fila_metrica(numero,'Temporal',s,r,x,yt,ys,yr,
                       tiempo_t,mem_t,nb_t,fs,n_bloque,
                       {'umbral_espectral':'','tiempo_minimo_ms':mini_t,'tiempo_maximo_ms':maxi_t}))

        umbral=0.1 # IGUAL en los tres casos; 0.85 se reporta aparte solo como estrés.
        ye,det=reduccion_espectral_adaptativa(x,n_bloque,umbral,
                                               referencia=s,devolver_detalles=True)
        ys_e=det['referencia_con_mascara']
        yr_e=ye-ys_e
        nb_e=det['bloques_fft']
        tiempo_e,mini_e,maxi_e=tiempo_por_bloque(
               lambda: reduccion_espectral_adaptativa(x,n_bloque,umbral),nb_e,repeticiones)
        # Estimación conceptual del trabajo por bloque FFT float64:
        # 6 arreglos reales y 2 complejos, sin contar almacenamiento de
        # grabación completa, memoria Python ni buffers internos de FFT.
        mem_e=int(6*n_bloque*8 + 2*n_bloque*16)
        registros.append(fila_metrica(numero,'Espectral',s,r,x,ye,ys_e,yr_e,
                       tiempo_e,mem_e,nb_e,fs,n_bloque,
                       {'umbral_espectral':umbral,'tiempo_minimo_ms':mini_e,'tiempo_maximo_ms':maxi_e}))

        for metodo,y in [('temporal',yt),('espectral',ye)]:
            dest=carpeta/metodo/f'caso_{numero}'
            dest.mkdir(parents=True,exist_ok=True)
            np.save(dest/'filtrada.npy',y)
        trazas.append((numero,s,x,yt,ye,r,ys_e))

    assert len(registros)==9
    # Prueba adicional de distorsión en caso 3: mismo algoritmo con umbral 0.85.
    numero,s,x,yt,ye,r,ys_e=trazas[2]
    agresiva,det_agresiva=reduccion_espectral_adaptativa(x,n_bloque,0.85,
                                                          referencia=s,devolver_detalles=True)
    dic_compromiso=[]
    for nombre,y,filtrada in [('conservador_0.10',ye,ys_e),('agresivo_0.85',agresiva,det_agresiva['referencia_con_mascara'])]:
        dic_compromiso.append({'caso':3,'ajuste':nombre,
         'mse':mse(s,y),'snr_salida_db':snr(s,y),
         'energia_util_conservada_pct':100*potencia(filtrada)/potencia(s),
         'mse_senal_limpia_filtrada':mse(s,filtrada)})
    campos=list(registros[0].keys())
    for registro in registros:
        for campo in registro:
            if campo not in campos:campos.append(campo)
    with (carpeta/'metricas.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=campos); writer.writeheader()
        for d in registros:writer.writerow(d)
    with (carpeta/'espectral_compromiso.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=dic_compromiso[0]);writer.writeheader();writer.writerows(dic_compromiso)
    metadatos={
      'notas':['Se usan los mismos 3 archivos limpia.npy/ruido.npy/contaminada.npy de la sección 2.2',
        'MSE y SNR: señal limpia frente a salida causal SIN compensación de retardo ni reescalado',
        'Energía útil conservada: 100*E(referencia limpia procesada)/E(referencia limpia); en espectral se congela máscara estimada SOLO de contaminada',
        'Atenuación: 10log10(E(ruido inyectado)/E(ruido tratado con mismas ganancias)), medición offline con ruido conocido',
        'Tiempo por bloque: mediana del tiempo total de cada llamada, dividido por bloques; se excluyen disco, figuras, importaciones y diseño',
        'En temporal 16 bloques de 1024 (125 ms de adquisición); en espectral 33 ventanas de 1024 y salto 512 (62.5 ms entre saltos)',
        'Memoria aproximada: buffers ideales de bloque en float64; NO es perfil real ni memoria máxima de Python, FFT o ESP32',
        'Se corrigió cobertura y normalización OLA del código espectral, preservando la regla de decisión y el umbral 0.1 para comparación justa',
        'Umbral 0.85 sólo en prueba adicional de compromiso del caso 3; no se mezcla con la tabla principal',
        'La señal limpia se usa únicamente en evaluación offline; no participa en la detección de ruido'],
      'hardware_ejecucion':{'tipo':'PC / Python, no ESP32', 'plataforma':platform.platform(),
             'python':sys.version.split()[0],'numpy':np.__version__},
      'fs_hz':fs,'bloque_muestras':n_bloque,'salto_espectral':n_bloque//2,
      'repeticiones_benchmark':repeticiones,
      'memoria_estimacion_temporal':"(6SOS*6coef + 6SOS*4estados + 2*N_bloque) * 8 bytes",
      'memoria_estimacion_espectral':"6*N_bloque*8 + 2*N_bloque*16 bytes, ignorando buffers de grabación y overhead",
    }
    (carpeta/'metricas_metodologia.json').write_text(json.dumps(metadatos,indent=2,ensure_ascii=False),encoding='utf-8')
    if crear_figuras:
        figs=carpeta/'figuras';figs.mkdir(exist_ok=True)
        guardar_imagenes(trazas,figs)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(1,2,figsize=(10,4),layout='constrained')
        for et,y in [('Mezcla',x),('Umbral 0.10',ye),('Umbral 0.85',agresiva)]:
            axs[0].plot(np.arange(2500,2850)/fs*1000,y[2500:2850],label=et,alpha=.8)
        axs[0].plot(np.arange(2500,2850)/fs*1000,s[2500:2850],label='Referencia limpia',ls='--')
        axs[0].set(xlabel='Tiempo (ms)',ylabel='Amplitud',title='Caso 3: rechazo vs. distorsión')
        axs[0].legend(fontsize=7);axs[0].grid(alpha=.25)
        axs[1].bar(['0.10','0.85'],[v['energia_util_conservada_pct'] for v in dic_compromiso])
        axs[1].set(xlabel='Umbral relativo',ylabel='Energía útil conservada (%)',title='Efecto sobre señal limpia')
        axs[1].grid(axis='y',alpha=.25)
        fig.savefig(figs/'espectral_compromiso.png',dpi=155)
        plt.close(fig)
    return registros, dic_compromiso


if __name__=='__main__':
    registros,comparacion=generar_metricas()
    for r in registros:
        print(f"Caso {r['caso']} {r['metodo']:11s} SNR {r['snr_salida_db']:8.3f} dB, "
              f"ΔSNR {r['mejora_snr_db']:+8.3f} dB; MSE {r['mse']:.6g}; "
              f"energía útil {r['energia_util_conservada_pct']:.2f}%")
    print('Guardado: resultados/metricas.csv')
    print('Compromiso caso3:',comparacion)
