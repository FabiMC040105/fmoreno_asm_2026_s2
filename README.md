# Proyecto de reducción adaptativa de ruido — Rama `filtrosESP`

**Curso:** CE1110 — Proyecto grupal de reducción de ruido en tiempo real  
**Rama documentada:** `filtrosESP`  
**Plataforma de desarrollo:** Windows, Python, Arduino IDE y ESP32 clásica  
**Estado general:** prototipos de software y algoritmos validados parcialmente; integración física de los tres nodos pendiente.

> **Importante sobre el alcance de este README:** documenta el trabajo que está en la rama `filtrosESP` y los paquetes de integración preparados durante esta etapa. Los ZIP de integración más recientes se entregaron localmente en la conversación; no se deben considerar incorporados a GitHub hasta que se copien al repositorio y se haga el commit correspondiente.

---

## 1. Objetivo y arquitectura propuesta

El proyecto busca reducir ruido en una señal adquirida y procesada en tiempo real. La arquitectura que se está preparando usa **dos ESP32 clásicas** para implementar tres nodos lógicos:

1. **Nodo 1 — Adquisición:** conversión analógica-digital, acondicionamiento, eliminación de componente DC, antialias y entrega de bloques de muestras.
2. **Nodo 2 — Filtrado temporal:** filtro FIR pasa-bajas de 129 coeficientes.
3. **Nodo 3 — Filtrado espectral:** FFT/IFFT adaptativa por ventanas con solapamiento.

Los nodos 2 y 3 se ejecutan en paralelo en la segunda ESP32. Ambos reciben el mismo bloque proveniente del Nodo 1. No se aplica el FIR seguido por la FFT: son dos rutas independientes para poder comparar sus salidas.

```text
ESP32 A — Nodo 1
GPIO34 / ADC1 + DMA
        |
        v
FIR antialias + decimación 3:1
24576 Hz -> 8192 Hz nominales
        |
        | UART2: GPIO17 TX -> GPIO16 RX
        v
ESP32 B — Nodos 2 y 3
        |-------------------------|
        v                         v
Nodo 2: FIR129              Nodo 3: FFT/IFFT v2
        |                         |
        v                         v
GPIO25 / DAC1               GPIO26 / DAC2
        |                         |
        +-----------+-------------+
                    v
            Comparación de salidas
```

La asignación física propuesta es:

| Función | ESP32 A — Nodo 1 | ESP32 B — Nodos 2/3 |
|---|---|---|
| Entrada ADC | GPIO34 (ADC1_CHANNEL_6) | — |
| UART de datos | GPIO17 (TX2) | GPIO16 (RX2) |
| Salida FIR | — | GPIO25 (DAC1) |
| Salida espectral | — | GPIO26 (DAC2) |
| Tierra | GND común | GND común |

El enlace UART es unidireccional. Se requiere lógica TTL de 3.3 V; no se debe usar RS-232 ni aplicar 5 V directamente a los pines ESP32.

---

## 2. Contenido existente en la rama `filtrosESP`

### 2.1 `tarea1/` — Referencia de señales, filtros y métricas

Esta carpeta contiene la base de software del proyecto y los casos sintéticos reproducibles:

- `src/generacion_senales.py`: genera una señal útil multitono (256, 512 y 1024 Hz), ruido controlado y mezclas con semillas reproducibles. La configuración base utiliza `fs = 8192 Hz`, bloques de 1024 muestras y registros de 2 segundos.
- `src/filtros_temporales.py`: contiene el filtro temporal **IIR Butterworth de orden 12**, representado mediante seis secciones SOS. Conserva el estado entre bloques.
- `src/filtrado_espectral.py`: contiene la primera versión Python del filtro espectral FFT/IFFT con ventana Hann periódica, salto del 50 %, umbral relativo y reconstrucción overlap-add (OLA) normalizada.
- `src/comparar_metodos.py`: compara la señal sin filtrar, el método temporal IIR y el método espectral; genera métricas y figuras.
- `src/temporal_datos.py`: carga y valida las señales, configuración y SNR de entrada.
- `pruebas/`: pruebas unitarias y de integración.
- `metadatos/configuraciones.json`: configuración de los experimentos.
- `resultados/`: resultados, métricas y figuras generadas.
- `notebook.ipynb`: notebook de análisis.

