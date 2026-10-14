"""Tarea 1, apartado 2.3: carga de entradas y diseno Butterworth.

Conserva los datos del 2.2. Guarda el diseno en metadatos/filtro_temporal.json.
Todavia no aplica el filtro a las senales.
"""

import json
from pathlib import Path

import numpy as np
import scipy
from scipy import signal


RAIZ = Path(__file__).resolve().parents[1]

# Objetivos referidos a ganancia unitaria.
ESPECIFICACIONES = {
    "borde_paso_hz": 1100.0,
    "borde_rechazo_hz": 1600.0,
    "perdida_maxima_paso_db": 1.0,
    "atenuacion_minima_rechazo_db": 40.0,
}


def cargar_entradas(raiz=RAIZ):
    """Devuelve la configuracion y los tres casos con sus arrays NPY."""
    raiz = Path(raiz)
    ruta_config = raiz / "metadatos" / "configuraciones.json"
    with ruta_config.open(encoding="utf-8") as archivo:
        config = json.load(archivo)

    fs = config["fs_hz"]
    n_bloque = config["n_bloque"]
    n_total = config["n_total"]
    if fs <= 0 or n_total <= 0 or n_bloque <= 0:
        raise ValueError("Frecuencia y longitudes deben ser positivas.")
    if n_bloque & (n_bloque - 1):
        raise ValueError("El bloque configurado no es potencia de dos.")
    if not np.isclose(n_total / fs, config["duracion_s"]):
        raise ValueError("La duracion no coincide con n_total / fs.")
    if sorted(c["id"] for c in config["condiciones"]) != [1, 2, 3]:
        raise ValueError("Se esperan exactamente los casos 1, 2 y 3.")

    casos = {}
    for condicion in config["condiciones"]:
        numero = condicion["id"]
        for campo in ("fs_hz", "n_bloque", "n_total", "duracion_s"):
            if condicion[campo] != config[campo]:
                raise ValueError(f"Caso {numero}: {campo} difiere de la configuracion general.")

        datos = {}
        for nombre in ("limpia", "ruido", "contaminada"):
            # El JSON apunta a WAV; el NPY de referencia tiene el mismo nombre.
            ruta = (raiz / condicion["rutas"][nombre]).with_suffix(".npy")
            senal = np.load(ruta, allow_pickle=False)
            if senal.ndim != 1 or senal.size != n_total:
                raise ValueError(f"Caso {numero}, {nombre}: longitud o forma incorrecta.")
            if senal.dtype.kind not in "fiu" or not np.all(np.isfinite(senal)):
                raise ValueError(f"Caso {numero}, {nombre}: muestras invalidas.")
            datos[nombre] = senal.astype(np.float64, copy=False)

        limpia = datos["limpia"]
        ruido = datos["ruido"]
        contaminada = datos["contaminada"]
        if not np.allclose(limpia + ruido, contaminada, atol=1e-12, rtol=0):
            raise ValueError(f"Caso {numero}: la mezcla no coincide con limpia + ruido.")

        energia_util = np.sum(limpia ** 2)
        energia_error = np.sum((contaminada - limpia) ** 2)
        if energia_util <= 0 or energia_error <= 0:
            raise ValueError(f"Caso {numero}: energia insuficiente para verificar SNR.")
        snr = float(10 * np.log10(energia_util / energia_error))
        if abs(snr - condicion["snr_objetivo_db"]) > 1e-9:
            raise ValueError(f"Caso {numero}: SNR distinta de la configurada.")

        casos[numero] = {**datos, "snr_entrada_db": snr}

    return config, casos


def disenar_filtro(fs):
    """Calcula el orden minimo Butterworth y comprueba su magnitud.

    SOS sera la representacion de trabajo para reducir errores numericos.
    b/a se conserva para expresar H(z); no se usa para filtrar en este paso.
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
        "caso_diseno": 1, "fs_hz": fs,
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


def guardar_diseno(diseno, raiz=RAIZ):
    """Guarda parametros y coeficientes sin alterar configuraciones.json."""
    destino = Path(raiz) / "metadatos" / "filtro_temporal.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(diseno, indent=2, ensure_ascii=False,
                                 allow_nan=False) + "\n", encoding="utf-8")
    return destino


def main():
    config, casos = cargar_entradas()
    fs = config["fs_hz"]
    bloque = config["n_bloque"]
    print(f"Frecuencia de muestreo: {fs} Hz")
    print(f"Longitud por senal: {config['n_total']} muestras")
    print(f"Duracion: {config['duracion_s']:.3f} s")
    print(f"Bloque: {bloque} muestras ({1000 * bloque / fs:.3f} ms)")
    print(f"Separacion entre bins: {fs / bloque:.3f} Hz")
    for numero, datos in sorted(casos.items()):
        print(f"Caso {numero}: entradas OK | SNR = {datos['snr_entrada_db']:.6f} dB")
    print("Paso 1 completado: entradas listas para disenar el filtro temporal.")
    diseno = disenar_filtro(fs)
    ruta = guardar_diseno(diseno)
    v = diseno["verificacion_magnitud"]
    print(f"\nFiltro: {diseno['tipo']} Butterworth")
    print(f"Orden: {diseno['orden']}")
    print(f"Frecuencia de corte: {diseno['frecuencia_corte_hz']:.6f} Hz")
    print(f"Secciones SOS: {len(diseno['sos'])}")
    print(f"Perdida maxima en paso: {v['perdida_maxima_paso_db']:.6f} dB")
    print(f"Atenuacion minima en rechazo: {v['atenuacion_minima_rechazo_db']:.6f} dB")
    print("Coeficientes SOS [b0, b1, b2, a0, a1, a2]:")
    print(np.array2string(np.array(diseno['sos']), precision=10))
    print(f"Diseno guardado en: {ruta}")
    print("Diseno verificado; filtrado pendiente.")


if __name__ == "__main__":
    main()
