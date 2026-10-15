# 2.3(h): implementación del filtro temporal en ESP32

Se considera la placa ESP32 de referencia comercial AD42922, con el perfil
ESP32 Dev Module de Arduino IDE. No se atribuye una variante WROOM específica.
El filtro conserva orden 12, seis secciones SOS en cascada y forma directa I.
Los resultados siguientes proceden de simulación en PC con las tres entradas
originales, reposo inicial y continuidad entre bloques de 1024 muestras.

## Cuantización de coeficientes y operaciones

Se propone `float32` (4 bytes por valor). Se compara contra la implementación
propia en `float64`, separando el redondeo de los coeficientes del procesamiento
completo en precisión reducida. No se convierte únicamente la salida final:
las muestras, coeficientes, operaciones aritméticas y estados usan `float32`.
La tolerancia absoluta declarada para esta comparación es 2.0e-06,
con tolerancia relativa cero y amplitudes normalizadas. Es independiente de la
tolerancia de 1e-12 de la prueba original en float64 contra SciPy.

| Caso | Error máximo, solo coeficientes | Error máximo, todo float32 | Pico de salida | Muestras fuera de [-1,1] |
|---|---:|---:|---:|---:|
| 1 | 3.397e-08 | 9.702e-08 | 0.314813 | 0 |
| 2 | 5.470e-08 | 2.937e-07 | 0.552897 | 0 |
| 3 | 1.222e-07 | 3.153e-07 | 0.812212 | 0 |

El error máximo de representación de los coeficientes es 4.573160584e-08.
Con los coeficientes redondeados, el radio polar máximo es
0.903490205202; permanece menor que uno, por lo que el sistema
lineal causal definido por esos coeficientes conserva estabilidad BIBO.
Esto no garantiza por sí solo ausencia de fenómenos de precisión finita para
cualquier entrada. La pérdida máxima en paso es 0.999998403669 dB
y la atenuación mínima en rechazo es 41.101230751 dB.
Se reporta el valor de paso sin ocultar desviaciones diminutas alrededor del
límite de 1 dB; un diseño de producción debe reservar margen para redondeo.

Una conversión directa a Q1.15 firmado (rango [-1, 1-2^-15]) no es apropiada:
hay coeficientes de magnitud mayor que uno y los tres coeficientes del numerador
de la primera sección se redondean a cero con resolución 2^-15. Se perdería
la transferencia. Punto fijo exigiría redistribuir ganancias, seleccionar otro
formato y comprobar acumuladores, escalamiento y estabilidad nuevamente.
La propuesta float32 evita esa conversión directa. La equivalencia bit a bit
con un ESP32 no se afirma: el compilador y operaciones fusionadas pueden
modificar los últimos bits; debe repetirse la comparación al portar a C/C++.

## Saturación y salida analógica

En los tres casos evaluados no se excede [-1,1]. Esto no demuestra ausencia
universal de saturación: el escalón unitario produce pico
1.209836, y una entrada acotada construida con los signos de la
respuesta al impulso produce pico 2.089930, con
420 muestras fuera del rango. La estabilidad no impide sobrepicos.

La cota teórica en aritmética exacta es ||y||∞ <= ||h||1 ||x||∞ para reposo
inicial. La suma de |h| sobre 4096 muestras es 2.089929808;
la contribución de las últimas 256 es 1.604e-169.
La ganancia previa orientativa 0.95/||h||1 es
0.454561. Es una estimación con respuesta truncada,
no una cota certificada de la cola infinita ni del error en float32.
Esta ganancia no se aplica a los archivos originales del experimento.

Se debe reservar margen de amplitud y contar recortes. El recorte se realiza
al convertir la salida al periférico, manteniendo sin recortar la realimentación
interna del IIR; recortar estados cambia su comportamiento. Los acumuladores
float32 admiten valores superiores a uno: el límite normalizado pertenece a la
interfaz de salida, no al rango numérico de float32.

Si se utiliza el DAC interno del ESP32 clásico, tiene 8 bits [2]. El modelo
ideal empleado es `codigo = floor((clip(y,-1,1)+1)*255/2 + 0.5)`, limitado
antes de convertir a uint8. La reconstrucción normalizada es `2*codigo/255-1`.
Sin saturación, el error de cuantización está acotado por 1/255, aproximadamente
0.003922; por su número par de niveles, cero no se representa exactamente.
Esta cuantización se estudia aparte de la de coeficientes. La salida física es
unipolar, por lo que necesita polarización y, según la carga, acoplamiento y
reconstrucción analógica. El modelo no mide ruido, no linealidad ni voltajes reales.

## Memoria y procesamiento por bloques

Se estima almacenamiento de arrays en C/C++ usando float de 32 bits y cuatro
estados por sección, como la implementación propia; no los dos estados de la
forma directa II transpuesta de SciPy. Se presupone una sola copia de cada array.

| Elemento | Cálculo | Bytes |
|---|---|---:|
| Coeficientes SOS | 6 × 6 × 4 | 144 |
| Estados persistentes | 6 × 4 × 4 | 96 |
| Bloque de entrada | 1024 × 4 | 4096 |
| Bloque de salida | 1024 × 4 | 4096 |
| Total | | 8432 |
| Total con dos bloques de entrada y dos de salida | | 16624 |

El total básico es 8.2344 KiB. El ESP32 clásico dispone
nominalmente de 520 KB de SRAM [1], compartidos entre datos e instrucciones;
no equivalen al heap libre. Estas cifras excluyen pila, RTOS, drivers, DMA,
Wi-Fi/Bluetooth y datos ADC/DAC. Los arrays deben reservarse una vez y reutilizarse;
el prototipo Python, con copias y grabaciones completas, no representa ese consumo.
No se presupone PSRAM ni una capacidad específica de Flash para esta placa.

A 8192 Hz, llenar un bloque tarda
125.000 ms. Es tiempo de adquisición, distinto
del retardo de grupo del filtro y de su tiempo de cómputo. El presupuesto de
memoria es reducido, pero la viabilidad en tiempo real debe medirse en el
microcontrolador con el resto de tareas activas. No se ha cargado firmware.

## Conclusión

Los resultados permiten evaluar float32 como formato de implementación,
conservar las seis secciones SOS y dimensionar buffers sin almacenar las
señales completas. Deben mantenerse margen de amplitud y recorte controlado
al salir al periférico. El inciso h queda documentado mediante análisis y
simulación; las mediciones físicas de memoria libre y tiempo quedan fuera de
esta validación en PC.

## Referencias

[1] Espressif, ESP32 Series Datasheet, memoria y periféricos:
https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf

[2] Espressif, ESP-IDF, Digital To Analog Converter (DAC), ESP32:
https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/dac.html