**Nota sobre los filtros temporales:** `tarea1/src/filtros_temporales.py` implementa el IIR Butterworth usado en la comparación académica original. El prototipo embebido del Nodo 2 usa un **FIR de 129 taps**. Son dos diseños distintos y no deben presentarse como si fueran el mismo filtro. La decisión final de cuál se documentará como método temporal del sistema debe quedar coordinada con el equipo y el informe.

Los tres casos iniciales de referencia son:

| Caso | Ruido agregado | SNR objetivo de entrada |
|---|---|---:|
| 1 | Interferencia sinusoidal de 1792 Hz | 5 dB |
| 2 | Ruido blanco gaussiano | 3 dB |
| 3 | Ruido limitado aproximadamente a 850–1300 Hz | 0 dB |

El caso 3 es un caso de solapamiento: el ruido ocupa parte de la banda donde también hay contenido útil.

### 2.2 `prueba_embebida/FIR_ESP32_prueba/` — Prototipo del Nodo 2

Contiene el sketch de prueba de FIR para una ESP32, el header C++ de coeficientes y la herramienta Python para enviar/recibir bloques por USB serial.

Parámetros del FIR embebido:

| Parámetro | Valor |
|---|---:|
| Frecuencia de diseño | 8192 Hz |
| Coeficientes | 129 |
| Ventana | Hamming |
| Tipo | Pasa-bajas |
| Frecuencia de corte | 1350 Hz |
| Retardo de grupo | 64 muestras = 7.8125 ms |

La prueba envía bloques `float32` desde la computadora a la ESP32 y compara la salida embebida con `scipy.signal.lfilter`. El historial del FIR se conserva entre bloques.

**Alcance de esa prueba:** valida el cálculo FIR y su tiempo de ejecución en la placa. No integra todavía el ADC del Nodo 1, la comunicación UART entre placas ni la salida DAC definitiva.

En una ejecución anterior de esta prueba se midió un tiempo de cálculo cercano a 5.13 ms por bloque, con máximo aproximado de 5.16 ms, y error numérico muy pequeño frente a SciPy. Los tiempos medidos excluyen adquisición, DAC/PWM y comunicaciones entre nodos.

### 2.3 `prueba_embebida/Nodo3_FFT_ESP32_serial_v2/` — Prototipo inicial del Nodo 3

Contiene el sketch de prueba de FFT/IFFT, el procesamiento OLA y un programa Python de evaluación por USB serial.

Parámetros principales del prototipo inicial:

- FFT de 1024 puntos.
- Ventana Hann periódica.
- Salto de 512 muestras (50 % de solapamiento).
- Umbral relativo inicial de 0.10.
- Ganancia de 0.1 para los bins cuya magnitud cae por debajo del umbral; ganancia 1.0 para los demás.
- Máscara espectral empaquetada y simétrica para conservar una señal real al reconstruir.

El programa inicial permite aprender una máscara de un registro y reproducirla en otra señal. La prueba procesa registros completos y los transfiere por USB serial; **no equivale a un procesador continuo conectado al ADC/DAC**.

---

## 3. Pruebas y resultados de software

### 3.1 Comparación sintética FIR contra FFT inicial

Se creó y ejecutó una simulación que aplica la misma señal de entrada a dos ramas independientes: FIR129 y FFT espectral inicial. Se hicieron tres repeticiones por cada caso.

Promedios de mejora de SNR obtenidos en esa simulación:

