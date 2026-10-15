"""Filtro temporal IIR Butterworth reutilizable.

Requiere NumPy y SciPy. No depende de archivos del proyecto, Matplotlib,
pruebas ni del generador de senales; importar este modulo no ejecuta tareas.

Funciones:
- disenar_filtro(fs): obtiene los coeficientes segun ESPECIFICACIONES.
- caracterizar_filtro(diseno, tonos_hz): calcula propiedades y respuestas.
- filtrar_sos_propio(entrada, sos, estado): procesa muestras con ecuacion propia.
- filtrar_por_bloques(entrada, sos, n_bloque, estado): conserva la continuidad.

Ejemplo (entrada es un vector real muestreado a 8192 Hz):
    diseno = disenar_filtro(8192)
    salida, estado = filtrar_por_bloques(entrada, diseno["sos"], 1024)
    siguiente, estado = filtrar_por_bloques(otra_entrada, diseno["sos"], 1024, estado)

Usar estado=None al comenzar una grabacion independiente. La salida conserva
el retardo causal y el transitorio inicial. No normaliza ni recorta amplitudes.
Las especificaciones actuales son 1100/1600 Hz y 1/40 dB; deben corresponder
al problema y a la frecuencia de muestreo de la entrada.
"""
import numpy as np
import scipy
from scipy import signal

ESPECIFICACIONES = {
    "borde_paso_hz": 1100.0,
    "borde_rechazo_hz": 1600.0,
    "perdida_maxima_paso_db": 1.0,
    "atenuacion_minima_rechazo_db": 40.0,
}


def disenar_filtro(fs):
    """Calcula el orden minimo Butterworth y comprueba su magnitud.

    SOS sera la representacion de trabajo para reducir errores numericos.
    b/a se conserva para expresar H(z); el procesamiento utilizara SOS.
    Referencias: docs.scipy.org, scipy.signal.buttord y scipy.signal.butter.
    """
    e = ESPECIFICACIONES
    fp = e["borde_paso_hz"]
    fr = e["borde_rechazo_hz"]
    if not 0 < fp < fr < fs / 2:
        raise ValueError("Se requiere 0 < borde de paso < rechazo < Nyquist.")

    orden, corte = signal.buttord(
        fp, fr, e["perdida_maxima_paso_db"],
        e["atenuacion_minima_rechazo_db"], fs=fs,
    )
    sos = signal.butter(orden, corte, btype="lowpass", fs=fs, output="sos")
    b, a = signal.butter(orden, corte, btype="lowpass", fs=fs, output="ba")

    # Incluimos ambos bordes exactamente en la malla de comprobacion.
    frecuencias = np.unique(np.r_[np.linspace(0, fs / 2, 32769), fp, fr])
    _, h = signal.sosfreqz(sos, worN=frecuencias, fs=fs)
    db = 20 * np.log10(np.maximum(np.abs(h), np.finfo(float).tiny))
    paso = db[frecuencias <= fp]
    rechazo = db[frecuencias >= fr]
    perdida = float(-paso.min())
    atenuacion = float(-rechazo.max())
    tolerancia_db = 1e-8
    if (perdida > e["perdida_maxima_paso_db"] + tolerancia_db
            or paso.max() > tolerancia_db
            or atenuacion < e["atenuacion_minima_rechazo_db"] - tolerancia_db):
        raise ValueError("El diseno no cumple las especificaciones de magnitud.")

    return {
        "familia": "Butterworth", "tipo": "IIR pasa bajas",
        "fs_hz": fs,
        "especificaciones": dict(e), "orden": int(orden),
        "frecuencia_corte_hz": float(corte),
        "nota_corte": "Magnitud 1/sqrt(2), aproximadamente -3.0103 dB",
        "representacion_procesamiento": "sos",
        "columnas_sos": ["b0", "b1", "b2", "a0", "a1", "a2"],
        "sos": sos.tolist(), "b": b.tolist(), "a": a.tolist(),
        "verificacion_magnitud": {
            "puntos_malla": len(frecuencias),
            "perdida_maxima_paso_db": perdida,
            "atenuacion_minima_rechazo_db": atenuacion,
            "tolerancia_db": tolerancia_db,
        },
        "versiones": {"numpy": np.__version__, "scipy": scipy.__version__},
    }


