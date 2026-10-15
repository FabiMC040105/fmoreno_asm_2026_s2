"""Reducción adaptativa espectral FFT/IFFT con OLA normalizado.

Adaptación trazable del módulo aportado por la persona 4.
Se mantiene su regla espectral: cada magnitud inferior al umbral relativo
al máximo del bloque se atenúa 10 veces (ganancia 0.1); las otras se conservan.

Correcciones de integración verificables:
- Se cubren todos los bloques, incluido el último.
- Se añade un margen de N/2 muestras a ambos lados para cubrir bordes.
- Se divide por la suma de ventanas superpuestas, evitando pérdida de amplitud.
- Se usa rFFT/irFFT: simetría hermítica y reconstrucción real garantizadas.
- La referencia limpia OPCIONAL se procesa con la misma máscara ya aprendida
  de la mezcla SOLO para estimar preservación de señal en pruebas offline.

El archivo filtrado_espectral_original.py guarda el original sin modificar.
"""
from __future__ import annotations
import numpy as np


def reduccion_espectral_adaptativa(signal, block_size=1024, umbral_energia=0.1,
                                   referencia=None, devolver_detalles=False):
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or len(x) == 0 or not np.all(np.isfinite(x)):
        raise ValueError('La entrada debe ser una señal real 1D finita no vacía')
    if block_size < 4 or block_size & (block_size - 1):
        raise ValueError('El tamaño de bloque debe ser potencia de dos y >= 4')
    if not 0 <= umbral_energia <= 1:
        raise ValueError('El umbral relativo debe estar entre 0 y 1')
    if referencia is not None:
        s = np.asarray(referencia, dtype=np.float64)
        if s.shape != x.shape or not np.all(np.isfinite(s)):
            raise ValueError('La referencia debe tener forma idéntica y datos finitos')
    else:
        s = None

    salto = block_size//2
    # Hann periódica: con salto N/2 se obtiene exactamente COLA en el interior.
    ventana = np.hanning(block_size + 1)[:-1]
    # N/2 muestras de protección en cada extremo, evitando bordes de peso nulo.
    x_pad = np.pad(x, (salto,salto))
    s_pad = np.pad(s, (salto,salto)) if s is not None else None
    # Permite registros de longitud arbitraria.
    sobrante = (-(len(x_pad)-block_size)) % salto
    if sobrante:
        x_pad=np.pad(x_pad,(0,sobrante))
        if s_pad is not None:s_pad=np.pad(s_pad,(0,sobrante))
    salida = np.zeros_like(x_pad)
    suma_ventanas = np.zeros_like(x_pad)
    salida_referencia = np.zeros_like(x_pad) if s is not None else None
    cuenta=0

    for i in range(0, len(x_pad)-block_size+1, salto):
        bloque = x_pad[i:i+block_size]*ventana
        espectro = np.fft.rfft(bloque)
        magnitud = np.abs(espectro)
        umbral = float(np.max(magnitud))*umbral_energia
        ganancia = np.where(magnitud < umbral, 0.1, 1.0)
        # Al trabajar solo con los bins únicos de rFFT, una ganancia real
        # preserva automáticamente la simetría requerida por irFFT.
        filtrado = np.fft.irfft(espectro * ganancia, n=block_size)
        salida[i:i+block_size] += filtrado
        suma_ventanas[i:i+block_size] += ventana
        if s_pad is not None:
            s_fft = np.fft.rfft(s_pad[i:i+block_size]*ventana)
            salida_referencia[i:i+block_size] += np.fft.irfft(s_fft*ganancia, n=block_size)
        cuenta += 1

    rebanada = slice(salto,salto+len(x))
    pesos = suma_ventanas[rebanada]
    if np.any(pesos <= 0):
        raise AssertionError('Ventanas no cubren todos los puntos de salida')
    y=salida[rebanada]/pesos
    if not np.all(np.isfinite(y)):
        raise FloatingPointError('Salida espectral no finita')
    if not devolver_detalles:
        return y
    detalles = dict(bloques_fft=cuenta, salto_muestras=salto,
                    solapamiento_porcentaje=50,
                    umbral_relativo=float(umbral_energia),
                    ganancias_baja_magnitud=0.1,
                    correccion='Hann periódica, márgenes, OLA normalizado')
    if salida_referencia is not None:
        detalles['referencia_con_mascara']=salida_referencia[rebanada]/pesos
    return y, detalles


if __name__=='__main__':
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1]
    for caso in range(1,4):
        mezcla=np.load(ruta/'pruebas'/f'caso_{caso}'/'contaminada.npy')
        y,info=reduccion_espectral_adaptativa(mezcla,1024,0.1, devolver_detalles=True)
        dest=ruta/'resultados'/'espectral'/f'caso_{caso}'
        dest.mkdir(parents=True,exist_ok=True)
        np.save(dest/'filtrada.npy',y)
        print(f'Caso {caso}: {len(y)} muestras, {info["bloques_fft"]} bloques FFT')