| Caso | FIR129 — Nodo 2 | FFT inicial — Nodo 3 |
|---|---:|---:|
| 1. Tono de 1792 Hz | +44.67 dB | +0.00 dB |
| 2. Ruido blanco | +4.89 dB | +10.40 dB |
| 3. Ruido 850–1300 Hz | +0.05 dB | +0.18 dB |

Lectura de los resultados:

- El FIR funciona muy bien cuando la interferencia está fuera de la banda de paso.
- El método espectral inicial tiene ventaja con ruido blanco.
- Ambos tienen dificultades con ruido cuyo espectro se solapa con el contenido útil.
- La FFT inicial prácticamente no atenúa un tono interferente dominante porque su regla favorece conservar bins de magnitud elevada.

Los CSV de esta simulación incluyen además MSE, energía útil conservada, atenuación de ruido inyectado y tiempos de PC. Estos tiempos **no son tiempos de ESP32**.

### 3.2 Mejora del Nodo 3 — FFT espectral v2

Se preparó una segunda versión del método espectral para resolver, entre otros, el problema del tono interferente dominante. Incorpora criterios adicionales de detección espectral, persistencia y concentración en frecuencia, además de una variante causal apta para procesar bloques en línea.

Se evaluaron cinco condiciones con tres repeticiones:

1. Tono interferente de 1792 Hz.
2. Ruido blanco gaussiano.
3. Ruido parcialmente solapado entre 850 y 1300 Hz.
4. Tres tonos interferentes fuera de banda.
5. Ruido impulsivo.

La variante C++ de Nodo 3 compatible con streaming fue comparada contra una referencia Python equivalente. El error absoluto máximo informado fue aproximadamente `2.18e-6` en las pruebas realizadas.

Mejoras medias de SNR de la variante streaming evaluada:

| Condición | Mejora media aproximada |
|---|---:|
| Tono de 1792 Hz | +19.00 dB |
| Ruido blanco | +10.33 dB |
| Ruido 850–1300 Hz | +4.76 dB |
| Tres tonos fuera de banda | +19.31 dB |
| Ruido impulsivo | +0.40 dB |

Estas cifras pertenecen a la variante streaming-compatible, no a la versión Python offline que puede usar información de ventanas futuras/anteriores. No se deben mezclar ambas tablas.

**Supuesto de banda útil:** la detección tonal actual supone que el contenido útil termina aproximadamente en 1350 Hz. En una prueba adicional, un tono útil de 1795 Hz pudo confundirse con interferencia. Si el proyecto necesita conservar voz, música u otra señal con contenido útil por encima de 1350 Hz, primero se debe acordar la banda útil y rediseñar/validar el detector y el FIR.

### 3.3 Nodo 1 — Prueba física inicial de ADC/DMA

Se probó un primer sketch de adquisición ADC continuo con DMA en GPIO34. La configuración inicial de 8192 Hz fue rechazada por el controlador con el error `ADC sampling frequency out of range`. Para continuar la prueba se cambió temporalmente a 20000 Hz.

Se recibieron cinco bloques por USB serial con CRC correcto. Sin embargo, las muestras estaban mayormente en cero y el máximo observado fue solo 162 cuentas ADC. Esa ejecución confirma recepción de paquetes y CRC, pero **no demuestra que la entrada analógica estuviera correctamente conectada, polarizada o adquirida**.

Se conservan esos datos como diagnóstico; no deben utilizarse como prueba de calidad de señal ni como validación de la tasa ADC.

---

## 4. Integración embebida preliminar preparada

Durante esta etapa se preparó, como paquete local independiente, `Implementacion_Preliminar_Nodos_1_2_3.zip`. Incluye una primera integración de firmware para dos ESP32 clásicas. El paquete debe copiarse al repositorio y revisarse antes de considerarlo parte efectiva de la rama.

### 4.1 Nodo 1 propuesto: ADC/DMA + antialias + decimación

Configuración prevista:

