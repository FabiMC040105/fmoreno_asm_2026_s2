# Diagnóstico FFT N1 y validación temporal — ampliación conservadora

**Estado de entrega:** parche de software preparado y FFT comprobada con prueba C++ nativa. **NO** se pudo compilar como firmware ESP32 ni probar físicamente; los resultados de audio, memoria real, ADC y DAC quedan **sin verificar en hardware**.

## Punto de partida y objetivo

Repositorio: `https://github.com/FabiMC040105/fmoreno_asm_2026_s2`

Rama base auditada: `filtrosESP`, commit `e53440a1ed3e7e62a4b5acf19b34e094db0ec842` (incluye corrección de intermitencia `9fbc7d49c76a31e25a02f720a3609d9773603477`). La rama destino debe llamarse `feature/nodo1-fft-temporal-validation`.

El parche verifica por SHA los dos `.ino` originales antes de escribir; se detiene si han cambiado. **No cambiar** el FIR antialias/coeficientes, la decimación 3:1, la cabecera N1B2, CRC, secuencias, procesamiento FIR129, FFT/IFFT de Nodo 3, I2S, pinout de audio o transmisión.

### Archivos

- `nodo1_adquisicion/nodo1_adquisicion.ino`: medición temporal, FFT asíncrona a partir de copia del bloque enviado, contadores y GPIO optativos.
- `nodo1_adquisicion/fft_diagnostico_n1.h`: FFT radix-2 de 1024 puntos, Hann periódica, 5 máximos locales y energía por bandas; **no altera las muestras**.
- `nodo1_adquisicion/estadisticas_tiempo.h`: acumulador de media, mínimo, máximo y desviación estándar.
- `nodo2_nodo3_procesamiento/nodo2_nodo3_procesamiento.ino`: tiempos de FIR, FFT, llamada I2S, intervalo de recepción y pérdida estimada por secuencias.
- `nodo2_nodo3_procesamiento/estadisticas_tiempo.h`: acumulador idéntico al de Nodo 1 para compilación autónoma de cada sketch.
- `VALIDACION_FFT_Y_TIEMPOS.md`: este procedimiento.

### Diseño y riesgos

- N1 adquiere 3072 muestras de ADC a **24576 Hz nominales**, tras FIR antialias de 61 taps y decimación 3:1 entrega 1024 muestras a **8192 Hz nominales**. Se analiza la **salida filtrada y decimada** que se envía, sin ninguna operación in-place sobre ella.
- FFT de **1024 muestras**, `Δf = 8192/1024 = 8 Hz`; Hann **periódica**; cada **8 bloques**. Trabaja en una tarea FreeRTOS en core 0, prioridad 1, con una copia estática, sin memoria dinámica por transformada. Si aún está ocupada se omite ese diagnóstico, **no el bloque de audio**. La FFT y sus arrays ocupan 3×1024×4 = **12288 bytes** más copia 4096 bytes; pila reservada 8192 bytes, más sobrecarga de FreeRTOS. La cifra exacta de compilación/heap se debe medir en la placa.
- Nodo 2/3 ya usa memoria para el filtro espectral, buffers y DMA. El parche añade acumuladores de tiempo y GPIO condicionales; no vuelve a reservar grandes buffers.
- El ADC continua usando DMA; la FFT no detiene voluntariamente ADC. **No está garantizado** que un core secundario elimine por completo la contención de CPU/memoria o el riesgo de pérdidas. Validarlo físicamente antes de emplear esta rama en una defensa.
- Se conserva el registro serial USB existente de ambos nodos. El monitor puede alterar la temporización, por eso la medición externa sigue siendo la referencia más independiente.

## Pines — diagrama lógico, sin nuevos cables

| Placa | GPIO | Función existente o futura | Situación |
|---|---:|---|---|
| N1 | 34 | ADC micrófono | **ocupado; no tocar** |
| N1 | 16 / 17 | UART2 RX / TX (N1B2) | **ocupados; no tocar** |
| N1 | 32 | Pulso fin de adquisición del bloque (lectura DMA completada) | Solo si `DIAG_GPIO_HABILITADOS=true` |
| N1 | 33 | Alto durante llamada `Serial2.write()` | Solo si habilitado; **no implica que termine TX física** |
| N2/3 | 16 / 17 | UART2 RX / TX reservado | **ocupados; no tocar** |
| N2/3 | 25 / 26 | DAC FIR / FFT | **ocupados; no tocar** |
| N2/3 | 32 | Pulso al recibir paquete válido (CRC + formato) | Solo si habilitado |
| N2/3 | 33 | Alto durante llamada `i2s_write()` | Solo si habilitado; **NO indica fin de reproducción** |

