# Nodo 1 — ADC DMA, antialias y decimación 3:1

## Estado

Este es un **primer firmware de integración para ESP32 clásico**, basado en el ADC continuo de ESP-IDF 5.x. La referencia C++ del FIR/decimador fue compilada con `g++` y comparada contra Python. El sketch de Arduino pasó una comprobación sintáctica con cabeceras simuladas, pero **todavía debe compilarse con la versión exacta de Arduino-ESP32 del equipo y probarse en una placa con señal analógica real**.

## Configuración prevista

- Placa: ESP32 clásico / ESP32 Dev Module (no ESP32-S2/S3/C3).
- ADC: GPIO34, ADC1_CHANNEL_6.
- DMA: ADC continuo, formato `ADC_DIGI_OUTPUT_FORMAT_TYPE1`, 12 bits.
- Frecuencia ADC configurada inicialmente: 24576 Hz.
- Entrada por bloque: 3072 muestras.
- Acondicionamiento: FIR antialias de 61 taps Hamming, corte 3000 Hz, factor de decimación 3:1.
- Salida nominal: 8192 Hz, 1024 muestras cada 125 ms.
- UART2: TX GPIO17, RX GPIO16, 921600 baudios. Para conexión unidireccional Nodo1→Nodo2/3 se conecta GPIO17 del Nodo1 a GPIO16 del receptor y GND común.
- USB `Serial` es exclusivamente para mensajes de diagnóstico.

## Protocolo de salida N1B2

| Campo | Bytes | Tipo |
|---|---:|---|
| Magic `N1B2` | 4 | ASCII |
| Versión | 1 | uint8 |
| Flags | 1 | uint8; bit 0 = ADC raw alcanzó 0–2 o 4093–4095 |
| Secuencia | 4 | uint32 little-endian |
| Frecuencia ADC configurada | 4 | uint32 little-endian |
| Frecuencia de salida nominal | 4 | uint32 little-endian |
| Muestras raw | 2 | uint16 little-endian (3072) |
| Muestras salida | 2 | uint16 little-endian (1024) |
| Tiempo de lectura DMA | 4 | uint32 microsegundos; no equivale por sí solo a calibrar la frecuencia de muestreo |
| Payload | 4096 | 1024 float32 little-endian |
| CRC32 | 4 | CRC-32/IEEE del header + payload |

El payload es flotante normalizado aproximadamente a [-1,1] después de restar la media por bloque. No representa voltios calibrados.

## Carga en Arduino IDE

1. Copiar esta carpeta como `implementacion_embebida/nodo1_adquisicion/`.
2. Seleccionar una placa ESP32 clásica, por ejemplo **ESP32 Dev Module**.
3. Usar Arduino-ESP32 3.x / ESP-IDF 5.x con `esp_adc/adc_continuous.h`.
4. Abrir `nodo1_adquisicion.ino`, compilar y cargar.
5. Abrir Monitor Serial USB a 115200 para diagnóstico. Los paquetes de datos salen por GPIO17, no por USB.

## Pruebas de software incluidas

### Simulación Python del antialias y decimador

Desde esta carpeta, instalar las dependencias y ejecutar el archivo de prueba copiado desde la validación:

```powershell
py -m pip install -r requirements.txt
py probar_decimador_nodo1.py
```

El filtro probado mantiene la continuidad entre bloques y rechaza un tono de 5000 Hz que, sin antialias, aliasaría a 3192 Hz tras reducir 3:1.

### Prueba nativa del header C++

Si se tiene `g++` disponible:

```powershell
g++ -std=c++11 -O2 prueba_decimador.cpp -o prueba_decimador.exe
.\prueba_decimador.exe
```

Genera `salida_cpp_nodo1.csv` con 16384 muestras de salida (16 bloques a 8192 Hz nominales).

### Recepción y verificación de paquetes UART en una PC

Conectar un adaptador USB-UART **TTL de 3.3 V**: RX del adaptador a GPIO17 del Nodo1 y GND común. No conectar TX del adaptador ni usar niveles RS-232/5 V. Ejecutar:

```powershell
py -m pip install -r requirements.txt
py recibir_nodo1.py --puerto COMx --bloques 5
```

Cambiar `COMx` por el puerto del adaptador. Guarda CSV y JSON, valida CRC y reporta secuencias y rangos. Para conectar directamente otra ESP32, usar GPIO17 del Nodo1 → GPIO16 del receptor y GND común.

## Advertencias importantes antes de uso final

- `sample_freq_hz` de ESP-IDF es una frecuencia esperada/configurada. Hay reportes de una diferencia entre la tasa configurada y real en algunas versiones del controlador. Por tanto, el paquete marca 8192 Hz como **nominal**. Antes de que Nodo2/3 interpreten frecuencias, medir la tasa efectiva con un tono físico conocido y ajustar `ADC_FS_CONFIGURED_HZ` hasta que la salida sea realmente 8192 Hz.
- Método de ajuste: con un tono conocido `f_conocida`, analizar la salida suponiendo 8192 Hz y medir `f_observada`. Una corrección inicial es `ADC_FS_CONFIGURED_HZ_nuevo = ADC_FS_CONFIGURED_HZ_actual * f_observada / f_conocida`; volver a medir y refinar. No asumir que el factor es idéntico entre versiones.
- El ADC continuo utiliza I2S0 como FIFO DMA en el ESP32 clásico; no usar I2S0 simultáneamente en otra parte del programa.
- El buffer pool puede desbordarse. El sketch reporta el error, descarta el bloque parcial, reinicia el ADC y continúa; revisar que no aparezcan mensajes `ADC_POOL_OVERFLOW`.
- El ADC necesita señal analógica dentro de su rango y polarizada por encima de GND. Una señal alterna centrada en 0 V se recorta en la parte negativa. Las capturas previas 0–162 con muchos ceros no demuestran una entrada correcta.
- El FIR antialias y el FIR del Nodo2 suponen banda útil hasta ~1350 Hz. La detección de tonos del Nodo3 v2 usa este mismo supuesto. Confirmar formalmente el ancho de banda útil del proyecto.
- Los 3072 resultados raw y 1024 decimados forman 125 ms solo si la frecuencia efectiva es 24576 Hz. Medir y documentar la tasa real.
- Este sketch todavía no se ha compilado con Arduino IDE ni se ha probado en placa física en esta sesión.