| Parámetro | Valor nominal |
|---|---:|
| ADC | GPIO34 / ADC1_CHANNEL_6 |
| Frecuencia ADC configurada | 24576 Hz |
| Muestras raw por bloque | 3072 |
| FIR antialias | 61 taps, Hamming, corte 3000 Hz |
| Factor de decimación | 3:1 |
| Frecuencia de salida nominal | 8192 Hz |
| Muestras de salida | 1024 `float32` |
| Periodo nominal de bloque | 125 ms |

La salida de 8192 Hz es **nominal** hasta medir la frecuencia efectiva del ADC con una señal física conocida. La prueba C++ nativa del acondicionamiento/decimador se comparó con Python y mostró una diferencia máxima inferior a `1e-6` en la escala normalizada utilizada. Esto valida la implementación matemática en software, no el reloj de muestreo real del ESP32.

El payload se normaliza aproximadamente a `[-1, 1]` después de quitar la media del bloque; no representa voltios calibrados.

### 4.2 Protocolo Nodo 1 → Nodo 2/3

La integración preliminar define un paquete binario `N1B2`:

| Campo | Bytes |
|---|---:|
| Magic `N1B2` | 4 |
| Versión | 1 |
| Flags | 1 |
| Secuencia | 4 |
| Frecuencia ADC configurada | 4 |
| Frecuencia de salida nominal | 4 |
| Número de muestras raw | 2 |
| Número de muestras de salida | 2 |
| Tiempo de lectura DMA | 4 |
| Payload: 1024 `float32` | 4096 |
| CRC32-IEEE | 4 |
| **Total** | **4126 bytes** |

El receptor valida magic, versión, tamaño, frecuencia nominal, CRC y secuencia de paquetes. El flag permite reportar muestras raw cercanas a los extremos del ADC.

### 4.3 Nodo 2/3 propuesto: dos filtros en paralelo

La segunda ESP32 recibe cada paquete y procesa dos copias lógicas del mismo bloque:

- **Nodo 2:** FIR129, 8192 Hz, corte 1350 Hz, Hamming, estado conservado entre bloques.
- **Nodo 3:** FFT/IFFT espectral v2, FFT 1024, hop 512, ventana Hann periódica e historial de ventanas.

Salidas propuestas:

- GPIO25 / DAC1: salida del FIR.
- GPIO26 / DAC2: salida del filtrado espectral.

El DAC interno del ESP32 clásico es de 8 bits; las salidas necesitan medición y, para una señal suavizada, un filtro de reconstrucción analógico apropiado. Un RC de 4.7 kΩ y 10 nF puede servir como primer experimento de laboratorio (fc aproximada 3.39 kHz), pero hay que observar su efecto real. No conectar un parlante directamente a un GPIO DAC.

El firmware preliminar incluye mediciones separadas para `DSP+DAC pack` e `I2S write`. Ninguna equivale por sí sola a latencia extremo a extremo ni demuestra que el DAC haya reproducido todas las muestras sin interrupciones.

### 4.4 Estado real de la integración

- El FIR129, el decimador y la FFT v2 cuentan con pruebas de referencia en software/C++ nativo.
- Los sketches `.ino` pasaron comprobaciones sintácticas con cabeceras API simuladas.
- Los sketches **no se han compilado todavía con la instalación real de Arduino-ESP32 del compañero**.
- La integración de dos ESP32 no se ha probado físicamente.
- No hay todavía mediciones físicas completas de latencia, pérdidas UART, overflow DMA, tasa efectiva ADC/DAC, calidad analógica ni reducción de ruido real.

Por tanto, el paquete es una **base preliminar para revisión y primera puesta en marcha**, no una versión final validada.

---

## 5. Consideraciones obligatorias antes de probar con hardware

Esta sección debe revisarse antes de cargar los sketches.

### 5.1 Modelo de placa y compatibilidad del core

