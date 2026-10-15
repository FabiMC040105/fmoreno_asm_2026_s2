# fmoreno_asm_2026_s2# Taller: experimentación con FFT y detección de ecos

Curso: CE 1110 — Análisis de Señales Mixtas.

Integrantes:
- Fabiana Moreno Castrillo — 2023153700.
- Andrés Blanco Coto — 2022108841.

## Contenido

- `Documentacion_Taller_1.pdf`: procedimiento, resultados y conclusiones.
- `proyecto_1/`: implementación y experimentos de DFT y FFT en GNU Octave.
- `proyecto_1/resultados/`: gráficas y tiempos de Fourier.
- `ecos/deteccion_ecos.py`: simulación y detección de ecos en Python.
- `ecos/resultados_ecos/`: gráficas y tablas de los experimentos de ecos.

## Requisitos

- GNU Octave para ejecutar los archivos `.m`.
- Python 3 con NumPy y Matplotlib para ejecutar los experimentos de ecos.

Instalar las bibliotecas de Python:

```powershell
python -m pip install numpy matplotlib
```

## Ejecutar los experimentos de Fourier

En GNU Octave, seleccionar `proyecto_1` como carpeta de trabajo.
Ejecutar estos comandos, uno por uno:

```octave
experimentos_fft
experimentos_mezcla
comparar_transformadas
comparar_tiempos
```

Los dos primeros generan las gráficas de tiempo, magnitud y fase.
El tercero verifica la equivalencia entre la DFT propia, la FFT propia
y la función `fft` de Octave.
El cuarto compara los tiempos para diferentes cantidades de muestras.

Los resultados se guardan en `proyecto_1/resultados`.

Las funciones `mi_dft.m` y `mi_fft.m` reciben una señal como argumento;
no se ejecutan directamente como scripts.
La FFT propia requiere una longitud que sea potencia de dos.

## Ejecutar los experimentos de ecos

Desde la carpeta principal del repositorio, ejecutar en una terminal:

```powershell
cd ecos
python deteccion_ecos.py
```

El programa simula señales con ecos y ruido, compara la correlación
directa con la calculada mediante FFT, estima retardos y guarda
gráficas y tablas en `ecos/resultados_ecos`.

Para generar únicamente la gráfica de los espectros, desde `ecos`:

```powershell
python -c "import deteccion_ecos as e; e.generar_grafica_espectros()"
```

## Resultados esperados

- Señal senoidal: componente de 50 Hz.
- Mezcla: componentes de 50 Hz y 120 Hz.
- Las transformadas coinciden dentro de las tolerancias del programa.
- Primer eco: 960 muestras, equivalentes a 20 ms.
- Segundo eco: 1920 muestras, equivalentes a 40 ms.

El detector busca ecos a partir de 8 ms. En el experimento de múltiples
ecos se indica previamente que debe buscar dos.

## Reproducción de resultados

Los tiempos dependen del equipo y pueden cambiar entre ejecuciones.
Al ejecutar los experimentos se reemplazan los archivos de resultados
correspondientes. Los tiempos del informe pertenecen a las mediciones
guardadas para esa versión de la entrega.

Los archivos `.m` están escritos para GNU Octave.