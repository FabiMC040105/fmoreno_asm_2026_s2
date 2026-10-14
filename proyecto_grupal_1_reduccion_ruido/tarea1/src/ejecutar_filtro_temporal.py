"""Ejecuta el experimento y exporta las salidas del filtro temporal.

Desde la raiz del repositorio:
python proyecto_grupal_1_reduccion_ruido/tarea1/src/ejecutar_filtro_temporal.py
Agregar --pruebas para ejecutar solamente la suite de validacion.
"""
import argparse
import csv
import json
import unittest
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from temporal_datos import cargar_entradas
from filtros_temporales import disenar_filtro, caracterizar_filtro, filtrar_por_bloques

RAIZ = Path(__file__).resolve().parents[1]


def exportar_caracterizacion(diseno, resumen, respuesta, raiz=RAIZ):
    """Guarda H(z), CSV y figuras a partir de resultados ya calculados."""
    raiz = Path(raiz)
    fs = diseno["fs_hz"]
    sos = np.asarray(diseno["sos"])
    ceros = np.array([complex(*z) for z in resumen["ceros"]])
    polos = np.array([complex(*p) for p in resumen["polos"]])
    radio = resumen["radio_polar_maximo"]
    estable = resumen["estable_bibo"]
    f = respuesta["frecuencias_hz"]
    magnitud_db = respuesta["magnitud_db"]
    fase = respuesta["fase_rad"]
    retardo = respuesta["retardo_muestras"]
    validos = respuesta["validos"]
    resultados = raiz / "resultados"
    figuras = resultados / "figuras"
    figuras.mkdir(parents=True, exist_ok=True)
    # El TXT muestra la forma global y la cascada; el JSON conserva los
    # coeficientes con precision completa para cualquier calculo posterior.
    def polinomio(coef):
        return " ".join(f"{v:+.12g}" + (f"*z^-{i}" if i else "")
                        for i, v in enumerate(coef))

    texto = ["FUNCION DE TRANSFERENCIA DEL FILTRO TEMPORAL",
             "H(z) = B(z) / A(z)",
             "B(z) = " + polinomio(diseno["b"]),
             "A(z) = " + polinomio(diseno["a"]),
             "", "Forma en cascada: H(z) = H1(z) * ... * H6(z)"]
    for i, fila in enumerate(sos, 1):
        texto.append(f"H{i}(z) = ({polinomio(fila[:3])}) / ({polinomio(fila[3:])})")
    texto += ["", f"ROC causal: {resumen['roc_causal']}",
              f"Maximo modulo de polos: {radio:.12g}",
              f"Estable BIBO: {estable}",
              "La ROC incluye el circulo unidad.",
              "Coeficientes completos: metadatos/filtro_temporal.json"]
    (resultados / "temporal_transferencia.txt").write_text("\n".join(texto)+"\n", encoding="utf-8")
    with (resultados / "temporal_respuesta.csv").open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["frecuencia_hz", "magnitud_db", "fase_rad",
                            "retardo_muestras", "retardo_ms"])
        for i, frecuencia in enumerate(f):
            # Campos vacios indican fase/retardo omitidos, nunca retardo cero.
            escritor.writerow([frecuencia, magnitud_db[i],
                               fase[i] if validos[i] else "",
                               retardo[i] if validos[i] else "",
                               1000*retardo[i]/fs if validos[i] else ""])

    fig, ax = plt.subplots(figsize=(7, 7), layout="constrained")
    angulo = np.linspace(0, 2*np.pi, 500)
    ax.plot(np.cos(angulo), np.sin(angulo), "--", color="gray", label="Círculo unidad")
    ax.scatter(polos.real, polos.imag, marker="x", s=65, color="tab:red", label="Polos")
    ax.scatter(ceros.real, ceros.imag, facecolors="none", edgecolors="tab:blue", s=90, label="Ceros")
    ax.annotate("12 ceros en z = −1", (-1, 0), xytext=(-1.2, .3),
                arrowprops={"arrowstyle": "->"})
    ax.set(xlabel="Parte real", ylabel="Parte imaginaria", xlim=(-1.35, 1.35),
           ylim=(-1.25, 1.25), title=f"Polos y ceros — Butterworth de orden {diseno['orden']}\n"
           f"Máximo |p| = {radio:.6f} < 1: estable")
    ax.set_aspect("equal")
    ax.axhline(0, color="gray", lw=.6)
    ax.axvline(0, color="gray", lw=.6)
    ax.grid(alpha=.25)
    ax.legend(loc="lower left")
    fig.savefig(figuras / "temporal_polos_ceros.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True, layout="constrained")
    e = diseno["especificaciones"]
    axes[0].plot(f, magnitud_db)
    axes[0].axhline(-e["perdida_maxima_paso_db"], color="tab:green", ls=":", label="Límite de paso: −1 dB")
    axes[0].axhline(-e["atenuacion_minima_rechazo_db"], color="tab:red", ls=":", label="Límite de rechazo: −40 dB")
    axes[0].set(ylabel="Magnitud (dB)", ylim=(-120, 5))
    axes[0].legend(loc="upper right")
    axes[1].plot(f, fase)
    axes[1].set_ylabel("Fase desenvuelta (rad)")
    axes[2].plot(f, retardo)
    axes[2].set(ylabel="Retardo de grupo (muestras)", xlabel="Frecuencia (Hz)")
    sec = axes[2].secondary_yaxis("right", functions=(lambda x: x*1000/fs, lambda x: x*fs/1000))
    sec.set_ylabel("Retardo de grupo (ms)")
    for ax in axes:
        ax.axvline(e["borde_paso_hz"], color="tab:green", ls="--", alpha=.6)
        ax.axvline(e["borde_rechazo_hz"], color="tab:red", ls="--", alpha=.6)
        ax.set_xlim(0, fs/2)
        ax.grid(alpha=.25)
    fig.suptitle("Respuesta del filtro temporal\n"
                 "Fase y retardo mostrados solo para |H| > −120 dB; Nyquist excluido")
    fig.savefig(figuras / "temporal_respuesta.png", dpi=160)
    plt.close(fig)
    return resumen


def guardar_diseno(diseno, raiz=RAIZ):
    """Guarda parametros y coeficientes sin alterar configuraciones.json."""
    destino = Path(raiz) / "metadatos" / "filtro_temporal.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(diseno, indent=2, ensure_ascii=False,
                                 allow_nan=False) + "\n", encoding="utf-8")
    return destino