- La integración está preparada para **ESP32 clásico** (por ejemplo ESP32 Dev Module / ESP-32D). No asumir compatibilidad con ESP32-S2, S3 o C3.
- El Nodo 1 utiliza `esp_adc/adc_continuous.h`, correspondiente al driver ADC continuo de ESP-IDF 5.x / Arduino-ESP32 3.x.
- El sketch de Nodo 2/3 utiliza la API I2S legado `driver/i2s.h` para el DAC interno. La API I2S cambió entre versiones mayores de Arduino-ESP32; comprobar que compile con la versión exacta instalada. No mezclar el driver legado y la nueva API I2S en el mismo periférico.
- Anotar el modelo exacto de ambas placas, versión de Arduino IDE y versión del paquete `esp32 by Espressif Systems` antes de depurar.

### 5.2 Uso de I2S0 y DMA

El ADC continuo del ESP32 clásico utiliza I2S0 como FIFO DMA de hardware. La salida DAC mediante I2S del otro ESP32 también utiliza I2S0. En la arquitectura propuesta no comparten el periférico porque están en **placas físicas distintas**. No iniciar ADC continuo e I2S DAC sobre I2S0 dentro de una misma ESP32 ni agregar otra función que ocupe I2S0.

El driver ADC continuo puede desbordar su pool DMA si el programa no consume los datos con suficiente rapidez. Vigilar los mensajes/contadores de overflow; no aceptar silenciosamente bloques parciales.

### 5.3 Tasa real de muestreo y decimación

- `24576 Hz` en el sketch del Nodo 1 es la frecuencia configurada, no una calibración independiente del reloj.
- `8192 Hz` después de la decimación es nominal hasta validar la frecuencia real.
- Inyectar un tono conocido, con frecuencia medida por una fuente confiable, analizarlo y registrar la frecuencia observada. Repetir hasta ajustar la tasa configurada y documentar la tasa efectiva.
- No cambiar a 20000 Hz y seguir entregando los bloques como si fueran 8192 Hz: eso desplaza todas las frecuencias interpretadas por los filtros.
- La decimación 3:1 requiere el FIR antialias antes de descartar dos de cada tres muestras; no quitar ese filtro.

### 5.4 Entrada ADC: polarización, amplitud y saturación

- GPIO34 no debe recibir tensiones negativas ni una señal que exceda el rango permitido según la atenuación configurada y la placa.
- Una señal de audio bipolar debe acondicionarse/polarizarse alrededor de un punto medio seguro antes del ADC. Restar la media digitalmente ocurre después de convertir y **no recupera una señal que ya se recortó en el ADC**.
- Verificar amplitud y offset con osciloscopio o multímetro antes de conectar.
- Las capturas iniciales con rango 0–162 y muchas muestras en cero no demuestran una entrada correcta. Pueden deberse a una señal débil, flotante, mal polarizada o a otra condición de conexión.
- Revisar mínimo, máximo, media, cantidad de muestras cercanas a cero y a escala completa, además del flag de saturación.

### 5.5 Banda útil del proyecto

El FIR129 y el detector tonal del Nodo 3 se han diseñado bajo el supuesto de que el contenido útil termina aproximadamente en 1350 Hz. Confirmar esa especificación con el equipo/docente. Si el contenido útil puede superar 1350 Hz, no cargar los filtros como definitivos: cambiar las especificaciones, rediseñar y volver a ejecutar todas las pruebas. Un tono útil de 1795 Hz puede confundirse con una interferencia en el detector espectral actual.

### 5.6 UART, CRC y secuencias

- Conectar Nodo 1 GPIO17 TX2 → Nodo 2/3 GPIO16 RX2 y GND → GND.
- UART propuesta: 921600 baudios, 8N1, lógica de 3.3 V.
- El enlace es unidireccional; no conectar el TX de la segunda placa.
- Comprobar magic `N1B2`, versión, tamaño esperado, CRC32 y contador de secuencia.
- Registrar paquetes corruptos, paquetes perdidos, saltos de secuencia, timeouts y reinicios.

### 5.7 Salidas DAC y reconstrucción

