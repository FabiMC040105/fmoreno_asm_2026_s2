"""Tarea 1, apartado 2.3: diseno, caracterizacion y filtrado Butterworth.

Colocar en tarea1/src/. Ejecutar: python src/filtros_temporales.py
Pruebas automaticas: python src/filtros_temporales.py --pruebas
Conserva los datos del 2.2. Guarda el diseno en metadatos/filtro_temporal.json.
Aplica una ecuacion de diferencias propia por bloques y guarda salidas NPY.
"""

import argparse
import csv
import json
import unittest
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
import matplotlib
matplotlib.use("Agg")  # Guarda figuras sin requerir una ventana grafica.
import matplotlib.pyplot as plt


RAIZ = Path(__file__).resolve().parents[1]

# Especificaciones de magnitud referidas a ganancia unitaria.
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


def caracterizar_filtro(diseno, tonos_hz, raiz=RAIZ):
    """Calcula H(z), ROC causal, estabilidad y respuestas del filtro.

    H(z) = producto_i (b0_i+b1_i*z^-1+b2_i*z^-2) /
                         (a0_i+a1_i*z^-1+a2_i*z^-2).
    Para este IIR causal, la ROC es |z| > max(|polos|). Es BIBO
    estable si todos los polos estan estrictamente dentro del circulo unidad.
    """
    raiz = Path(raiz)
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
    diseno["caracterizacion"] = resumen

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


