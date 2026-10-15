import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path  
# Poner atención a la ruta de importación, ya que depende de la estructura del proyecto
from generacion_senales import FS, N_BLOQUE, CASOS


print("1. Iniciando el script...")

def reduccion_espectral_adaptativa(signal, block_size = 1024, umbral_energia = 0.1):
    # Cadena mínima de reducción de ruido por bloques con solapamiento (Overlap-Add).
    # a) Operar con bloques de tamaño potencia de dos
    # d) Utilizar solapamiento (50% en este caso) con ventana
    step_size = block_size // 2
    window = np.hanning(block_size)

    # Preparar señal de salida
    salida = np.zeros(len(signal) + block_size)

    # Procesamiento por bloques
    for i in range(0, len(signal) - block_size, step_size):
        # 1. Bloque con entrada y ventana
        bloque = signal[i:i + block_size] * window

        # 2. FFT
        espectro = np.fft.fft(bloque)
        magnitud = np.abs(espectro)
        fase = np.angle(espectro)

        # 3. Estimación y modificación espectral (Parámetro adaptativo: umbral de energía)
        # c) Parámetro adaptativo: umbral de atenuación basado en la energía del bloque
        umbral = np.max(magnitud) * umbral_energia

        # Aplicar atenuación a componentes menores al umbral
        magnitud_modificada = np.where(magnitud < umbral, magnitud * 0.1, magnitud)

        # b) Preservar la simetría necesaria para reconstruir una señal real
        # np.fft.fft genera el espectro simétrico, al modificar la magnitud en todo el arreglo
        # basándonse en umbrales absolutos, la simetría se mantiene automáticamente.
        espectro_modificado = magnitud_modificada * np.exp(1j*fase)

        # 4. IFFT
        bloque_procesado = np.fft.ifft(espectro_modificado).real

        # 5. Reconstrucción y solapamiento (Overlap-Add)
        salida[i:i + block_size] += bloque_procesado
        
    return salida[:len(signal)]
if __name__ == "__main__":
    print("2. Entrando al bloque principal de pruebas...")
    # También prestar atención a esta ruta.
    # Directorio padre, tarea1
    dir_padre = Path(__file__).resolve().parent.parent
    # Directorio de pruebas, tarea1/pruebas
    base_path = dir_padre / "pruebas"
    FS = 8192

    for i in range(1, 4):
        print(f"\n--- Procesando CASO {i} ---")
        ruta_caso = base_path / f"caso_{i}"

        try:
            print("   Cargando archivos .npy...")
            # Se hace el umbral muy agresivo en el Caso 3 para forzar la degradación de la señal útil
            umbral = 0.1 if i != 3 else 0.85

            # 1. Cargar señal contaminada validada por las pruebas
            senal_contaminada = np.load(ruta_caso / "contaminada.npy")
            senal_limpia = np.load(ruta_caso / "limpia.npy")

            print("   Aplicando filtro FFT...")
            #2. Aplicar el filtro usando el N_BLOQUE validado
            # Ajusta el umbral según el caso
            senal_filtrada = reduccion_espectral_adaptativa(
                senal_contaminada,
                block_size = N_BLOQUE,
                umbral_energia = umbral
            )
            
            # VISUALIZACIÓN
            plt.figure(figsize=(14, 6))
            
            # 3A. Gráfica en el Dominio del Tiempo (Primeras 500 muestras para ver detalle)
            plt.subplot(2, 1, 1)
            muestras = 500
            plt.plot(senal_contaminada[:muestras], label="Contaminada", alpha=0.5, color='gray')
            plt.plot(senal_limpia[:muestras], label="Limpia (Referencia)", linestyle='--', color='blue')
            plt.plot(senal_filtrada[:muestras], label="Filtrada (FFT)", color='orange', linewidth=1.5)
            plt.title(f"CASO {i} - Reducción en el Tiempo")
            plt.ylabel("Amplitud")
            plt.legend()
            plt.grid(True)
            
            # 3B. Gráfica en el Dominio de la Frecuencia (Espectro)
            plt.subplot(2, 1, 2)
            N = len(senal_contaminada)
            freqs = np.fft.fftfreq(N, 1/FS)
            mask = freqs >= 0  # Solo parte positiva
            
            # Espectros normalizados
            espectro_contaminado = (2/N) * np.abs(np.fft.fft(senal_contaminada))
            espectro_filtrado = (2/N) * np.abs(np.fft.fft(senal_filtrada))
            
            plt.plot(freqs[mask], espectro_contaminado[mask], label="Espectro Contaminado", alpha=0.5, color='gray')
            plt.plot(freqs[mask], espectro_filtrado[mask], label="Espectro Filtrado", color='orange')
            plt.xlim(0, 1500) # Ajustar el límite de frecuencia según los tonos disponibles
            plt.title(f"CASO {i} - Salida Espectral")
            plt.xlabel("Frecuencia (Hz)")
            plt.ylabel("Magnitud")
            plt.legend()
            plt.grid(True)
            
            plt.tight_layout()
            # Obtener la ruta exacta de la carpeta donde está este script
            carpeta_script = Path(__file__).resolve().parent
            ruta_imagen = carpeta_script / f"resultado_caso_{i}.png"
            
            # Guardar la imagen en esa carpeta
            plt.savefig(ruta_imagen, bbox_inches='tight')
            print(f"   ¡Gráfica guardada exitosamente en: {ruta_imagen}")
            
            # Limpiar la figura de la memoria para que el siguiente caso empiece en blanco
            plt.close()
        except FileNotFoundError as e:
            print(f"   ERROR: No se encontró un archivo. Detalle: {e}")
        except Exception as e:
            print(f"   ERROR INESPERADO: {e}")
print("\n4. Fin del script.")
