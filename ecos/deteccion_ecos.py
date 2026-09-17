"""
Convencion de correlacion usada:
    r_yx[l] = sum_n y[n+l] * conj(x[n])
De esta forma, un eco y[n] = a*x[n-D] produce un pico en lag l = +D.
"""

from pathlib import Path
import csv
import time
import numpy as np
import matplotlib.pyplot as plt



# Parametros globales del experimento
FS = 48_000                 # Hz
DURACION_CHIRP = 8e-3       # s
F_INICIAL = 2_000           # Hz
F_FINAL = 8_000             # Hz
AMPLITUD_TX = 1.0
DURACION_REGISTRO = 0.100   # s
RETARDO_1 = 0.020           # s -> 960 muestras a 48 kHz
RETARDO_2 = 0.040           # s -> 1920 muestras a 48 kHz
AMPLITUD_ECO_1 = 0.65
AMPLITUD_ECO_2 = 0.35
RUIDO_STD = 0.10
SEMILLA = 2026
VELOCIDAD_SONIDO = 343.0    # m/s, solo para relacionar retardo con distancia


# Generacion y simulacion de senales
def generar_senal(fs=FS, duracion=DURACION_CHIRP, f0=F_INICIAL,
                  f1=F_FINAL, amplitud=AMPLITUD_TX):
    """Genera un chirp lineal  f0 -> f1  con ventana de Hann."""
    n_muestras = int(round(fs * duracion))
    t = np.arange(n_muestras) / fs
    duracion_real = n_muestras / fs
    pendiente = (f1 - f0) / duracion_real
    fase = 2.0 * np.pi * (f0 * t + 0.5 * pendiente * t**2)

    # La ventana suaviza los bordes y reduce discontinuidades/esparcimiento espectral.
    ventana = np.hanning(n_muestras)
    x = amplitud * ventana * np.sin(fase)
    return t, x

def agregar_eco(y, x, retardo_muestras, amplitud):
    """Suma a y una copia retardada y atenuada de x."""
    inicio = int(retardo_muestras)
    fin = inicio + len(x)
    if inicio < 0 or fin > len(y):
        raise ValueError("El eco no cabe dentro del registro recibido.")
    y[inicio:fin] += amplitud * x
    return y

def agregar_ruido(y, std=RUIDO_STD, semilla=SEMILLA):
    """Agrega ruido blanco gaussiano reproducible."""
    rng = np.random.default_rng(semilla)
    return y + rng.normal(0.0, std, size=len(y))

def simular_recibida(x, n_total, ecos, ruido_std=0.0,
                     amplitud_directa=1.0, semilla=SEMILLA):
    """
    Construye:
        y[n] = b0*x[n] + sum_i ai*x[n-Di] + w[n]

    ecos: iterable de tuplas (retardo_muestras, amplitud)
    """
    y = np.zeros(n_total, dtype=float)
    if len(x) > n_total:
        raise ValueError("La referencia transmitida no cabe en el registro.")

    # Senal directa, colocada en lag 0.
    y[:len(x)] += amplitud_directa * x

    for retardo, amplitud in ecos:
        agregar_eco(y, x, retardo, amplitud)

    if ruido_std > 0:
        y = agregar_ruido(y, ruido_std, semilla)

    return y


# Correlacion directa y por FFT
def correlacion_directa(y, x):
    """
    Correlacion cruzada lineal implementada de forma educativa.

    Convencion:
        r_yx[l] = sum_n y[n+l] * conj(x[n])

    El algoritmo recorre todos los lags y calcula solo la zona que se solapa.
    No utiliza np.correlate para producir el resultado.
    """
    y = np.asarray(y)
    x = np.asarray(x)
    ny = len(y)
    nx = len(x)

    lags = np.arange(-(nx - 1), ny)
    dtype = np.result_type(y, x, np.complex128)
    r = np.empty(len(lags), dtype=dtype)

    for i, lag in enumerate(lags):
        # Indices de y que tienen una muestra correspondiente en x.
        y_inicio = max(0, lag)
        y_fin = min(ny, nx + lag)
        x_inicio = y_inicio - lag
        x_fin = y_fin - lag

        # np.vdot conjuga el primer argumento: sum conj(x)*y.
        r[i] = np.vdot(x[x_inicio:x_fin], y[y_inicio:y_fin])

    return np.real_if_close(r), lags

