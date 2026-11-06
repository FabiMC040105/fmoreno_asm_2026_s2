# Instalación rápida de métricas sin modificar filtros

## 1. Preparación

En una **copia** local de la rama `filtrosESP`, localice:

`proyecto_grupal_1_reduccion_ruido/implementación_embebida/implementacion_embebida/nodo2_nodo3_procesamiento/`

Se esperan `nodo2_nodo3_procesamiento.ino`, `fir_esp32.h` y `fft_ola_v2_stream.h`.

El cambio instrumenta solamente el receptor y conserva algoritmo FIR129, FFT/IFFT v2, ADC, UART, protocolo N1B2 y DAC actual 32768 Hz.

Si sigue existiendo el fichero `prueba_fir.cpp` dentro de la carpeta `.ino`, **muévalo fuera del sketch**, porque Arduino intenta compilarlo y puede dar `multiple definition`. Guardarlo en carpeta de pruebas nativas. No borrar ningún `.h`.

## 2. Aplicación del parche

Descomprima este paquete en una carpeta independiente y ejecute desde su consola PowerShell:

```powershell
py aplicar_parche.py "C:\\RUTA_AL_REPO\\proyecto_grupal_1_reduccion_ruido\\implementación_embebida\\implementacion_embebida\\nodo2_nodo3_procesamiento"
```

El parche crea `nodo2_nodo3_procesamiento.ino.antes_metricas.bak` y copia `metricas_receptor.h` al sketch. Nunca se aplica por duplicado. **No ejecutarlo dentro de la carpeta de este ZIP** si ahí no está el `.ino` original.

Alternativa manual: copiar `metricas_receptor.h` a la carpeta del `.ino`, agregar `#include "metricas_receptor.h"` debajo del include de `fft_ola_v2_stream.h`, y después de `++packetsOk;` introducir:

```cpp
  metricas_asm::registrar(inputBlock, firBlock, fftBlock, BLOCK_SAMPLES,
      lastSequence, flags, packetsOk, packetsBadCrc,
      packetsBadFormat, sequenceGaps, dacErrors,
      readU32LE(headerRest + 18), processingUs, i2sWriteUs,
      sizeof(SpectralOLA1024V2Stream));
```

## 3. Compilar y subir

En Arduino IDE: abrir sketch receptor, `ESP32 Dev Module`, core Arduino-ESP32 3.x y puerto COM correcto. Primero **Verificar**, luego **Subir**. Al reiniciar monitor USB a 115200 debe seguir mostrando `DAC I2S: solicitado=32768 Hz...` y `Esperando N1B2...`. Con ambas placas enlazadas, además deben aparecer filas `MTR,...` cada ocho bloques. Si no compila, guarde error; vuelva a la copia original si hace falta.

## 4. Guardar datos en archivos CSV

Instalar dependencias de los scripts en PC:

```powershell
py -m pip install pyserial numpy
```

Cerrar el Monitor Serial de Arduino antes de abrir el registrador. Sustituir `COM8` por puerto **USB de ESP32 B (receptor)**:

```powershell
py registrar_serial.py --puerto COM8 --prueba P1 --repeticion 1 --segundos 15
```

Repetir cambiando prueba y número para P1 rep1, rep2, rep3; hasta P5. `resultados_p1_p6/` guardará CSV, logs íntegros y resumen de cada ejecución. Se admiten P6 y otras duraciones.

## 5. Generar estímulos WAV reproducibles

```powershell
py generar_estimulos_p1_p5.py --segundos 10 --reps 3
```

Se generan WAV limpios/ruido/mezcla de P1-P5 (audio PCM16 mono a 48000 Hz) y `manifest.json`. Este generador no controla el hardware y **no reemplaza** los casos que especifique el profesor. Para P6 NO generar una señal ficticia.

## 6. Métricas con referencia limpia real (opcional)

Si se lograron adquirir y **alinear** las cuatro señales físicas en un CSV (`clean,input,fir,fft`), ejecute:

```powershell
py calcular_metricas_referencia.py mediciones_alineadas.csv --prueba P1 --repeticion 1 --tono 1792
```

Para compensar los retardos de muestras físicos medidos se pueden indicar `--lag-input`, `--lag-fir`, `--lag-fft` como números enteros; NO asumir que son cero ni usar 512 arbitrariamente. Estas métricas NO se pueden obtener rigurosamente del Monitor Serial actual porque falta una entrada de referencia limpia.

## 7. Repo / estado

Este paquete fue preparado a partir de la rama `filtrosESP` tal como estaba el 6 de noviembre de 2026 a las ~05:40 (Costa Rica), commit `aa6db8e201c50366d41ba9f32387a40c132cca78`. **No se subió a GitHub** porque la conexión respondió `403 Resource not accessible by integration` al intentar crear una rama. El equipo debe revisar, compilar, probar y después hacer commit de estos cambios. No hay promesa de compilación verificada en su placa.

## 8. Resumen de tres repeticiones

```powershell
py resumir_repeticiones.py --carpeta resultados_p1_p6
```

Produce `resultados_p1_p6/resumen_p1_p6.csv` con promedio y desviación estándar entre repeticiones. Si una condición tiene menos de tres repeticiones, queda marcada para revisar.

## 9. Advertencia sobre el alcance

Este paquete agrega telemetría al Nodo 2/3, NO implementa la FFT de diagnóstico exigida para Nodo 1, NO mide automáticamente latencia física, y NO calcula MSE/SNR reales si el sistema no proporciona una señal limpia alineada. El firmware nuevo debe probarse en ESP32 antes de usarlo para la defensa.