Los GPIO32/33 no se usan en el **código revisado**, pero **no se verificó visualmente el cableado del montaje**. No conectar nada sin confirmar el pinout físico. Todos estos marcadores están `false` por defecto. **Para la entrega sin tocar circuito, dejar desactivados.** Se evitan GPIO de arranque, memoria flash y GPIO34-39 de solo entrada.

## Temporización interna: qué miden las cifras

Periodo ideal: `T = 1024 / 8192 = 0.125 s = 125000 us`.

- **`T1`** cada 32 bloques: intervalo entre finalizaciones de `acquireRawBlock`, tiempo de lectura ADC, media/min/max/desviación, duración de `Serial2.write`, fallos de captura, overflows del pool y FFT omitidas.
- **`FFT1`** cada 8 bloques, si se ejecuta: duración real de cálculo de la FFT (en tarea), 5 picos ordenados frecuencia:amplitud, energía por bandas `[0,500)`, `[500,1500)`, `[1500,3000)` y `[3000,4096]` Hz, RAM estática + pila nominal y heap libre.
- **`T23_RX`** cada 32 paquetes válidos: periodo medio/min/max/desviación entre finales de recepción válida, CRC, formato, saltos de secuencia, número estimado de paquetes perdidos por avances positivos de secuencia y errores DAC.
- **`T23_DSP`** cada 32 paquetes válidos: tiempos de FIR, FFT/IFFT por bloque y retorno de llamada `i2s_write`, además de heap y DSP total. Las estadísticas se acumulan; no hay historial creciente.
- **`MTR`** existente: sigue disponible y no debe confundirse con MSE o SNR contra señal limpia sin medir esa referencia.

El flujo N1B2 tiene 26 B de cabecera + 4096 B de payload + 4 B CRC = **4126 B**. La ocupación teórica de la línea UART 8N1 a 921600 baudios es `4126 × 10 / 921600 ≈ 44.77 ms`. El reloj configurado y los tiempos de API no prueban que ese envío haya sido físicamente exacto.

**Advertencia sobre `i2s_write`:** el tiempo de retorno informa encolado y posibles esperas por espacio en los buffers DMA, **no** tiempo de reproducción real. Para 1024 muestras DSP repetidas 4 veces a 32768 Hz de DAC, la duración nominal del bloque reproducido es también **125 ms**. Hay latencia de cola I2S y retardo de algoritmos independientes de ese valor.

## Validar en las placas, sin rehacer circuito

1. Guardar una copia de la rama estable `filtrosESP`; crear rama `feature/nodo1-fft-temporal-validation`. Aplicar parche y compilar en Arduino-ESP32 **3.x** con ESP32 clásica (`ESP32 Dev Module` / ESP-32D). Usar la misma configuración y puertos que ya funcionaban.
2. Primero compilar/cargar **solo N1** en la rama de prueba y abrir **USB de N1 a 115200**. Confirmar que aparecen `FFT1`, `T1`; observar que N2/3 sigue recibiendo N1B2 sin aumento de CRC ni gaps. Si hay cortes, volver inmediatamente a la versión estable.
3. Para la prueba P1 desde GUI actual, buscar máximos cerca de **512 Hz** (componente útil) y **1792 Hz** (contaminación). P2: **256, 512 y 1024 Hz** y ruido alto. P3: espectro dependiente del WAV. P4: **512 Hz** cuando hay tono, con energía distribuida por impulsos. P5: **256, 512 y 1024 Hz** y energía difusa de 850–1300 Hz. Estas son **frecuencias del estímulo digital**, no promesa de picos medidos en el micrófono.
4. En `FFT1` verificar resolución 8 Hz y comparar las posiciones de máximos. No exigir amplitudes digitales idénticas: intervienen altavoces, ambiente, micrófono y preprocesado.
5. Cargar luego N2/3 desde esta rama, observar `T23_RX` y `T23_DSP` por **USB de esa placa a 115200**. Comparar media/dispersion con 125000 us; comprobar CRC, gaps, errores DAC y heap libre.
6. Probar también sin estímulo (P6, cuando corresponda). Comparar la versión estable y la nueva bajo condiciones iguales. Si reaparece pitido, cortes, CRC/gaps o overflow, **revertir ambos firmwares**. No llamar estable a un cambio no probado.
7. Para medir frecuencia ADC efectiva por software: aplicar un tono analógico de frecuencia conocida y registrar picos de N1. La relación aproximada `fs_real = fs_nominal × f_conocida/f_medida` es sensible a resolución FFT, aliasing, amplitud y precisión del generador: solo una estimación, no calibración independiente. Se pueden acumular bloques/cero cruces en una captura y comparar con generador calibrado.
8. Para DAC real, medir físicamente la salida GPIO25/26 con osciloscopio o analizador adecuado frente a tono conocido. El `i2s_get_clk()` y el tiempo de `i2s_write` no certifican por sí solos el valor analógico ni la frecuencia efectiva de la onda.

