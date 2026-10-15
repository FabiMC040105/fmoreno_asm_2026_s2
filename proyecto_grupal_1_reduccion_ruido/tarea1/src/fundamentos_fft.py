
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

#adaptación del proyecto indiv para dft

def mi_dft(x):
    N = len(x)
    X = np.zeros(N, dtype=complex)

    # Recorremos las frecuencias que queremos analizar
    for k in range(N):

        # Sumamos el aporte de cada muestra
        for n in range(N):
            X[k] += x[n] * np.exp(-2j * np.pi * k * n / N)

    return X


# adaptacion del proyect indiv para fft

def mi_fft(x):
    x = np.asarray(x, dtype=complex)
    N = len(x)

    # La FFT radix-2 requiere una potencia de 2
    if N == 0 or (N & (N - 1)) != 0:
        raise ValueError("N debe ser potencia de 2")

    # Caso base
    if N == 1:
        return x.copy()

    # Dividimos las muestras en posiciones pares e impares
    pares = mi_fft(x[::2])
    impares = mi_fft(x[1::2])

    # Calculamos los factores complejos
    k = np.arange(N // 2)
    W = np.exp(-2j * np.pi * k / N)

    # Combinamos los resultados
    return np.concatenate((
        pares + W * impares,
        pares - W * impares
    ))


# Prueba de DFT

Fs = 1024          # Frecuencia de muestreo (Hz)
N = 256            # Cantidad de muestras
f0 = 128           # Frecuencia de la señal (Hz)

t = np.arange(N) / Fs

# Generamos una señal sinusoidal
x = np.sin(2 * np.pi * f0 * t)

# Calculamos la DFT utilizando nuestra función
X_dft = mi_dft(x)

# Comparamos con la FFT de NumPy
X_fft = np.fft.fft(x)

error = np.max(np.abs(X_dft - X_fft))

print("Cantidad de muestras:", N)
print("Frecuencia de la señal:", f0, "Hz")
print("Resolución frecuencial:", Fs / N, "Hz")
print("Error máximo DFT vs FFT:", error)
print("¿Coinciden?", np.allclose(X_dft, X_fft, atol=1e-9, rtol=0))



# comparación de las tres implementaciones

X_fft_propia = mi_fft(x)

error_propia = np.max(np.abs(X_dft - X_fft_propia))
error_numpy = np.max(np.abs(X_fft_propia - X_fft))

print("\nComparación de implementaciones:")
print("Error DFT propia vs FFT propia:", error_propia)
print("Error FFT propia vs NumPy:", error_numpy)

tolerancia = 1e-9

assert error_propia < tolerancia
assert error_numpy < tolerancia

print("Las tres implementaciones coinciden correctamente.")


# Comparacion de ventanas rectangular y Hann
# Inciso 2.1(c)

frecuencias = [128, 130]
ventanas = {
    "Rectangular": np.ones(N),
    "Hann": np.hanning(N)
}

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

for fila, frecuencia in enumerate(frecuencias):

    # Generamos la señal
    senal = np.sin(2 * np.pi * frecuencia * t)

    for columna, (nombre, ventana) in enumerate(ventanas.items()):

        # Aplicamos la ventana
        senal_ventana = senal * ventana

        # Calculamos su espectro
        espectro = np.fft.rfft(senal_ventana)
        eje_f = np.fft.rfftfreq(N, 1 / Fs)

        # Magnitud normalizada en decibelios
        magnitud = 2 * np.abs(espectro) / np.sum(ventana)
        magnitud_db = 20 * np.log10(np.maximum(magnitud, 1e-12))

        # Graficamos
        ax = axes[fila, columna]
        ax.plot(eje_f, magnitud_db)
        ax.set_title(f"{frecuencia} Hz - Ventana {nombre}")
        ax.set_xlabel("Frecuencia (Hz)")
        ax.set_ylabel("Magnitud (dB)")
        ax.set_xlim(0, 256)
        ax.set_ylim(-100, 5)
        ax.grid(True)

plt.tight_layout()

# img para el informe
carpeta = Path(__file__).resolve().parents[1] / "resultados" / "figuras"
carpeta.mkdir(parents=True, exist_ok=True)

plt.savefig(carpeta / "comparacion_ventanas.png", dpi=150)
plt.show()



# Graficas de fase
# el 2.1(c)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

for fila, frecuencia in enumerate(frecuencias):

    senal = np.sin(2 * np.pi * frecuencia * t)

    for columna, (nombre, ventana) in enumerate(ventanas.items()):

        espectro = np.fft.rfft(senal * ventana)
        eje_f = np.fft.rfftfreq(N, 1 / Fs)

        magnitud = np.abs(espectro)
        fase = np.angle(espectro, deg=True)

        # Solo mostramos fases de componentes significativas
        umbral = 0.01 * np.max(magnitud)
        validos = magnitud > umbral

        ax = axes[fila, columna]
        ax.stem(eje_f[validos], fase[validos])

        ax.set_title(f"Fase - {frecuencia} Hz - {nombre}")
        ax.set_xlabel("Frecuencia (Hz)")
        ax.set_ylabel("Fase (grados)")
        ax.set_xlim(90, 170)
        ax.set_ylim(-190, 19)
        ax.grid(True)

plt.tight_layout()

plt.savefig(carpeta / "comparacion_fases.png", dpi=150)
plt.show()


# Simetria conjugada e IFFT
# el 2.1(d)

# Calculamos el espectro completo de nuestra señal
X = np.fft.fft(x)

# Verificamos X[k] = conjugado(X[N-k])
indices = np.arange(1, N // 2)

error_simetria = np.max(np.abs(
    X[indices] - np.conj(X[N - indices])
))

print("\nVerificacion de simetria conjugada:")
print("Error maximo de simetria:", error_simetria)

# Reconstruimos la señal original con IFFT
x_recuperada = np.fft.ifft(X)

error_reconstruccion = np.max(
    np.abs(x - x_recuperada.real)
)

print("Error de reconstruccion:", error_reconstruccion)
print("Parte imaginaria maxima:",
      np.max(np.abs(x_recuperada.imag)))

# Demostramos que pasa si rompemos la simetria
k = int(round(f0 * N / Fs))

X_incorrecto = X.copy()
X_incorrecto[k] = 0

senal_incorrecta = np.fft.ifft(X_incorrecto)

# Ahora modificamos las dos frecuencias simetricas
X_correcto = X.copy()
X_correcto[k] = 0
X_correcto[N - k] = 0

senal_correcta = np.fft.ifft(X_correcto)

print("\nModificacion del espectro:")
print("Parte imaginaria sin simetria:",
      np.max(np.abs(senal_incorrecta.imag)))
print("Parte imaginaria con simetria:",
      np.max(np.abs(senal_correcta.imag)))

assert error_simetria < 1e-9
assert error_reconstruccion < 1e-9

print("Simetria y reconstruccion verificadas.")



# Resolucion frecuencial, latencia y memoria
# el 2.1(b)

print("\nComparacion de tamanos de bloque:")
print("N\tDelta f (Hz)\tT (ms)\tMemoria (bytes)")

tamanos = [128, 256, 512]

for N_prueba in tamanos:

    # Separacion entre bins
    delta_f = Fs / N_prueba

    # Tiempo necesario para adquirir un bloque
    tiempo_ms = (N_prueba / Fs) * 1000

    # Memoria de entrada usando float32 (4 bytes/muestra)
    memoria = N_prueba * 4

    print(f"{N_prueba}\t{delta_f:.2f}\t\t"
          f"{tiempo_ms:.2f}\t\t{memoria}")