- Confirmar con osciloscopio que GPIO25 corresponde al FIR y GPIO26 al filtro espectral.
- El DAC es de 8 bits y tiene un rango de salida relacionado con VDD; la conversión bipolar a unipolar y el nivel medio deben revisarse en el código y medirse.
- Usar GND común para instrumentos y filtros.
- Evaluar un filtro de reconstrucción RC independiente por canal; no asumir que el ejemplo de 4.7 kΩ + 10 nF sea el óptimo.
- No conectar directamente un parlante ni una carga de baja impedancia al pin DAC. Utilizar buffer/amplificador adecuado.

### 5.8 Tiempo real y latencia

- Los tiempos Python son tiempos de PC. Los tiempos C++ nativos también son tiempos de PC.
- El tiempo de cálculo aislado del FIR medido en la prueba embebida anterior no incluye todo el camino físico.
- Medir por separado: lectura ADC/DMA, acondicionamiento/decimación, armado y transmisión UART, validación de paquete, DSP, escritura I2S/DAC y latencia extremo a extremo.
- Vigilar continuidad I2S, underflows, jitter, pérdidas UART y overflow del ADC.
- Comparar los tiempos con el periodo nominal de bloque de 125 ms. La ruta FFT usa ventanas de 1024 muestras con salto de 512; la alineación FIR/FFT incluida en el prototipo debe comprobarse en el osciloscopio y en las señales recibidas.

---

## 6. Orden recomendado de puesta en marcha física

1. **Identificar las placas y versiones:** fotografiar/leer el modelo exacto y anotar versión Arduino-ESP32.
2. **Compilar sin cargar:** compilar primero ambos sketches con el core instalado. Resolver errores de API, en especial ADC continuo e I2S legado, sin cambiar silenciosamente los parámetros DSP.
3. **Probar Nodo 1 solo:** conectar una fuente de señal conocida, acondicionada y polarizada; registrar muestras ADC, saturación, DMA y tasa efectiva.
4. **Probar Nodo 1 hacia una PC:** si se dispone de adaptador USB-UART TTL de 3.3 V, conectar RX del adaptador a GPIO17 y GND común; usar `recibir_nodo1.py` para validar paquetes N1B2/CRC/secuencias. No conectar TX del adaptador.
5. **Probar Nodo 2/3 solo:** cargar la segunda placa y verificar arranque e inicialización del DAC/I2S.
6. **Conectar ambas placas:** GPIO17 → GPIO16, GND común; confirmar recepción de bloques sin CRC inválido ni saltos.
7. **Comprobar las salidas:** medir GPIO25 y GPIO26 con osciloscopio y verificar amplitud, polarización, frecuencia y continuidad.
8. **Ejecutar la matriz de pruebas:** repetir las condiciones de prueba requeridas al menos tres veces, guardar parámetros y resultados, y reservar una condición desconocida para la evaluación/defensa si así lo exige la especificación.
9. **Documentar resultados reales:** MSE, SNR de entrada/salida, mejora de SNR, energía útil conservada, atenuación de ruido, latencia, pérdidas y consumo/memoria aproximados.

No declarar el sistema completo como validado hasta completar los pasos físicos y la matriz de pruebas.

---

## 7. Archivos/paquetes auxiliares preparados en esta etapa

Los siguientes paquetes se generaron localmente para la integración y validación. Su contenido no forma parte de la rama hasta copiarse al repositorio y hacer commit:

- `Simulacion_Tres_Nodos.zip`: ejecución de señales sintéticas y comparación de Nodo 1 sin filtro, FIR y FFT inicial.
- `Validacion_FFT_Nodo3_v2.zip`: segunda versión del algoritmo espectral, casos sintéticos adicionales, métricas, gráficas y notas.
- `Nodo1_Adquisicion_DMA_Decimador3.zip`: firmware preliminar de adquisición, FIR antialias, decimación y herramientas de recepción.
- `Implementacion_Preliminar_Nodos_1_2_3.zip`: integración preliminar de Nodo 1 y receptor de Nodo 2/3, con pruebas C++ nativas y documentación.

