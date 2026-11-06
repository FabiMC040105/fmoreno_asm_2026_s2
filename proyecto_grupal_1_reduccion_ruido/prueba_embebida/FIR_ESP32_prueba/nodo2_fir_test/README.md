# Prueba del FIR en ESP32 (Nodo temporal, prueba de algoritmo)

## Qué prueba este paquete

Este firmware ejecuta en la ESP32 el FIR pasa bajas de 129 coeficientes diseñado en Python:

- `fs = 8192 Hz`
- `numtaps = 129` (orden 128)
- corte = `1350 Hz`
- ventana Hamming
- retardo de grupo = `64 muestras = 7.8125 ms`

La computadora envía bloques `float32` por USB serial. La ESP32 procesa cada bloque con el FIR en C++ y devuelve la salida. El script de Python compara la salida embebida con `scipy.signal.lfilter` y calcula las mismas métricas de `probar_FIR.py`.

**Importante:** esta es una prueba del algoritmo y del tiempo de cálculo en la ESP32. Todavía NO implementa el ADC de entrada, la salida DAC/PWM, la comunicación final entre nodos ni el sistema distribuido completo. El tiempo reportado excluye adquisición, salida y serial.

## Dónde colocar la carpeta

No se incorpora dentro de `tarea1`. Coloque la carpeta `nodo2_fir_test` en:

```text
proyecto_grupal_1_reduccion_ruido/
└── implementacion_embebida/
    └── nodo2_fir_test/
        ├── nodo2_fir_test.ino
        ├── fir_esp32.h
        ├── filtro_FIR.py
        ├── README.md
        └── scripts/
            └── probar_fir_esp32.py
```

El script busca automáticamente `proyecto_grupal_1_reduccion_ruido/tarea1` si se conserva esa estructura. Si la ubicación es distinta, utilice `--tarea1`.

## Paso 1: cargar el firmware

1. Copie `nodo2_fir_test` a la ubicación indicada.
2. Abra `nodo2_fir_test.ino` con Arduino IDE.
3. Seleccione la placa ESP32 clásica correspondiente (por ejemplo, **ESP32 Dev Module**) y el puerto COM correcto.
4. Compile y cargue el firmware.
5. Cierre el Monitor Serial antes de ejecutar el script de Python.

El sketch utiliza USB serial a `921600` baudios y un protocolo binario. No imprime texto en el puerto.

## Paso 2: preparar Python

Desde la terminal:

```powershell
py -m pip install numpy scipy pyserial
```

## Paso 3: probar un caso

Desde la raíz del paquete `FIR_ESP32_prueba`:

```powershell
py nodo2_fir_test/scripts/probar_fir_esp32.py --puerto COM6 --caso 1
```

Cambie `COM6` por el puerto de la ESP32. Repita con `--caso 2` y `--caso 3`.

Si el script no encuentra la carpeta `tarea1`, indique su ruta explícitamente:

```powershell
py nodo2_fir_test/scripts/probar_fir_esp32.py --puerto COM6 --caso 1 --tarea1 "C:\ruta\fmoreno_asm_2026_s2\proyecto_grupal_1_reduccion_ruido\tarea1"
```

Si el adaptador USB-serial no trabaja de forma estable a 921600, cambie `SERIAL_BAUD` en el sketch y ejecute el script con el mismo valor mediante `--baudrate`.

## Qué resultados debe compartir

El script guarda dentro de `resultados/`:

- `caso_X_resumen_esp32.json`: métricas y equivalencia numérica.
- `caso_X_metricas_esp32.csv`: resumen en CSV.
- `caso_X_tiempos_bloque.csv`: tiempo de cálculo FIR de cada bloque.
- `caso_X_salida_esp32.npy`: salida generada por la placa.

Criterio preliminar de equivalencia: error máximo absoluto ESP32–Python menor o igual a `5e-5`. Es una tolerancia de validación numérica propuesta para esta prueba, no un umbral impuesto por el enunciado. También se compara el tiempo máximo de cálculo FIR por bloque con el plazo nominal de `125 ms`.

## Qué falta después de esta prueba

Si la equivalencia y el tiempo de cálculo son satisfactorios, el siguiente paso es convertir la prueba de escritorio en el Nodo 2 real:

1. recibir el bloque desde el Nodo 1 mediante el enlace cableado;
2. validar longitud, número de bloque y CRC;
3. aplicar el FIR conservando el historial entre bloques;
4. reproducir la salida por DAC o PWM;
5. documentar y probar el filtrado analógico de reconstrucción;
6. medir la latencia total, no solamente el tiempo matemático del FIR.

No cargue este sketch en el ESP32 emisor de Semana 12. Es un firmware de prueba para una ESP32 que actuará temporalmente como procesador FIR.
