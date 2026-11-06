# CE1110 — Análisis de Señales Mixtas
## Tarea 1: Caracterización espectral y prototipado de filtros para reducción de ruido

### Descripción

Este proyecto implementa y compara métodos de procesamiento digital de señales para reducir ruido mediante filtrado temporal y espectral.

El trabajo comprende:

- **2.1 — Fundamentos y FFT:** implementación de DFT y FFT, comparación de ventanas rectangular y Hann, resolución frecuencial y simetría conjugada.
- **2.2 — Generación de señales:** creación de tres casos reproducibles de señales contaminadas.
- **2.3 — Filtrado temporal:** diseño e implementación de un filtro IIR Butterworth.
- **2.4 — Filtrado espectral:** reducción adaptativa de ruido mediante FFT/IFFT y reconstrucción por solapamiento.
- **2.5 — Comparación:** evaluación de MSE, SNR, atenuación, energía útil, tiempo de procesamiento y memoria.

**Repositorio:** https://github.com/FabiMC040105/fmoreno_asm_2026_s2

**Rama de integración:** `development`

## 1. Estructura del proyecto

El código correspondiente a esta entrega se encuentra en:

`proyecto_grupal_1_reduccion_ruido/tarea1/`

Contenido principal:

- `notebook.ipynb`: notebook de generación de señales y comparación de filtros.
- `src/`: implementaciones Python de FFT, generación, filtrado temporal, filtrado espectral y comparación.
- `pruebas/`: señales originales, contaminadas y archivos de pruebas automatizadas.
- `resultados/`: gráficas, archivos filtrados, métricas y análisis numérico.
- `metadatos/`: configuraciones reproducibles y parámetros de los filtros.
- `referencia_octave/`: implementaciones anteriores de DFT y FFT utilizadas como referencia.
- `requirements.txt`: dependencias del proyecto.
- `README.md`: instrucciones de ejecución y documentación.

## 2. Requisitos

Se necesita Python 3 y las dependencias indicadas en `requirements.txt`:

- NumPy
- SciPy
- Matplotlib
- Pandas
- nbformat
- ipykernel

Para ejecutar el notebook visualmente también se puede utilizar Jupyter Notebook o Visual Studio Code con la extensión Jupyter.

## 3. Instalación y ejecución

Abrir PowerShell desde la raíz del repositorio y acceder a la carpeta de la tarea:

`cd proyecto_grupal_1_reduccion_ruido/tarea1`

Instalar dependencias:

`py -m pip install -r requirements.txt`

Regenerar las señales y sus gráficas:

`py src/generacion_senales.py`

Ejecutar los dos filtros y generar las métricas comparativas:

`py src/comparar_metodos.py`

Ejecutar las pruebas automatizadas:

`py -m unittest discover -s pruebas -p "test_*.py" -v`

Los comandos anteriores permiten reproducir los resultados sin necesidad de abrir Jupyter.

Para utilizar el notebook, abrir `notebook.ipynb` en VS Code y seleccionar **Run All**.

Alternativamente, instalar Jupyter Notebook:

`py -m pip install notebook`

Y ejecutarlo mediante:

`py -m notebook notebook.ipynb`

En Linux o macOS puede utilizarse `python3` en lugar de `py`.

## 4. Configuración de las señales

Los experimentos principales utilizan los siguientes parámetros:

| Parámetro | Valor |
|---|---|
| Frecuencia de muestreo | 8192 Hz |
| Tamaño de bloque | 1024 muestras |
| Duración de registro | 2 segundos |
| Muestras por registro | 16384 |
| Resolución frecuencial por bloque | 8 Hz |
| Tonos útiles | 256, 512 y 1024 Hz |

Se utilizan tres casos de prueba:

| Caso | Tipo de ruido | SNR inicial |
|---|---|---|
| 1 | Interferencia sinusoidal de 1792 Hz | 5 dB |
| 2 | Ruido blanco gaussiano | 3 dB |
| 3 | Ruido limitado aproximadamente a 850–1300 Hz | 0 dB |

Las semillas y los parámetros completos se almacenan en `metadatos/configuraciones.json`.

Los casos se conservan en `pruebas/caso_1/`, `pruebas/caso_2/` y `pruebas/caso_3/`, incluyendo señales limpias, ruido y señales contaminadas en formatos WAV y NPY.

## 5. Implementaciones

### 5.1. Fundamentos y FFT

Archivo: `src/fundamentos_fft.py`

Incluye implementaciones propias de DFT y FFT, comparación con NumPy, generación de tonos alineados y no alineados, análisis de ventanas rectangular y Hann, magnitud y fase, verificación de simetría conjugada e IFFT.

Los experimentos didácticos utilizan 1024 Hz y 256 muestras, independientemente de los parámetros de los tres casos principales.

### 5.2. Generación de señales

Archivo: `src/generacion_senales.py`

Genera las tres señales de prueba, ajusta los niveles de ruido a las SNR objetivo y exporta archivos WAV, NPY, figuras y metadatos.

### 5.3. Filtrado temporal

Archivo: `src/filtros_temporales.py`

Implementa un filtro IIR Butterworth pasa bajas de orden 12 mediante seis secciones de segundo orden (SOS).

Se conservan los estados del filtro entre bloques y se compara la implementación propia con las funciones de SciPy.

### 5.4. Filtrado espectral

Archivo: `src/filtrado_espectral.py`