def retardo_grupo_sos(sos, frecuencias, fs):
    """Suma los retardos de las secciones en cascada, en muestras.

    D(w) = -d arg(H(exp(jw)))/dw. Se evalua por seccion para evitar
    polinomios de orden alto. No evaluar en Nyquist: H tiene ceros alli.
    Referencia: scipy.signal.group_delay.
    """
    retardo = np.zeros_like(frecuencias, dtype=float)
    for fila in sos:
        _, parcial = signal.group_delay((fila[:3], fila[3:]),
                                        w=frecuencias, fs=fs)
        retardo += parcial
    return retardo


def caracterizar_filtro(diseno, tonos_hz=()):
    """Calcula H(z), ROC causal, estabilidad y respuestas del filtro.

    H(z) = producto_i (b0_i+b1_i*z^-1+b2_i*z^-2) /
                         (a0_i+a1_i*z^-1+a2_i*z^-2).
    Para este IIR causal, la ROC es |z| > max(|polos|). Es BIBO
    estable si todos los polos estan estrictamente dentro del circulo unidad.
    """
    fs = diseno["fs_hz"]
    sos = np.asarray(diseno["sos"])
    ceros, polos, ganancia = signal.sos2zpk(sos)
    radio = float(np.max(np.abs(polos)))
    estable = bool(radio < 1)
    if not estable:
        raise ValueError("El filtro causal tiene polos fuera del circulo unidad.")

    f = np.linspace(0, fs / 2, 16385)
    _, h = signal.sosfreqz(sos, worN=f, fs=fs)
    magnitud_db = 20 * np.log10(np.maximum(np.abs(h), np.finfo(float).tiny))
    # La fase y su derivada carecen de utilidad donde la respuesta es casi nula.
    # Se limita su visualizacion a magnitudes superiores a -120 dB; Nyquist
    # se excluye explicitamente, pues los ceros en z=-1 anulan H alli.
    validos = (magnitud_db > -120) & (f < fs / 2)
    fase = np.full(f.shape, np.nan)
    retardo = np.full(f.shape, np.nan)
    fase[validos] = np.unwrap(np.angle(h[validos]))
    retardo[validos] = retardo_grupo_sos(sos, f[validos], fs)
    if not np.all(np.isfinite(retardo[validos])):
        raise ValueError("Retardo no finito en la region de analisis.")

    tonos = np.asarray(tonos_hz, dtype=float)
    _, ht = signal.sosfreqz(sos, worN=tonos, fs=fs)
    dt = retardo_grupo_sos(sos, tonos, fs)
    resumen = {
        "ceros": [[float(z.real), float(z.imag)] for z in ceros],
        "polos": [[float(p.real), float(p.imag)] for p in polos],
        "formato_complejos": "[parte real, parte imaginaria]",
        "ganancia_zpk": float(ganancia),
        "radio_polar_maximo": radio,
        "margen_radio_unidad": 1 - radio,
        "roc_causal": f"|z| > {radio:.12g}",
        "estable_bibo": estable,
        "tonos_utiles": [
            {"frecuencia_hz": float(ft), "magnitud_db": float(20*np.log10(abs(hv))),
             "retardo_grupo_muestras": float(d), "retardo_grupo_ms": float(1000*d/fs)}
            for ft, hv, d in zip(tonos, ht, dt)
        ],
        "umbral_visualizacion_fase_retardo_db": -120,
    }
    return resumen, {
        "frecuencias_hz": f, "magnitud_db": magnitud_db,
        "fase_rad": fase, "retardo_muestras": retardo, "validos": validos,
    }

