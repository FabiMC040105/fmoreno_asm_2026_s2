# Implementación embebida preliminar — Nodos 1, 2 y 3

Este paquete contiene la primera integración de firmware para dos ESP32 clásicas:

- **ESP32 A:** Nodo 1, adquisición ADC continuo/DMA, FIR antialias y decimación 3:1.
- **ESP32 B:** Nodo 2 FIR129 y Nodo 3 FFT espectral v2 ejecutados en paralelo sobre el mismo bloque recibido. Las salidas salen por el DAC interno de GPIO25 y GPIO26.

> **Estado:** los algoritmos de decimación, FIR y FFT v2 se comprobaron con simulaciones y pruebas C++ nativas. Los `.ino` pasaron comprobaciones de sintaxis con cabeceras simuladas, no una compilación con el core Arduino-ESP32 real. No se ha realizado una prueba física de la integración. Este paquete es una base de integración para revisión y primeras pruebas, no evidencia de que el sistema completo ya funcione en placa.

## Árbol

```text
implementacion_embebida/
├── nodo1_adquisicion/
│   ├── nodo1_adquisicion.ino
│   ├── acondicionamiento_nodo1.h
│   ├── recibir_nodo1.py
│   └── pruebas de decimador
├── nodo2_nodo3_procesamiento/
│   ├── nodo2_nodo3_procesamiento.ino
│   ├── fir_esp32.h
│   └── fft_ola_v2_stream.h
└── nodo3_espectral_v2_validacion/
    ├── filtrado_espectral_v2_nolookback.py
    ├── validar_port_cpp.py
    ├── prueba_fft_v2.cpp
    ├── validacion_cpp_vs_python.csv
    └── datos_prueba/
```

## Hardware y cableado

Usar dos ESP32 clásicas (por ejemplo ESP32 Dev Module). Mantener alimentación USB independiente y unir GND.

| Señal | ESP32 A — Nodo 1 | ESP32 B — Nodo 2/3 |
|---|---|---|
| UART datos | GPIO17 TX2 | GPIO16 RX2 |
| Tierra | GND | GND |
| Entrada analógica | GPIO34 ADC1_CH6 | — |
| Salida FIR | — | GPIO25 DAC1 |
| Salida FFT | — | GPIO26 DAC2 |

El enlace UART es unidireccional. No se conecta el TX GPIO17 de la segunda placa. Los niveles son 3.3 V TTL; no utilizar RS-232 ni una señal de 5 V.

La entrada ADC debe mantenerse dentro del rango permitido de la placa. Una señal de audio bipolar debe polarizarse alrededor de un punto medio antes del ADC; no conectar directamente una señal que pueda bajar de GND. El firmware resta la media de cada bloque, pero eso ocurre **después** de la conversión y no evita el recorte analógico.

Las salidas GPIO25 y GPIO26 son DAC de 8 bits. Para medirlas, usar osciloscopio o una etapa buffer. Para suavizar imágenes de muestreo puede probarse un RC independiente por salida (por ejemplo 4.7 kΩ en serie y 10 nF a GND, fc aproximada 3.39 kHz), comprobando su atenuación. No conectar un parlante directamente al pin DAC.

## Parámetros nominales

| Parámetro | Valor |
|---|---:|
| Frecuencia ADC configurada | 24576 Hz |
| Bloque raw ADC | 3072 muestras |
| Antialias Nodo 1 | FIR 61 taps, Hamming, fc 3000 Hz |
| Decimación | 3:1 |
| Frecuencia de salida nominal | 8192 Hz |
| Bloque entre nodos | 1024 float32 = 125 ms |
| UART | 921600 baudios, 8N1 |
| Paquete N1B2 | 4126 bytes, CRC32-IEEE |
| Nodo 2 | FIR 129 taps, fc 1350 Hz, retardo 64 muestras |
| Nodo 3 | FFT 1024, hop 512, Hann periódica, historial 8 frames |
| Salida de audio | I2S0 interno, DAC GPIO25/GPIO26, 8 bits |

24576 Hz es el valor configurado/nominal del controlador ADC. Antes de interpretar frecuencias debe calibrarse la tasa efectiva con una señal física conocida y registrar la versión exacta del core/placa. La salida 8192 Hz todavía no es una medición calibrada.

## Orden recomendado de primera prueba

1. **Sin unir placas:** compilar y ejecutar pruebas nativas del FIR y FFT. El validador C++ está en `nodo3_espectral_v2_validacion`.
2. **Nodo 1 hacia PC:** cargar el sketch de Nodo 1 y validar paquetes con un adaptador USB-UART TTL 3.3 V usando `recibir_nodo1.py`.
3. **Nodo 2/3 solo:** compilar y cargar el sketch receptor de la segunda ESP32. Comprobar en monitor USB que arranque I2S/DAC.
4. **Enlace entre ESP32:** unir GPIO17→GPIO16 y GND→GND, luego iniciar Nodo 1. Verificar CRC, secuencias y ausencia de `ADC_POOL_OVERFLOW`.
5. **Salidas:** observar GPIO25 y GPIO26 por separado con osciloscopio. Confirmar mapeo, frecuencia, amplitud y filtro de reconstrucción.
6. **Calibración:** inyectar un tono de frecuencia conocida y medir la salida nominal; ajustar y documentar la frecuencia efectiva antes de evaluar filtros.
7. **Medición en hardware:** guardar tiempo de procesamiento en placa, pérdidas de paquetes, saturación ADC, latencia de extremo a extremo y métricas MSE/SNR con referencia offline.

## Supuesto de banda útil

Tanto el FIR pasa-bajas del Nodo 2 como el detector tonal de Nodo 3 protegen una banda útil hasta aproximadamente 1350 Hz. Si el sistema debe conservar contenido útil por encima de ese límite (voz, música u otra señal), debe acordarse otra banda útil y rediseñarse/validarse el FIR y el detector. Una señal útil de 1795 Hz puede ser confundida con interferencia por la versión actual del Nodo 3.

## Qué no se debe afirmar todavía

- No afirmar que el ADC está calibrado a 24576 Hz efectivos ni que la salida ya está calibrada a 8192 Hz.
- No afirmar tiempo real del firmware completo con base en mediciones Python o C++ ejecutadas en PC.
- No afirmar reducción de ruido física: aún falta probar una señal contaminada real, la comunicación entre placas, los DAC y la reconstrucción.
- No usar el ADC continuo/I2S0 del Nodo 1 y el I2S0 DAC del Nodo 2/3 en la misma placa. Son placas distintas en este diseño.
