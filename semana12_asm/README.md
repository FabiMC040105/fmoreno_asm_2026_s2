# CE1110 - Análisis de Señales Mixtas
## Sesión asincrónica - Semana 12

### Descripción

En esta sesión se desarrolló un prototipo para generar, recibir y analizar señales mediante la Transformada Rápida de Fourier (FFT).

El trabajo incluye un sistema en Python para generar y analizar señales, así como una implementación física utilizando dos microcontroladores ESP32.

También se reutilizan los filtros temporales y espectrales desarrollados anteriormente para el Proyecto Grupal 1.

## 1. Organización de archivos

La carpeta `semana12_asm` contiene:

- `firmware/`: programas Arduino para las pruebas con ESP32.
- `python/`: programas de generación, adquisición y análisis de señales.
- `pruebas/`: pruebas automáticas de los programas.
- `datos/fisico/`: capturas de pruebas iniciales.
- `datos/fisico_dos_placas/`: capturas y resultados de las pruebas con dos ESP32.
- `resultados_integracion/`: gráficas, tablas y resultados del prototipo en Python.
- `requirements_fisica.txt`: dependencias para las pruebas físicas.
- `requirements_integracion.txt`: dependencias del sistema de alto nivel.

## 2. Parámetros utilizados

Se trabajó con los siguientes valores:

| Parámetro | Valor |
|---|---|
| Frecuencia de muestreo nominal | 8192 Hz |
| Tamaño de bloque | 1024 muestras |
| Resolución frecuencial | 8 Hz |
| Duración nominal del bloque | 125 ms |
| Frecuencias utilizadas | 256, 512, 1024 y 1792 Hz |

Se implementaron cinco modos de generación:

| Modo | Frecuencias |
|---|---|
| 1 | 256 Hz |
| 2 | 1024 Hz |
| 3 | 256, 512 y 1024 Hz |
| 4 | 256, 512, 1024 y 1792 Hz |
| 5 | 1792 Hz |

Estas frecuencias se utilizan tanto en el prototipo de Python como en el programa del emisor.

## 3. Sistema en Python

El programa principal se encuentra en:

`python/prototipo_alto_nivel.py`

Este programa permite:

- Generar las señales de los cinco modos.
- Visualizar las señales en el tiempo y en frecuencia.
- Calcular sus espectros mediante FFT.
- Reutilizar los filtros temporal IIR y espectral FFT/IFFT de la Tarea 1.
- Comparar las señales limpias, contaminadas y filtradas.
- Calcular métricas de MSE y SNR para los casos simulados.
- Revisar las capturas físicas guardadas.
- Exportar gráficas y archivos CSV.

### Instalación

Se requiere Python 3 con las bibliotecas NumPy, SciPy, Matplotlib y PySerial.

Desde la raíz del repositorio, ejecutar:

```powershell
py -m pip install -r semana12_asm/requirements_integracion.txt
py -m pip install -r semana12_asm/requirements_fisica.txt
```

### Ejecutar el sistema completo

Desde la raíz del repositorio:

```powershell
py semana12_asm/python/prototipo_alto_nivel.py --completo
```

Este comando genera los cinco modos, ejecuta los experimentos de filtrado y revisa las capturas físicas disponibles.

Para generar únicamente los modelos de frecuencias:

```powershell
py semana12_asm/python/prototipo_alto_nivel.py --solo-frecuencias
```

Los resultados se guardan automáticamente en:

`semana12_asm/resultados_integracion/`

## 4. Implementación física

Se utilizaron dos placas ESP-32D.

### ESP32 emisor

El emisor genera las señales utilizando el DAC interno en el pin GPIO25.

Programa:

`firmware/02_emisor_dos_placas/02_emisor_dos_placas.ino`

### ESP32 receptor

El receptor adquiere las señales mediante el ADC interno en el pin GPIO34.

Programa:

`firmware/03_receptor_dos_placas/03_receptor_dos_placas.ino`