def filtrar_sos_propio(entrada, sos, estado=None, *, dtype=np.float64):
    """Filtra un vector real mediante secciones SOS en forma directa I.

    Cada fila SOS es [b0, b1, b2, a0, a1, a2]. Para cada seccion:
      y[n] = (b0*x[n] + b1*x[n-1] + b2*x[n-2]
              - a1*y[n-1] - a2*y[n-2]) / a0.
    La salida de una seccion es la entrada de la siguiente.

    estado tiene forma (numero_secciones, 4), con columnas
    [x[n-1], x[n-2], y[n-1], y[n-2]] para cada seccion.
    None indica reposo inicial. Devuelve (salida, estado_final) sin modificar
    los argumentos. Para continuar otra porcion de la MISMA senal, pasar
    estado_final a la siguiente llamada. No es el estado de scipy.sosfilt,
    que utiliza una estructura interna diferente.

    dtype admite np.float64 (referencia) o np.float32 (precision reducida).
    Coeficientes, muestras, operaciones y estados usan la precision elegida.
    Conservar el mismo dtype al reanudar una grabacion. No simula instrucciones
    fusionadas ni todos los detalles de un compilador de microcontrolador.
    """
    dtype = np.dtype(dtype)
    if dtype not in (np.dtype(np.float32), np.dtype(np.float64)):
        raise ValueError("dtype debe ser float32 o float64.")
    if np.iscomplexobj(entrada) or np.iscomplexobj(sos) or np.iscomplexobj(estado):
        raise ValueError("Se esperan muestras, coeficientes y estados reales.")
    x = np.asarray(entrada, dtype=dtype)
    coef = np.asarray(sos, dtype=dtype)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("La entrada debe ser un vector finito.")
    if (coef.ndim != 2 or coef.shape[1] != 6 or len(coef) == 0
            or not np.all(np.isfinite(coef)) or np.any(coef[:, 3] == 0)):
        raise ValueError("SOS debe tener seis columnas finitas y a0 distinto de cero.")
    # Normalizar una vez evita dividir por a0 dentro del bucle de muestras.
    coef = coef / coef[:, 3:4]
    if estado is None:
        memoria = np.zeros((len(coef), 4), dtype=dtype)
    else:
        memoria = np.array(estado, dtype=dtype, copy=True)
        if memoria.shape != (len(coef), 4) or not np.all(np.isfinite(memoria)):
            raise ValueError("Estado incompatible con las secciones SOS.")

    salida = np.empty_like(x)
    for n, muestra in enumerate(x):
        valor = muestra
        for i, (b0, b1, b2, _, a1, a2) in enumerate(coef):
            x1, x2, y1, y2 = memoria[i]
            y = b0*valor + b1*x1 + b2*x2 - a1*y1 - a2*y2
            memoria[i] = (valor, x1, y, y1)
            valor = y
        salida[n] = valor
    if not np.all(np.isfinite(salida)) or not np.all(np.isfinite(memoria)):
        raise FloatingPointError("El filtrado produjo valores no finitos.")
    return salida, memoria


def filtrar_por_bloques(entrada, sos, n_bloque, estado=None, *, dtype=np.float64):
    """Procesa bloques consecutivos conservando la memoria del filtro.

    El ultimo bloque puede ser mas corto: no se rellena ni se recorta la
    senal. Se conservan retardo causal y transitorio inicial; no se aplica
    ventana, normalizacion de amplitud ni filtrado hacia atras.
    """
    if not isinstance(n_bloque, (int, np.integer)) or n_bloque <= 0:
        raise ValueError("El tamano de bloque debe ser un entero positivo.")
    x = np.asarray(entrada)
    if x.ndim != 1:
        raise ValueError("La entrada debe ser un vector.")
    # Validar coeficientes/estado aun para una entrada vacia.
    _, memoria = filtrar_sos_propio(x[:0], sos, estado, dtype=dtype)
    salida = np.empty(len(x), dtype=dtype)
    for inicio in range(0, len(x), n_bloque):
        fin = min(inicio + n_bloque, len(x))
        salida[inicio:fin], memoria = filtrar_sos_propio(x[inicio:fin], sos, memoria, dtype=dtype)
    return salida, memoria

