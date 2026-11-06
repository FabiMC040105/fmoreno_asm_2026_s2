# Banco experimental P1-P6 — CE1110 Reducción de ruido

## Alcance y reglas de validez

**Estado:** procedimiento propuesto, NO son resultados de laboratorio. El procesador FIR y FFT/IFFT continúa en la ESP32 B; PC solo genera señales, registra logs y permite análisis de referencia. Se requiere **tres repeticiones mínimas de P1 a P5** y **P6 desconocida, definida por el profesor**. Registrar versión del firmware/commit, microcontroladores, cableado, alimentación y hora de cada ensayo.

## Montaje

- ESP32 A, Nodo 1: micrófono electret analógico a GPIO34, muestreo ADC continuo + decimador; salida TX GPIO17.
- ESP32 B (NodeMCU ESP-32S), Nodo 2/3: UART RX GPIO16; salida FIR GPIO25, salida espectral GPIO26, GND común. GPIO25 y GPIO26 son **DAC de señal**, NO salidas de potencia para el altavoz. Usar amplificador de audio adecuado con alimentación y referencia compatibles.
- Cada ESP32 por su propio USB. Con placas **desenergizadas**, conectar UART GPIO17 -> GPIO16 y GND -> GND; comprobar que no haya corto, y **no unir 5V ni 3V3 entre placas**.
- Laptop/altavoz como fuente acústica para P1-P5; dejar distancia/volumen constantes. Evitar que el altavoz de salida retroalimente el micrófono; para medir audio usar audífonos/registrador/amplificador bien aislado.
- Foto del montaje y conexiones; identificación de pines, fuente y módulo amplificador. El montaje de la foto enviada aún no permite verificar individualmente todas las conexiones o tensiones: revisarlas con alimentación desconectada.

## Matriz mínima

| Prueba | Entrada útil | Ruido | Evidencia específica | Repeticiones |
|---|---|---|---|---|
| P1 | tono sinusoidal (p.ej. 512 Hz) | tono separado (p.ej. 1792 Hz) | espectros antes/después y atenuación del tono | 3 |
| P2 | 3 tonos (p.ej. 256, 512, 1024 Hz) | ruido de alta frecuencia | reconstrucción de los 3 tonos y delta SNR | 3 |
| P3 | audio del profesor o señal arbitraria | ruido de banda ancha | escucha comparativa, MSE, energía conservada | 3 |
| P4 | transitorios/pulsos | impulsos de ruido | forma temporal, picos, latencia y efecto del filtro | 3 |
| P5 | señal útil conocida | ruido 850–1300 Hz con solapamiento | compromiso entre rechazo y distorsión útil | 3 |
| P6 | señal desconocida presentada por profesor | condición desconocida | adaptación, medición, explicación de desempeño | según defensa |

Los valores numéricos de tonos y bandas en esta tabla son **estímulos de ensayo propuestos**, no valores obligatorios impuestos por el enunciado. Si el docente especifica otros, obedecer su prueba real. El generador incluido crea P1–P5, tres repeticiones con semillas distintas y WAV limpio/ruido/mezcla. P6 no se debe anticipar.

## Secuencia de ejecución para cada repetición

1. Comprobar montaje apagado y seguridad eléctrica, conectar USB, ver ambos arranques y bloques `N1B2` sin errores CRC ni pérdida. Confirmar DAC funcionando con osciloscopio o carga de alta impedancia **antes** de conectar amplificador.
2. Abrir `registrar_serial.py` con `--prueba P1 --repeticion 1 --segundos 15`; mirar el contador de bloques. El puerto serie de la ESP32 B es **115200**; cerrar Monitor Serial de Arduino antes de abrir Python.
3. Reproducir el archivo `P1_rep1_limpia.wav` (sin ruido). Esta etapa ayuda a obtener **referencia limpia capturada a través de la misma ruta física**. Reproducir después `P1_rep1_mezcla.wav` al mismo volumen y distancia; registrar entradas/salidas por instrumentos si se quieren MSE y SNR de verdad.
4. Guardar capturas de pantallas del espectro, forma de onda, audio original/FIR/FFT, CSV telemetría y foto del montaje. Registrar variaciones de volumen, distancia y ruido ambiental.
5. Repetir rep 2 y rep 3 para P1. Continuar P2, P3, P4 y P5. Preparar para P6 sin fijar frecuencia/contenido de antemano.
6. Evaluar evidencia por ruta **FIR y FFT sobre misma entrada**, resumir promedio y desviación estándar de los tres ensayos y discutir limitaciones (en especial solapamiento P5).