El receptor adquiere bloques de 1024 muestras y los transmite a la computadora mediante comunicación serial.

### Conexión

Entre el DAC del emisor y el ADC del receptor se colocó una resistencia de 4.7 kΩ.

También se utilizó un capacitor de 10 nF entre la entrada del ADC y GND.

Ambas placas comparten GND y se alimentan por separado mediante USB. No se conectan los pines de alimentación entre placas.

### Análisis de las capturas

El programa `python/validar_fft_receptor.py` permite analizar las muestras recibidas.

El procesamiento incluye la eliminación de la componente DC, aplicación de una ventana Hann, cálculo de FFT y comparación de las frecuencias detectadas con las esperadas.

La FFT se realiza actualmente en Python, no dentro del ESP32 receptor.

### Repetir las pruebas físicas

Para repetir las pruebas se deben conectar ambas placas, cargar el firmware correspondiente y conocer sus puertos seriales.

Desde la carpeta `semana12_asm`:

```powershell
py python/probar_dos_placas.py --listar-puertos
```

Para ejecutar los cinco modos, sustituyendo los puertos por los correspondientes:

```powershell
py python/probar_dos_placas.py --emisor COM6 --receptor COM7 --todos
```

Estas pruebas requieren tener las dos ESP32 conectadas.

## 5. Resultados

### Pruebas físicas

Se realizaron capturas con los cinco modos de generación utilizando las dos placas.

Los archivos guardados muestran la detección de las frecuencias esperadas en los cinco modos.

Cada captura contiene 1024 muestras. Los reportes registran cuatro muestras tardías por bloque y no indican saturación del ADC.

Las evidencias están disponibles en:

`datos/fisico_dos_placas/`

Archivos principales:

- `captura_modo*.csv`: muestras adquiridas por el ADC.
- `fft_modo*.png`: gráficas temporales y espectrales.
- `reporte_modo*.json`: resultados del análisis.
- `resumen_dos_placas.csv`: resumen de las cinco pruebas.

### Prototipo en Python

Los resultados del sistema de alto nivel se encuentran en:

`resultados_integracion/`

Archivos principales:

- `modelo_modo*.png`: gráficas de los cinco modos simulados.
- `senal_modo*.csv`: muestras generadas en Python.
- `modos_prototipados.csv`: resumen de frecuencias.
- `simulacion_filtros_caso*.png`: comparación de los métodos de filtrado.
- `metricas_simulacion.csv`: métricas de los casos simulados.
- `contraste_capturas_fisicas.csv`: comprobación de las capturas guardadas.
- `resumen_ejecucion.json`: resumen de la ejecución.

Los resultados simulados y los resultados físicos se mantienen identificados por separado.

Las métricas de MSE y SNR del prototipo corresponden a simulaciones con referencias conocidas y no representan mediciones del desempeño de los filtros en las ESP32.

## 6. Pruebas automáticas

Desde la raíz del repositorio, ejecutar:

```powershell
py -m unittest discover -s semana12_asm/pruebas -p "test_*.py" -v
```

En la ejecución de integración realizada el 29 de octubre de 2026 se obtuvieron 8 pruebas aprobadas.

Estas pruebas revisan los parámetros, las frecuencias generadas, los archivos exportados, los filtros disponibles y las capturas físicas almacenadas.

No sustituyen una nueva prueba experimental del hardware.

## 7. Limitaciones

La frecuencia de muestreo de 8192 Hz es nominal, ya que la adquisición se controla por software.

El receptor ESP32 captura y transmite las muestras, mientras que el análisis FFT se realiza en la computadora.

El procesamiento de reducción de ruido mediante los filtros temporal y espectral se ha evaluado en Python, pero todavía no se encuentra integrado como procesamiento principal dentro de los microcontroladores.

La implementación embebida de los métodos de filtrado y su evaluación en tiempo real corresponden a etapas posteriores del Proyecto Grupal 1.