## Procedimiento con osciloscopio (solo propuesto; requiere acceso físico)

1. Con montaje **apagado**, confirmar que GPIO32/33 de cada placa están libres; conectar tierra común y sondas de alta impedancia. Cambiar las dos constantes `DIAG_GPIO_HABILITADOS` a `true`, compilar/cargar; desactivarlas de nuevo al terminar. **No realizar en esta entrega si el circuito no se toca.**
2. Medir del flanco del pulso de **N1 GPIO32** al siguiente: esperado ≈125 ms; recolectar muchos periodos y calcular media/min/max/desviación y jitter p-p. Contar pulsos y contrastar secuencias recibidas N2/3 GPIO32; si hay pulso N1 pero no N2, investigar CRC/uart/sync.
3. Medir **N1 GPIO33** para tiempo de la llamada `Serial2.write`, y **N1 GPIO17 (línea UART real)** con decodificador 921600/8N1 para duración real del paquete. No declarar que GPIO33 solo mide transmisión física; no lo hace.
4. Medir **N2 GPIO33** para cuánto bloquea `i2s_write`; para audio real medir **DAC GPIO25 o GPIO26** y el periodo real de la onda, recordando el retardo del DSP. La diferencia entre duraciones de API y forma de onda es relevante.
5. Calcular histogramas de diferencias de flancos, eventos omitidos y jitter. Guardar capturas y registrar condiciones: carga, tono, cableado y firmware.

## Compilar, analizar memoria y retornar a estable

Arduino IDE 2.x: instalar ESP32 por Espressif Systems versión **3.x**; abrir cada `.ino` de forma separada en su carpeta, elegir placa **ESP32 Dev Module** y el puerto USB de cada ESP32, pulsar **Verificar**, registrar `Sketch uses ... bytes` y `Global variables use ... bytes`; luego **Subir** a una placa por vez. Para compilar con CLI (si instalado y configurado):

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 "proyecto_grupal_1_reduccion_ruido/implementación_embebida/implementacion_embebida/nodo1_adquisicion"
arduino-cli compile --fqbn esp32:esp32:esp32 "proyecto_grupal_1_reduccion_ruido/implementación_embebida/implementacion_embebida/nodo2_nodo3_procesamiento"
```

Se debe **copiar el resultado real** del compilador y el heap `FFT1`/`T23_DSP`; aquí no existen números verificados de flash/RAM. Los valores `ram_est` son **presupuesto de buffers y pila configurada**, no informe del enlazador ni consumo real.

Reversión de fuente y placas: desde el repositorio local `git switch filtrosESP`; compilar y cargar **ambos `.ino` estables de esa rama** a sus ESP32 (volver solo el código Git no cambia el firmware ya grabado). No mezclar un protocolo experimental con firmware que no fue probado conjuntamente. La rama nueva se puede descartar sin afectar `filtrosESP`.

## Comparación antes/después

| Elemento | Base estable `filtrosESP` | Rama experimental |
|---|---|---|
| FIR antialias, decimación, UART N1B2/CRC | Existentes | **Sin cambios** |
| FIR129 y FFT/IFFT de Nodo 2/3 | Existentes | **Sin cambios** |
| FFT de entrada en N1 | No | Sí, copia asíncrona cada 8 bloques |
| Estadística temporal acumulada | Telemetría parcial | Media, min, max, desviación y errores |
| GPIO de diagnóstico | No | Código optativo, **desactivado** |
| Cableado físico | Estable | **Sin cambios** |
| Prueba física exitosa del nuevo código | No corresponde | **Pendiente** |

Los cambios deben separarse en commits: `feat(nodo1): FFT diagnostica y tiempos`, `feat(nodo23): instrumentacion temporal`, `docs: guia de validacion y rollback`.
