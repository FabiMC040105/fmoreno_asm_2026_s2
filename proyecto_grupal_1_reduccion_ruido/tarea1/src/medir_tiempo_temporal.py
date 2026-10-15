"""Mide el nucleo propio por bloque en PC; no estima el tiempo del ESP32.

Desde la raiz del repositorio: python medir_tiempo_temporal.py
--raiz permite indicar otra carpeta tarea1. Excluye E/S, diseno y figuras.
"""
import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter_ns
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raiz', type=Path, default=Path('proyecto_grupal_1_reduccion_ruido/tarea1'))
    p.add_argument('--repeticiones', type=int, default=10)
    args = p.parse_args()
    if args.repeticiones < 1:
        p.error('repeticiones debe ser positivo')
    sys.path.insert(0, str(args.raiz.resolve()/'src'))
    from temporal_datos import cargar_entradas
    from filtros_temporales import disenar_filtro, filtrar_sos_propio
    config, casos = cargar_entradas(args.raiz)
    sos = np.asarray(disenar_filtro(config['fs_hz'])['sos'])
    n = config['n_bloque']
    filas = []
    for dtype in (np.float64, np.float32):
        coef = sos.astype(dtype)
        for numero, caso in casos.items():
            x = caso['contaminada'].astype(dtype)
            filtrar_sos_propio(x[:n], coef, dtype=dtype)  # Calentamiento fuera de medida.
            duraciones = []
            for _ in range(args.repeticiones):
                estado = None
                for inicio in range(0, len(x), n):
                    bloque = x[inicio:inicio+n]
                    t0 = perf_counter_ns()
                    _, estado = filtrar_sos_propio(bloque, coef, estado, dtype=dtype)
                    duraciones.append((perf_counter_ns()-t0)/1e6)
            filas.append(dict(caso=numero, precision=np.dtype(dtype).name,
                              bloques_medidos=len(duraciones),
                              media_ms=float(np.mean(duraciones)),
                              mediana_ms=float(np.median(duraciones)),
                              p95_ms=float(np.percentile(duraciones,95)),
                              maximo_ms=float(np.max(duraciones))))
    r = dict(entorno='PC; no medido en ESP32',sistema=platform.system(),
             arquitectura=platform.machine(), procesador=platform.processor(),
             python=platform.python_version(), numpy=np.__version__,
             fs_hz=config['fs_hz'], bloque_muestras=n, repeticiones=args.repeticiones,
             incluye='Validacion, normalizacion SOS, asignacion y bucle propio; sin E/S ni figuras',
             tiempo_adquisicion_ms=1000*n/config['fs_hz'], resultados=filas)
    destino=args.raiz/'resultados/hardware_temporal/tiempos_pc.json'
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
    for fila in filas:
        print(f"Caso {fila['caso']} {fila['precision']}: mediana {fila['mediana_ms']:.3f} ms; p95 {fila['p95_ms']:.3f} ms")
    print(destino)


if __name__ == '__main__':
    main()