## Telemetría que entrega el receptor

Cada 8 bloques (~1 s nominal), el firmware instrumentado emite una línea `MTR,...`. `registrar_serial.py` la guarda en CSV con identificación de prueba/repetición y hora PC. Contiene `adc_flags`, bloques aceptados, errores CRC/formato, saltos de secuencia, errores DAC, `captura_adc_us`, `dsp_us`, `i2s_write_us`, heap libre/mínimo y bytes reservados FFT, RMS de entrada/FIR/FFT, porcentaje de **energía TOTAL** a la salida y atenuación estimada de un tono conocido. `dsp_us` y `i2s_write_us` son medidas locales, no latencia extremo a extremo. La ESP32 NO tiene reloj sincronizado con la otra placa.

- `mse_*`, `snr_entrada_db`, `snr_*_db`, `delta_snr_*`, `energia_util_*_pct`: se dejan **en blanco** en el CSV hasta contar con muestras **limpias capturadas**, entradas contaminadas y salidas **alineadas**. No sustituir automáticamente por cifras de simulación Python.
- `atenuacion_tono_*_db` es válida solo cuando el tono indicado en `metricas_receptor.h` existe de forma suficiente en la entrada y representa interferencia, p.ej. P1 1792 Hz. Fuera de ese caso no llamar a ese valor "atenuación del ruido".
- `energia_total_*_pct` puede ser pequeña porque se eliminó sonido útil, NO demuestra conservación de energía útil.
- Para evaluación con referencia real, guardar CSV con columnas `clean,input,fir,fft`, muestreadas a la misma frecuencia **efectiva** y alineadas. Ejecutar `calcular_metricas_referencia.py`. Las muestras deben venir de adquisición **física**, por ejemplo registrador multipista/analizador externo o modo especial de captura (no incluido). Un WAV del generador no representa directamente la señal tras altavoz, aire y micrófono.
- Para latencia extremo a extremo medir diferencia de un flanco/pulso reconocible en **entrada analógica y DAC** con un instrumento de tiempo común (osciloscopio, analizador o grabador multicanal); no sumar supuestos como si fuera medición. Latencia algorítmica nominal de Nodo 3 = 512/8192 = 62.5 ms, además de captura de bloque, UART, cómputo y FIFO DAC.

## Criterios a acordar antes de presentar resultados

- Integridad UART: cero CRC erróneos y cero gaps durante cada ensayo como objetivo de ingeniería.
- Sin saturación ADC (flag `adc_flags=0`) como objetivo de calidad; verificar min/max del micrófono.
- Cómputo e I2S: sin bloqueos y tiempo medio y máximo bien documentados; constatar que el receptor no pierda bloques.
- La mejora de SNR, el MSE y la conservación de energía deben compararse **contra su respectiva referencia**, no contra una señal digital ideal ajena al montaje.
- No declarar resultados P1-P6 hasta ejecutarlos físicamente. P6 es sorpresa y no corresponde hacerle resultados inventados.

## Columnas de registro por ensayo

`fecha, prueba, repetición, señal útil, interferencia, banda útil, volumen/distancia, firmware_SHA, fs_adc_efectiva, fs_dsp, tasa_dac, N, CRC, gaps, saturaciones, heap_min, dsp_us, i2s_us, latencia_fisica_ms, SNR_entrada, SNR_FIR, SNR_FFT, delta_SNR_FIR, delta_SNR_FFT, MSE_FIR, MSE_FFT, energia_util_FIR, energia_util_FFT, atenuacion_tono_FIR, atenuacion_tono_FFT, observaciones`

Si el campo no es físicamente medible con el montaje actual, escribir `N/D — sin referencia limpia` u otra causa precisa. No reportar como cero.

## Brechas del firmware vigente que conviene declarar en la defensa

- **Nodo 1:** el firmware consultado captura por ADC/DMA, aplica antialias y transmite bloques, pero NO implementa todavía una FFT de diagnóstico propia dentro del Nodo 1. Si la rúbrica la exige, sigue siendo una tarea pendiente independiente del banco de métricas.
- **Nodo 2/3:** el tratamiento espectral v2 usa un supuesto de banda útil hasta 1350 Hz; conservar voz o tonos útiles por encima de esa frecuencia requerirá rediseño.
- Los ensayos con microfono pueden tener saturación, diferencias de nivel acústico, realimentación y variaciones en las distancias. No atribuir automáticamente cada mejora al filtro si no hay control experimental.