Implementa reducción adaptativa de ruido mediante FFT/IFFT.

Características:

- Ventana Hann periódica.
- Solapamiento del 50 %.
- FFT real e IFFT real.
- Umbral adaptativo relativo a la magnitud máxima de cada bloque.
- Factor de atenuación de 0.1 para componentes bajo el umbral.
- Reconstrucción Overlap-Add normalizada.
- Tratamiento de los extremos para conservar la longitud de la señal.

La implementación integrada incluye correcciones de reconstrucción por bloques y normalización OLA.

Para la comparación principal se utiliza un umbral relativo de 0.10 en los tres casos. El umbral de 0.85 se utiliza únicamente en el experimento adicional de distorsión del caso 3.

## 6. Métricas y resultados

Archivo principal: `resultados/metricas.csv`

Contiene nueve filas correspondientes a los tres casos y los tres métodos:

- Sin filtrar.
- Filtrado temporal.
- Filtrado espectral.

Se calculan:

- Error cuadrático medio (MSE).
- SNR de entrada y salida.
- Mejora de SNR.
- Porcentaje de energía útil conservada.
- Atenuación del ruido inyectado.
- Tiempo de procesamiento por bloque.
- Memoria aproximada.

La SNR y el MSE se calculan comparando directamente la salida con la referencia limpia, sin compensación de retardo.

La fase no lineal del filtro IIR puede producir diferencias temporales importantes y reducir la SNR medida, incluso cuando atenúa considerablemente la interferencia.

La energía útil conservada se evalúa procesando la referencia limpia. En el método espectral se utilizan las mismas máscaras obtenidas exclusivamente de la mezcla contaminada; la referencia no interviene en la detección.

Los tiempos reportados son mediciones realizadas en una computadora con Python, no en un ESP32.

Los presupuestos de memoria corresponden a estimaciones de búferes y estructuras de datos, no a mediciones de memoria física del microcontrolador.

## 7. Resultados generados

| Archivo | Contenido |
|---|---|
| `resultados/metricas_generacion.csv` | Caracterización de los tres casos |
| `resultados/metricas.csv` | Comparación de los métodos |
| `resultados/espectral_compromiso.csv` | Comparación de umbrales 0.10 y 0.85 |
| `resultados/metricas_metodologia.json` | Definiciones y metodología de medición |
| `resultados/figuras/comparacion_metodos.png` | Comparación gráfica de ambos filtros |
| `resultados/figuras/espectral_compromiso.png` | Compromiso entre reducción de ruido y distorsión |
| `resultados/temporal/` | Salidas del filtro temporal |
| `resultados/espectral/` | Salidas del filtro espectral |

También se incluyen las gráficas de fundamentos FFT, generación de señales, polos y ceros y respuesta del filtro temporal.

## 8. Pruebas y reproducibilidad

El proyecto contiene pruebas automatizadas para:

- Verificar la generación reproducible de las señales.
- Validar los niveles de SNR de entrada.
- Comprobar el funcionamiento del filtro temporal.
- Comparar la implementación temporal propia con SciPy.
- Verificar la reconstrucción espectral por bloques.
- Comprobar la consistencia de los resultados comparativos.

Para ejecutar las pruebas desde la carpeta `tarea1`:

`py -m unittest discover -s pruebas -p "test_*.py" -v`

El repositorio incluye también `resultados/notebook_validacion_ejecutado.ipynb` como evidencia de una ejecución previa.

Se recomienda repetir todas las pruebas sobre la versión definitiva antes de realizar la entrega.

## 9. Propuesta de implementación embebida

Para la futura implementación se considera la plataforma ESP32.

La propuesta contempla tres nodos:

1. Adquisición y análisis espectral.
2. Filtrado temporal.
3. Filtrado espectral y evaluación.

La selección definitiva del hardware, las interfaces de comunicación, los protocolos y los presupuestos de transmisión debe justificarse en el informe final.

Las simulaciones actuales se realizaron en Python y no constituyen una implementación física validada en microcontroladores.

## 10. Control de versiones y entrega

El desarrollo se realizó utilizando ramas individuales de Git y una rama de integración.

Ramas principales:

- `feature/fundamentos-fft`
- `feature/generacion-caracterizacion-senales`
- `feature/filtro-temporal`
- `feature/filtrado-espectral`
- `development`

El código de los diferentes componentes se encuentra integrado en `development`.

Después de ejecutar y aprobar las pruebas definitivas, se debe crear el tag:

`tarea1_prototipo`

El tag identificará la versión exacta del proyecto utilizada para la entrega.

El paquete de entrega debe incluir el informe PDF, notebook ejecutable, código fuente, casos de prueba, resultados, metadatos y este README.

## 11. Limitaciones

Los resultados proceden de señales sintéticas y simulaciones en computadora.

La eficacia de los filtros depende de la separación entre la señal útil y las componentes de ruido.

Cuando el ruido se superpone a las frecuencias útiles, su eliminación puede producir distorsión.

Las mediciones de tiempo y memoria en Python no garantizan funcionamiento en tiempo real sobre un ESP32. La implementación embebida requiere validación adicional de precisión, latencia, comunicación y recursos.

---

**Curso:** CE1110 — Análisis de Señales Mixtas

**Proyecto:** Tarea 1 — Caracterización espectral y prototipado de filtros para reducción de ruido

**Período:** II Semestre 2026

**Institución:** Instituto Tecnológico de Costa Rica