def procesar_casos(casos, diseno, n_bloque, raiz=RAIZ):
    """Filtra cada mezcla desde reposo y guarda salida y estado final.

    La referencia limpia no participa en el filtrado. Los archivos se
    guardan en resultados/temporal/caso_i/ para conservar las entradas.
    """
    for numero, datos in sorted(casos.items()):
        # Cada caso es una grabacion independiente: comienza desde reposo.
        salida, estado = filtrar_por_bloques(
            datos["contaminada"], diseno["sos"], n_bloque)
        destino = Path(raiz) / "resultados" / "temporal" / f"caso_{numero}"
        destino.mkdir(parents=True, exist_ok=True)
        np.save(destino / "filtrada.npy", salida)
        np.save(destino / "estado_final.npy", estado)
        print(f"Caso {numero}: {len(salida)} muestras filtradas | "
              f"pico de salida = {np.max(np.abs(salida)):.6f}")


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
    print("Entradas verificadas.")
    diseno = disenar_filtro(fs)
    caracterizacion, respuesta = caracterizar_filtro(diseno, config["frecuencias_utiles_hz"])
    diseno["caso_diseno"] = 1
    diseno["caracterizacion"] = caracterizacion
    exportar_caracterizacion(diseno, caracterizacion, respuesta)
    diseno["implementacion"] = {
        "estructura": "Cascada SOS, forma directa I propia",
        "precision": "float64",
        "n_bloque": bloque,
        "estado_por_seccion": ["x_anterior", "x_dos_atras", "y_anterior", "y_dos_atras"],
        "inicio": "Reposo al comenzar cada caso; continuidad entre bloques",
        "alineacion": "Salida causal, sin compensar retardo ni retirar transitorio",
    }
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
    print(f"Maximo modulo de polos: {caracterizacion['radio_polar_maximo']:.9f}")
    print(f"ROC causal: {caracterizacion['roc_causal']}")
    print(f"Estable BIBO: {caracterizacion['estable_bibo']}")
    for tono in caracterizacion["tonos_utiles"]:
        print(f"Tono {tono['frecuencia_hz']:.0f} Hz: retardo de grupo "
              f"{tono['retardo_grupo_muestras']:.4f} muestras "
              f"({tono['retardo_grupo_ms']:.4f} ms)")
    print("H(z), tabla de respuesta y figuras guardadas en resultados/.")
    procesar_casos(casos, diseno, bloque)
    print("Diseno, caracterizacion y filtrado completados.")


def ejecutar_pruebas():
    """Conserva el comando --pruebas y carga la suite desde pruebas/."""
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(RAIZ / "pruebas"), pattern="test_filtros_temporales.py")
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diseno y filtrado temporal de los tres casos.")
    parser.add_argument("--pruebas", action="store_true",
                        help="Ejecutar pruebas sin generar salidas ni figuras.")
    argumentos = parser.parse_args()
    if argumentos.pruebas:
        raise SystemExit(ejecutar_pruebas())
    main()