Antes de incorporarlos, revisar que las carpetas, parámetros y README coincidan con la versión que efectivamente compila el equipo.

---

## 8. Pendientes principales

- [ ] Acordar formalmente la banda útil y las especificaciones de señal.
- [ ] Decidir y documentar si la comparación académica debe incluir IIR Butterworth, FIR129 o ambos; explicar la diferencia entre el filtro IIR de `tarea1` y el FIR embebido.
- [ ] Compilar el Nodo 1 con la versión Arduino-ESP32 real.
- [ ] Compilar el Nodo 2/3 con esa misma instalación y resolver cualquier incompatibilidad de I2S legado.
- [ ] Calibrar la tasa efectiva ADC y comprobar la salida efectiva de 8192 Hz.
- [ ] Validar polarización, amplitud, offset y saturación de la entrada ADC.
- [ ] Probar el protocolo UART N1B2 entre las dos placas.
- [ ] Verificar DAC GPIO25/GPIO26 y filtros de reconstrucción.
- [ ] Medir latencia extremo a extremo, jitter, pérdidas, overflow y continuidad DAC/I2S.
- [ ] Repetir las pruebas exigidas en hardware y realizar la prueba desconocida.
- [ ] Guardar evidencia: fotos de conexiones, capturas de osciloscopio, logs seriales, CSV/JSON y configuración exacta.
- [ ] Incorporar los paquetes nuevos a la rama `filtrosESP` mediante commits revisados.

---

## 9. Referencias técnicas

- [Espressif — ADC Continuous Mode Driver (ESP32)](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc/adc_continuous.html): adquisición por DMA, limitaciones del driver y uso de I2S0 como FIFO DMA.
- [Espressif — ADC](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc.html): ADC, atenuación y calibración.
- [Espressif — DAC (ESP32)](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/dac.html): dos canales DAC de 8 bits en GPIO25 y GPIO26.
- [Arduino-ESP32 — Compatibility Guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/guides/core_compatibility.html): diferencias entre versiones del core.
- [Arduino-ESP32 — Migration guide 2.x to 3.0](https://docs.espressif.com/projects/arduino-esp32/en/latest/migration_guides/2.x_to_3.0.html): cambios mayores de API, incluido I2S.

---

## 10. Estado resumido

| Área | Estado |
|---|---|
| Generación de señales sintéticas | Implementada y reproducible |
| Comparación Python de filtros | Implementada |
| FIR129 en prueba aislada de ESP32 | Probado como cálculo aislado; falta integrar ADC/DAC/UART |
| FFT inicial en prueba serial ESP32 | Probada sobre registros; no equivale a streaming final |
| FFT v2 causal/streaming | Validada contra referencia C++/Python en software |
| Decimador 3:1 Nodo 1 | Validado en Python y C++ nativo; falta placa |
| Firmware preliminar de Nodo 1 | Preparado; compilación/captura física pendiente |
| Firmware preliminar Nodo 2/3 | Preparado; compilación/captura física pendiente |
| Comunicación UART entre ESP32 | Pendiente de prueba física |
| DAC y reconstrucción | Pendiente de prueba física |
| Sistema completo en tiempo real | No validado todavía |

**Conclusión:** la rama `filtrosESP` ya contiene una base de señales, métricas y prototipos de filtrado, y se preparó una integración preliminar de los tres nodos. El siguiente hito es la puesta en marcha real con las dos ESP32, verificando compatibilidad de compilación, adquisición calibrada, comunicación, salidas DAC y métricas de extremo a extremo.
**Curso:** CE1110 — Análisis de Señales Mixtas

**Proyecto:** Tarea 1 — Caracterización espectral y prototipado de filtros para reducción de ruido

**Período:** II Semestre 2026

**Institución:** Instituto Tecnológico de Costa Rica
