# Nodo 3 – prueba del filtrado espectral en ESP32 (protocolo serial v2)

Esta versión incluye la corrección de memoria y de recepción serial.

## Correcciones incluidas

- Se conserva un solo arreglo global de 16384 muestras float32; la salida se reconstruye in-place.
- La máscara de bins está empaquetada a 1 bit por bin.
- `Serial.setRxBufferSize(8192)` se configura antes de `Serial.begin()`.
- La ESP32 confirma `READY_DATA,n` después de validar el comando y antes de que Python transmita el arreglo.
- Python envía los datos en fragmentos de 512 bytes con una pequeña pausa entre fragmentos.
- La lectura de entrada en la ESP32 comprueba que lleguen todos los bytes y tiene timeout por inactividad.

## Parámetros del algoritmo

- FFT: 1024 puntos.
- Hop: 512 muestras (50 %).
- Ventana: Hann periódica.
- Umbral: relativo al máximo de magnitud de cada ventana.
- Ganancia: 0.1 para bins por debajo del umbral; 1.0 para los demás.
- `LEARN`: aprende una máscara a partir de la mezcla contaminada.
- `REPLAY`: aplica esa misma máscara a la referencia limpia o al ruido.
- Máximo: 16384 muestras.
- UART USB: 921600 baudios.

## Instalación

1. Sustituye tanto `nodo3_fft_test.ino` como `fft_ola.h` en el sketch que estás usando; lo más sencillo es abrir el `.ino` incluido aquí y cargarlo.
2. Selecciona tu placa ESP32 y puerto COM.
3. Carga el firmware actualizado.
4. Cierra el Monitor Serial.
5. Instala dependencias: `py -m pip install numpy pyserial`.
6. Ejecuta desde la carpeta `scripts`:

   `py probar_fft_esp32.py --port COM8 --tarea1 "RUTA_COMPLETA_A_tarea1"`

## Protocolo

Host -> ESP32: línea ASCII `LEARN,n,1024,0.10` o `REPLAY,n,1024,0.10`.
ESP32 -> Host: línea ASCII `READY_DATA,n`.
Host -> ESP32: `n` valores float32 little-endian, enviados por fragmentos.
ESP32 -> Host: `BEGIN,n,total_us,max_frame_us,frame_count`, seguido del resultado binario y `END`.

## Alcance

Sigue siendo un firmware de validación por USB Serial. No implementa todavía ADC, DAC/PWM ni comunicación entre nodos, y procesa registros completos en memoria; no es aún el firmware final de tiempo real.