def filtrar_sos_propio(entrada, sos, estado=None):
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
    """
    if np.iscomplexobj(entrada) or np.iscomplexobj(sos) or np.iscomplexobj(estado):
        raise ValueError("Se esperan muestras, coeficientes y estados reales.")
    x = np.asarray(entrada, dtype=np.float64)
    coef = np.asarray(sos, dtype=np.float64)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("La entrada debe ser un vector finito.")
    if (coef.ndim != 2 or coef.shape[1] != 6 or len(coef) == 0
            or not np.all(np.isfinite(coef)) or np.any(coef[:, 3] == 0)):
        raise ValueError("SOS debe tener seis columnas finitas y a0 distinto de cero.")
    # Normalizar una vez evita dividir por a0 dentro del bucle de muestras.
    coef = coef / coef[:, 3:4]
    if estado is None:
        memoria = np.zeros((len(coef), 4), dtype=np.float64)
    else:
        memoria = np.array(estado, dtype=np.float64, copy=True)
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


def filtrar_por_bloques(entrada, sos, n_bloque, estado=None):
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
    _, memoria = filtrar_sos_propio(x[:0], sos, estado)
    salida = np.empty(len(x), dtype=np.float64)
    for inicio in range(0, len(x), n_bloque):
        fin = min(inicio + n_bloque, len(x))
        salida[inicio:fin], memoria = filtrar_sos_propio(x[inicio:fin], sos, memoria)
    return salida, memoria


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


class TestFiltroTemporal(unittest.TestCase):
    """Verifica la ecuacion propia y su continuidad, sin generar archivos.

    La referencia es scipy.signal.sosfilt con reposo inicial. Se comparan
    salidas, no estados internos: SciPy usa forma directa II transpuesta
    y nuestra implementacion forma directa I.
    Tolerancia absoluta: 1e-12; relativa: 0. Es una prueba numerica de
    implementacion en float64, no una medida de reduccion de ruido.
    """

    ATOL = 1e-12

    @classmethod
    def setUpClass(cls):
        cls.config, cls.casos = cargar_entradas()
        cls.sos = np.asarray(disenar_filtro(cls.config["fs_hz"])["sos"])

    def test_tres_casos_contra_scipy(self):
        """Contrasta las tres mezclas completas con una referencia externa."""
        for numero, datos in sorted(self.casos.items()):
            with self.subTest(caso=numero):
                x = datos["contaminada"]
                salida, _ = filtrar_por_bloques(x, self.sos, self.config["n_bloque"])
                referencia = signal.sosfilt(self.sos, x)
                np.testing.assert_allclose(salida, referencia, atol=self.ATOL, rtol=0)
                error = float(np.max(np.abs(salida - referencia)))
                print(f"Caso {numero}: error maximo contra SciPy = {error:.3e}")

    def test_impulso_y_escalon_contra_scipy(self):
        """Comprueba arranque y transitorios con entradas deterministas."""
        impulso = np.zeros(2048)
        impulso[0] = 1
        for nombre, x in (("impulso", impulso), ("escalon", np.ones(2048))):
            with self.subTest(entrada=nombre):
                salida, _ = filtrar_sos_propio(x, self.sos)
                np.testing.assert_allclose(salida, signal.sosfilt(self.sos, x),
                                           atol=self.ATOL, rtol=0)

    def test_bloques_equivalentes_a_senal_completa(self):
        """Incluye bloques unitarios y una longitud que no divide la senal."""
        x = np.random.default_rng(20261014).standard_normal(2051)
        completa, estado_completo = filtrar_sos_propio(x, self.sos)
        for longitud in (1, 73, 1024, len(x) + 1):
            with self.subTest(n_bloque=longitud):
                salida, estado = filtrar_por_bloques(x, self.sos, longitud)
                self.assertEqual(salida.shape, x.shape)
                # Misma ecuacion y orden de operaciones: igualdad exacta.
                np.testing.assert_array_equal(salida, completa)
                np.testing.assert_array_equal(estado, estado_completo)

    def test_continuidad_entre_llamadas(self):
        """Reanuda con estado no nulo, incluso tras recibir un bloque vacio."""
        x = self.casos[3]["contaminada"][:2051]
        primera, estado = filtrar_por_bloques(x[:137], self.sos, 73)
        estado_guardado = estado.copy()
        vacia, siguiente = filtrar_sos_propio([], self.sos, estado)
        self.assertEqual(vacia.size, 0)
        np.testing.assert_array_equal(siguiente, estado_guardado)
        segunda, final = filtrar_por_bloques(x[137:], self.sos, 511, siguiente)
        np.testing.assert_array_equal(estado, estado_guardado)
        np.testing.assert_array_equal(siguiente, estado_guardado)
        completa, final_completo = filtrar_sos_propio(x, self.sos)
        np.testing.assert_array_equal(np.concatenate((primera, segunda)), completa)
        np.testing.assert_array_equal(final, final_completo)
        np.testing.assert_allclose(completa, signal.sosfilt(self.sos, x),
                                   atol=self.ATOL, rtol=0)

    def test_coeficientes_no_normalizados(self):
        """Multiplicar numerador y denominador no debe cambiar H(z)."""
        x = np.random.default_rng(21).standard_normal(513)
        escalados = self.sos * np.arange(2, len(self.sos) + 2)[:, None]
        copia_coef = escalados.copy()
        copia_x = x.copy()
        salida, _ = filtrar_sos_propio(x, escalados)
        np.testing.assert_allclose(salida, signal.sosfilt(self.sos, x),
                                   atol=self.ATOL, rtol=0)
        np.testing.assert_array_equal(escalados, copia_coef)
        np.testing.assert_array_equal(x, copia_x)

    def test_rechazo_de_entradas_invalidas(self):
        """Evita ejecutar con dimensiones, muestras o estados invalidos."""
        for entrada in (np.zeros((2, 2)), [np.nan], [np.inf], [1j]):
            with self.subTest(entrada=str(entrada)):
                with self.assertRaises(ValueError):
                    filtrar_sos_propio(entrada, self.sos)
        with self.assertRaises(ValueError):
            filtrar_sos_propio([1], self.sos, np.zeros((len(self.sos), 2)))
        malos = self.sos.copy()
        malos[0, 3] = 0
        with self.assertRaises(ValueError):
            filtrar_sos_propio([1], malos)
        for longitud in (0, -1, 1.5):
            with self.subTest(n_bloque=longitud):
                with self.assertRaises(ValueError):
                    filtrar_por_bloques([1], self.sos, longitud)


def ejecutar_pruebas():
    """Ejecuta solo validaciones; devuelve un codigo de proceso para CI."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestFiltroTemporal)
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


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
    caracterizacion = caracterizar_filtro(diseno, config["frecuencias_utiles_hz"])
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diseno y filtrado temporal de los tres casos.")
    parser.add_argument("--pruebas", action="store_true",
                        help="Ejecutar pruebas numericas sin generar salidas ni figuras.")
    argumentos = parser.parse_args()
    if argumentos.pruebas:
        raise SystemExit(ejecutar_pruebas())
    main()