def siguiente_potencia_de_2(n):
    """Retorna la menor potencia de 2 mayor o igual que n."""
    if n < 1:
        raise ValueError("n debe ser positivo")
    return 1 << (int(n) - 1).bit_length()

def correlacion_fft(y, x):
    """
    Correlacion lineal mediante FFT usando el teorema de convolucion.

    Como:
        r_yx[l] = y[n] * conj(x[-n])

    se calcula:
        IFFT( FFT(y) * FFT(conj(reverse(x))) )

    Para evitar correlacion circular se usa zero-padding con Nfft >= Ny+Nx-1.
    Los lags devueltos son exactamente los mismos que en correlacion_directa.
    """
    y = np.asarray(y)
    x = np.asarray(x)

    longitud_lineal = len(y) + len(x) - 1
    nfft = siguiente_potencia_de_2(longitud_lineal)

    referencia_invertida = np.conj(x[::-1])
    Y = np.fft.fft(y, n=nfft)
    H = np.fft.fft(referencia_invertida, n=nfft)
    r = np.fft.ifft(Y * H)[:longitud_lineal]

    lags = np.arange(-(len(x) - 1), len(y))
    return np.real_if_close(r), lags


def correlacion_numpy(y, x):
    """Correlacion de biblioteca usada solo como validacion independiente."""
    r = np.correlate(y, x, mode="full")
    lags = np.arange(-(len(x) - 1), len(y))
    return r, lags

# Estimacion de retardos y deteccion de multiples ecos
def estimar_retardo(r, lags, fs, lag_minimo=1):
    """
    Busca el mayor pico de |r| a partir de lag_minimo.
    lag_minimo permite excluir la componente directa de lag 0.
    """
    mascara = lags >= lag_minimo
    if not np.any(mascara):
        raise ValueError("No hay lags dentro del intervalo solicitado.")

    r_busqueda = np.abs(r[mascara])
    lags_busqueda = lags[mascara]
    i = int(np.argmax(r_busqueda))
    retardo_muestras = int(lags_busqueda[i])
    retardo_s = retardo_muestras / fs
    pico = float(r_busqueda[i])
    return retardo_muestras, retardo_s, pico

def detectar_multiples_ecos(r, lags, cantidad, lag_minimo,
                             separacion_minima):
    """
    Selecciona los picos de mayor magnitud aplicando supresion por distancia.
    Evita seleccionar varias veces el lobulo del mismo eco.
    """
    magnitud = np.abs(r)
    candidatos = np.where(lags >= lag_minimo)[0]
    orden = candidatos[np.argsort(magnitud[candidatos])[::-1]]

    seleccionados = []
    for idx in orden:
        lag = int(lags[idx])
        if all(abs(lag - lag_sel) >= separacion_minima
               for lag_sel, _ in seleccionados):
            seleccionados.append((lag, float(magnitud[idx])))
            if len(seleccionados) == cantidad:
                break

    return sorted(seleccionados, key=lambda par: par[0])

def distancia_desde_retardo(retardo_s, velocidad=VELOCIDAD_SONIDO):
    """Distancia monostatica d = v_s*tau/2."""
    return velocidad * retardo_s / 2.0


# Medicion de rendimiento
def medir_tiempo(funcion, *args, repeticiones=7):
    """Mide mediana de tiempo con calentamiento previo."""
    funcion(*args)  # warm-up
    tiempos = []
    for _ in range(repeticiones):
        t0 = time.perf_counter()
        funcion(*args)
        tiempos.append(time.perf_counter() - t0)
    return float(np.median(tiempos))

def comparar_tiempos(tamanos=(256, 512, 1024, 2048, 4096),
                      repeticiones=7, semilla=SEMILLA):
    """Compara correlacion directa y FFT para secuencias de igual longitud N."""
    rng = np.random.default_rng(semilla)
    filas = []

    for n in tamanos:
        x = rng.normal(size=n)
        y = rng.normal(size=n)

        t_directa = medir_tiempo(correlacion_directa, y, x,
                                 repeticiones=repeticiones)
        t_fft = medir_tiempo(correlacion_fft, y, x,
                             repeticiones=repeticiones)

        filas.append({
            "N": int(n),
            "directa_ms": 1000.0 * t_directa,
            "fft_ms": 1000.0 * t_fft,
            "speedup": t_directa / t_fft,
        })

    return filas


# Utilidades de salida
def guardar_csv(ruta, filas, columnas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)

def nueva_figura():
    plt.figure(figsize=(9, 4.8))

