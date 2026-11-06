# Nodo 2 + Nodo 3 — firmware preliminar en una ESP32 clásica

Este sketch recibe bloques `N1B2` del Nodo 1 y ejecuta **dos rutas paralelas** sobre la misma señal:

- Nodo 2: FIR pasa-bajas de 129 taps, Hamming, 8192 Hz, corte 1350 Hz.
- Nodo 3: FFT/IFFT espectral adaptativa v2, FFT 1024, salto 512, Hann periódica e historial de 8 ventanas.

Las dos salidas se escriben simultáneamente mediante el DAC interno de 8 bits:

- GPIO25 / DAC1: FIR del Nodo 2.
- GPIO26 / DAC2: FFT v2 del Nodo 3.

## Estado de validación

- El header FIR C++ fue comparado con `scipy.signal.lfilter`: error absoluto máximo aproximado `1.68e-7` en el registro usado para la prueba.
- El port C++ del Nodo 3 se comparó con la referencia Python streaming-compatible en 15 corridas (5 condiciones × 3 repeticiones). Error absoluto máximo `2.18e-6`.
- El `.ino` pasó una comprobación sintáctica usando cabeceras API simuladas. **No se ha compilado con el core Arduino-ESP32 real ni probado en una ESP32 física.**
- El tiempo nativo de PC no es una medición de rendimiento del ESP32. Medir `DSP+DAC pack`, `I2S write`, underflows/continuidad I2S y la latencia real cuando haya hardware.

La variante C++ de FFT es streaming-compatible y **no modifica ventanas previas retroactivamente**. Por ello no coincide con los mejores resultados del validador Python offline que podía usar un look-back. Las cifras esperables en esta variante son aproximadamente:

| Caso | Mejora media SNR v2 streaming |
|---|---:|
| Tono de 1792 Hz | +19.00 dB |
| Ruido blanco | +10.33 dB |
| Ruido 850–1300 Hz | +4.76 dB |
| Tres tonos fuera de banda | +19.31 dB |
| Ruido impulsivo | +0.40 dB |

La detección espectral y el FIR presuponen que la banda útil termina cerca de 1350 Hz. Si el proyecto debe conservar contenido útil por encima de esa frecuencia, hay que rediseñar y volver a validar ambos métodos antes de cargar este firmware.

## Compatibilidad y librerías

- ESP32 clásico solamente (por ejemplo ESP32 Dev Module / ESP-32D). No ESP32-S2/S3/C3.
- Arduino-ESP32 3.x / ESP-IDF 5.x.
- Usa el driver I2S legado `driver/i2s.h` para activar el DAC integrado por I2S0. No incluir a la vez la API nueva `i2s_std.h` en este sketch.
- El DAC interno es de 8 bits. No representa una salida de audio de alta fidelidad.

## Conexión Nodo 1 → Nodo 2/3

| Nodo 1 | Nodo 2/3 | Función |
|---|---|---|
| GPIO17 (TX2) | GPIO16 (RX2) | UART2, 921600 baudios |
| GND | GND | Referencia común |

Es un enlace unidireccional. El GPIO17 del Nodo 2/3 no se conecta.

No conectar directamente líneas TX a 5 V ni usar una interfaz RS-232. La UART ESP32 es lógica de 3.3 V.

## Salidas analógicas

- GPIO25: ruta FIR.
- GPIO26: ruta FFT v2.
- GND de los instrumentos y filtros debe ser común con la ESP32.
- El DAC entrega valores de 0–3.3 V aproximadamente, centrados en 128/255 para una señal normalizada bipolar.
- Para observar una señal suavizada, colocar un filtro de reconstrucción RC en cada salida. Una primera prueba puede reutilizar 4.7 kΩ en serie y 10 nF a GND (fc ≈ 3.39 kHz), pero comprobar su efecto en amplitud y forma de onda.
- No conectar un parlante directamente al GPIO DAC; utilizar una etapa de amplificación/buffer adecuada.

## Carga

1. Copiar toda esta carpeta `nodo2_nodo3_procesamiento` dentro de `implementacion_embebida`.
2. Abrir `nodo2_nodo3_procesamiento.ino` en Arduino IDE.
3. Seleccionar **ESP32 Dev Module** (ESP32 clásico), core Arduino-ESP32 3.x y el puerto correcto.
4. Compilar y cargar.
5. Abrir Monitor Serial por USB a 115200 baudios.
6. Conectar TX17 del Nodo 1 a RX16 de esta ESP32 y unir GND.
7. Cargar e iniciar el firmware del Nodo 1. El Monitor Serial de la segunda placa debe informar recepción de bloques y CRC sin errores.

El Monitor Serial USB debe estar cerrado si otra aplicación pretende usar el mismo puerto USB. El enlace de datos entre placas es UART2, no USB.

## Temporización y alineación de rutas

- Nodo 1 entrega 1024 muestras nominales cada 125 ms.
- El FIR129 aporta un retardo de grupo de 64 muestras (7.8125 ms). Se añade un buffer de 448 muestras para alinear la ruta FIR con el hop de latencia de la ruta FFT; ambas señales llegan alineadas nominalmente con un retardo de 512 muestras (62.5 ms) de procesamiento, sin contar la adquisición, el envío UART ni buffers I2S.
- El Nodo 3 procesa cada bloque en dos hops de 512 muestras. La primera mitad de salida del primer bloque se inicializa en silencio mientras se completa la primera ventana; después el flujo queda estable.
- El `DSP+DAC pack` impreso mide FIR + FFT + conversión de muestras a formato DAC antes de entregar el bloque a I2S. `I2S write` mide la llamada de envío al driver. Ninguno por separado es una medición de latencia extremo a extremo ni prueba por sí solo el consumo temporal real del DAC.

## Protocolo N1B2 recibido

Header de 26 bytes:

`magic[4], version[1], flags[1], sequence[4], fs_adc_configured[4], fs_out_nominal[4], raw_count[2], out_count[2], dma_read_us[4]`

Después vienen 1024 muestras float32 little-endian (4096 bytes) y CRC32-IEEE de header+payload (4 bytes). Tamaño total: 4126 bytes. El receptor busca el magic, valida CRC, longitud, versión y frecuencia nominal de salida; cuenta saltos de secuencia.

## Limitaciones pendientes de validar físicamente

1. Calibrar la tasa ADC real del Nodo 1: 8192 Hz de salida es nominal hasta comprobarla con un tono de frecuencia conocida.
2. Confirmar polarización y amplitud de la entrada ADC; no aplicar tensiones negativas ni superiores al rango de la placa.
3. Verificar pin/channel mapping DAC25 y DAC26 con osciloscopio; confirmar que GPIO25 emite FIR y GPIO26 FFT.
4. Medir frecuencia de muestreo DAC, jitter, pérdidas UART, overflow ADC, latencia de extremo a extremo y calidad de reconstrucción.
5. Confirmar que la banda útil del proyecto no necesita señales por encima de 1350 Hz.
6. Validar cinco condiciones requeridas y una condición desconocida en las ESP32, no solo en Python.
