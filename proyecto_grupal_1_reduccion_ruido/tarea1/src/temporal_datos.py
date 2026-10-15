"""Carga y valida las entradas reproducibles del apartado 2.2."""
import json
from pathlib import Path
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]

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