def guardar_figura(ruta):
    plt.tight_layout()
    plt.savefig(ruta, dpi=180, bbox_inches="tight")
    plt.close()

def graficar_resultados(carpeta, fs, x, y_sin_ruido, y_ruido,
                        r_dir_ruido, r_fft_ruido, lags,
                        r_multi, lags_multi, retardos_multi,
                        tabla_tiempos, amplitudes, picos_amplitud):
    """Genera las figuras principales solicitadas para el PDF."""
    tx_ms = 1000.0 * np.arange(len(x)) / fs
    ty_ms = 1000.0 * np.arange(len(y_ruido)) / fs
    lags_ms = 1000.0 * lags / fs

    # Figura 1 - senal transmitida
    nueva_figura()
    plt.plot(tx_ms, x, label="Chirp transmitido")
    plt.title("Figura 1. Señal transmitida en el dominio del tiempo")
    plt.xlabel("Tiempo (ms)")
    plt.ylabel("Amplitud normalizada")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig01_senal_transmitida.png")

    # Figura 2 - recibida con eco sin ruido
    nueva_figura()
    plt.plot(ty_ms, y_sin_ruido, label="Señal directa + eco")
    plt.title("Figura 2. Señal recibida con un eco, sin ruido")
    plt.xlabel("Tiempo (ms)")
    plt.ylabel("Amplitud normalizada")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig02_recibida_sin_ruido.png")

    # Figura 3 - recibida con ruido
    nueva_figura()
    plt.plot(ty_ms, y_ruido, label="Señal directa + eco + ruido")
    plt.title("Figura 3. Señal recibida con eco y ruido")
    plt.xlabel("Tiempo (ms)")
    plt.ylabel("Amplitud normalizada")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig03_recibida_con_ruido.png")

    # Figura 4 - correlacion directa
    nueva_figura()
    plt.plot(lags_ms, np.abs(r_dir_ruido), label="|r_yx[l]| directa")
    plt.title("Figura 4. Correlación directa de la señal con ruido")
    plt.xlabel("Lag / retardo (ms)")
    plt.ylabel("Magnitud de correlación")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig04_correlacion_directa.png")

    # Figura 5 - correlacion FFT
    nueva_figura()
    plt.plot(lags_ms, np.abs(r_fft_ruido), label="|r_yx[l]| mediante FFT")
    plt.title("Figura 5. Correlación mediante FFT")
    plt.xlabel("Lag / retardo (ms)")
    plt.ylabel("Magnitud de correlación")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig05_correlacion_fft.png")

    # Figura 6 - comparacion directa vs FFT
    normalizador = max(np.max(np.abs(r_dir_ruido)), 1e-15)
    nueva_figura()
    plt.plot(lags_ms, np.abs(r_dir_ruido) / normalizador,
             label="Directa")
    plt.plot(lags_ms, np.abs(r_fft_ruido) / normalizador,
             linestyle="--", label="FFT")
    plt.title("Figura 6. Comparación de correlación directa y por FFT")
    plt.xlabel("Lag / retardo (ms)")
    plt.ylabel("Magnitud normalizada")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig06_comparacion_correlaciones.png")

    # Figura 7 - rendimiento
    n_vals = [fila["N"] for fila in tabla_tiempos]
    t_dir = [fila["directa_ms"] for fila in tabla_tiempos]
    t_fft = [fila["fft_ms"] for fila in tabla_tiempos]
    nueva_figura()
    plt.plot(n_vals, t_dir, marker="o", label="Correlación directa")
    plt.plot(n_vals, t_fft, marker="o", label="Correlación FFT")
    plt.yscale("log")
    plt.title("Figura 7. Tiempo de ejecución vs tamaño de señal")
    plt.xlabel("N (muestras por secuencia)")
    plt.ylabel("Tiempo mediano (ms, escala logarítmica)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig07_tiempos.png")

    # Figura 8 - multiples ecos
    lags_multi_ms = 1000.0 * lags_multi / fs
    nueva_figura()
    plt.plot(lags_multi_ms, np.abs(r_multi), label="Correlación con múltiples ecos")
    for retardo in retardos_multi:
        plt.axvline(1000.0 * retardo / fs, linestyle="--",
                    label=f"Eco esperado: {retardo} muestras")
    plt.title("Figura 8. Detección de múltiples ecos")
    plt.xlabel("Lag / retardo (ms)")
    plt.ylabel("Magnitud de correlación")
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar_figura(carpeta / "fig08_multiples_ecos.png")

    # Figura 9 - efecto de amplitud del eco
    nueva_figura()
    plt.plot(amplitudes, picos_amplitud, marker="o")
    plt.title("Figura 9. Efecto de la atenuación en el pico de correlación")
    plt.xlabel("Amplitud relativa del eco")
    plt.ylabel("Magnitud del pico de correlación")
    plt.grid(True, alpha=0.3)
    guardar_figura(carpeta / "fig09_efecto_amplitud.png")


def imprimir_tabla_resultados(filas):
    print("\nRESULTADOS DE RETARDO")
    print("-" * 92)
    print(f"{'Experimento':<24} {'Metodo':<10} {'Real':>8} {'Estim.':>8} "
          f"{'Error':>8} {'tau (ms)':>10} {'d* (m)':>10}")
    print("-" * 92)
    for f in filas:
        print(f"{f['experimento']:<24} {f['metodo']:<10} "
              f"{f['retardo_real_muestras']:>8d} {f['retardo_estimado_muestras']:>8d} "
              f"{f['error_muestras']:>8d} {f['retardo_estimado_ms']:>10.3f} "
              f"{f['distancia_m']:>10.3f}")
    print("* d calculada solo como conexion con el radar: d = 343*tau/2.")


def imprimir_tabla_tiempos(filas):
    print("\nCOMPARACION DE TIEMPOS")
    print("-" * 60)
    print(f"{'N':>7} {'Directa (ms)':>15} {'FFT (ms)':>12} {'Speedup':>10}")
    print("-" * 60)
    for f in filas:
        print(f"{f['N']:>7d} {f['directa_ms']:>15.6f} "
              f"{f['fft_ms']:>12.6f} {f['speedup']:>10.2f}")


# Programa principal
def main():
    carpeta = Path("resultados_ecos")
    carpeta.mkdir(parents=True, exist_ok=True)

    # 1) Referencia transmitida
    _, x = generar_senal()
    n_total = int(round(FS * DURACION_REGISTRO))
    d1 = int(round(FS * RETARDO_1))
    d2 = int(round(FS * RETARDO_2))

    # Se excluye del buscador de ecos la zona ocupada por la senal directa.
    lag_minimo_eco = len(x)

    # Experimento 1: un eco sin ruido
    y1 = simular_recibida(
        x, n_total,
        ecos=[(d1, AMPLITUD_ECO_1)],
        ruido_std=0.0,
    )
    r1_dir, lags1 = correlacion_directa(y1, x)
    r1_fft, lags1f = correlacion_fft(y1, x)

    # Experimento 2: un eco con ruido
    y2 = simular_recibida(
        x, n_total,
        ecos=[(d1, AMPLITUD_ECO_1)],
        ruido_std=RUIDO_STD,
    )
    r2_dir, lags2 = correlacion_directa(y2, x)
    r2_fft, lags2f = correlacion_fft(y2, x)

    # Experimento 3: dos ecos con ruido
    y3 = simular_recibida(
        x, n_total,
        ecos=[(d1, AMPLITUD_ECO_1), (d2, AMPLITUD_ECO_2)],
        ruido_std=RUIDO_STD,
    )
    r3_fft, lags3 = correlacion_fft(y3, x)
    ecos_estimados = detectar_multiples_ecos(
        r3_fft, lags3,
        cantidad=2,
        lag_minimo=lag_minimo_eco,
        separacion_minima=max(len(x) // 2, 1),
    )

    # Experimento 4: efecto de amplitud, sin ruido para aislar el efecto.
    amplitudes = [0.80, 0.50, 0.20]
    picos_amplitud = []
    for amp in amplitudes:
        y_amp = simular_recibida(x, n_total, [(d1, amp)], ruido_std=0.0)
        r_amp, lags_amp = correlacion_fft(y_amp, x)
        _, _, pico = estimar_retardo(r_amp, lags_amp, FS, lag_minimo_eco)
        picos_amplitud.append(pico)

    # Validaciones numericas
    r_np, lags_np = correlacion_numpy(y2, x)
    max_diff_dir_numpy = float(np.max(np.abs(r2_dir - r_np)))
    max_diff_dir_fft = float(np.max(np.abs(r2_dir - r2_fft)))

    if not np.array_equal(lags1, lags1f):
        raise RuntimeError("Los lags de correlacion directa y FFT no coinciden.")
    if not np.array_equal(lags2, lags2f):
        raise RuntimeError("Los lags del experimento con ruido no coinciden.")
    if not np.array_equal(lags2, lags_np):
        raise RuntimeError("Los lags de NumPy no coinciden con la implementacion propia.")
    if not np.allclose(r2_dir, r2_fft, atol=1e-10, rtol=1e-10):
        raise RuntimeError("Correlacion directa y FFT no son equivalentes numericamente.")
    if not np.allclose(r2_dir, r_np, atol=1e-10, rtol=1e-10):
        raise RuntimeError("La implementacion directa no coincide con numpy.correlate.")

    # Tabla de retardos: exp. 1 y 2 con ambos metodos.
    resultados = []
    for nombre, r_dir, r_fft, lags in [
        ("Sin ruido", r1_dir, r1_fft, lags1),
        ("Con ruido", r2_dir, r2_fft, lags2),
    ]:
        for metodo, r in [("Directo", r_dir), ("FFT", r_fft)]:
            d_est, tau_est, _ = estimar_retardo(r, lags, FS, lag_minimo_eco)
            resultados.append({
                "experimento": nombre,
                "metodo": metodo,
                "retardo_real_muestras": d1,
                "retardo_estimado_muestras": d_est,
                "error_muestras": d_est - d1,
                "retardo_real_ms": 1000.0 * d1 / FS,
                "retardo_estimado_ms": 1000.0 * tau_est,
                "error_ms": 1000.0 * (d_est - d1) / FS,
                "distancia_m": distancia_desde_retardo(tau_est),
            })

    # Experimento 5: tiempos directa vs FFT.
    tabla_tiempos = comparar_tiempos()

    # Guardar tablas
    guardar_csv(
        carpeta / "tabla_resultados.csv", resultados,
        ["experimento", "metodo", "retardo_real_muestras",
         "retardo_estimado_muestras", "error_muestras",
         "retardo_real_ms", "retardo_estimado_ms", "error_ms",
         "distancia_m"],
    )
    guardar_csv(
        carpeta / "tabla_tiempos.csv", tabla_tiempos,
        ["N", "directa_ms", "fft_ms", "speedup"],
    )
    tabla_amp = [
        {"amplitud_eco": amp, "pico_correlacion": pico}
        for amp, pico in zip(amplitudes, picos_amplitud)
    ]
    guardar_csv(
        carpeta / "tabla_amplitudes.csv", tabla_amp,
        ["amplitud_eco", "pico_correlacion"],
    )

    # Graficas
    graficar_resultados(
        carpeta, FS, x, y1, y2,
        r2_dir, r2_fft, lags2,
        r3_fft, lags3, [d1, d2],
        tabla_tiempos, amplitudes, picos_amplitud,
    )

    # Consola
    print("PARAMETROS PRINCIPALES")
    print(f"fs = {FS} Hz")
    print(f"Chirp = {F_INICIAL} -> {F_FINAL} Hz")
    print(f"Duracion chirp = {1000*len(x)/FS:.3f} ms ({len(x)} muestras)")
    print(f"Duracion registro = {1000*n_total/FS:.3f} ms ({n_total} muestras)")
    print(f"Eco 1 = {d1} muestras = {1000*d1/FS:.3f} ms, amplitud {AMPLITUD_ECO_1}")
    print(f"Eco 2 = {d2} muestras = {1000*d2/FS:.3f} ms, amplitud {AMPLITUD_ECO_2}")
    print(f"Ruido sigma = {RUIDO_STD}, semilla = {SEMILLA}")

    print("\nVALIDACION")
    print(f"max |directa - numpy.correlate| = {max_diff_dir_numpy:.3e}")
    print(f"max |directa - FFT|             = {max_diff_dir_fft:.3e}")

    imprimir_tabla_resultados(resultados)

    print("\nMULTIPLES ECOS (FFT)")
    for lag, pico in ecos_estimados:
        print(f"lag = {lag:4d} muestras, tau = {1000*lag/FS:7.3f} ms, "
              f"pico = {pico:.6f}")

    print("\nEFECTO DE AMPLITUD")
    for amp, pico in zip(amplitudes, picos_amplitud):
        print(f"amplitud = {amp:.2f} -> pico = {pico:.6f}")

    imprimir_tabla_tiempos(tabla_tiempos)
    print(f"\nArchivos guardados en: {carpeta.resolve()}")


if __name__ == "__main__":
    main()
