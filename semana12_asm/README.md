# CE1110 — Semana 12: Emisor y receptor con ESP32

Este proyecto corresponde a la parte física de la sesión asincrónica de la semana 12. Se utilizaron dos placas ESP-32D: una genera señales por su DAC y la otra las recibe mediante su ADC. Las muestras se envían por USB a Python, donde se calcula la FFT y se comprueban las frecuencias detectadas.

## Montaje

- **Emisor:** ESP-32D, salida DAC en GPIO25.
- **Receptor:** ESP-32D, entrada ADC en GPIO34.
- **Enlace analógico:** resistencia de 4.7 kΩ en serie y capacitor de 10 nF entre la entrada ADC y GND.
- **Tierra común:** conectar GND de ambas placas. No unir los pines 3V3 ni 5V.
- **Adquisición:** 8192 muestras/s (nominales), bloques de 1024 muestras y resolución FFT de 8 Hz.

```text
ESP32 emisor                   ESP32 receptor
GPIO25 ---[4.7 kΩ]---+-------- GPIO34
                      |
                    [10 nF]
                      |
GND ------------------+-------- GND
```

## Archivos principales

| Ruta | Contenido |
| --- | --- |
| `firmware/02_emisor_dos_placas/` | Código Arduino del emisor. |
| `firmware/03_receptor_dos_placas/` | Código Arduino del receptor. |
| `firmware/01_loopback_una_placa/` | Prueba previa con una sola placa. |
| `python/probar_dos_placas.py` | Control de ambos puertos seriales y ejecución de las capturas. |
| `python/validar_fft_receptor.py` | Análisis FFT y generación de reportes. |
| `pruebas/` | Pruebas del analizador en Python. |
| `datos/fisico_dos_placas/` | CSV, gráficas y reportes de las pruebas reales. |
| `GUIA_DOS_PLACAS.md` | Procedimiento de montaje y solución de problemas. |

## Ejecución

1. Cargar los dos programas `.ino` en sus placas desde Arduino IDE (paquete **esp32 by Espressif Systems**, versión 3.x, placa **ESP32 Dev Module**).
2. Montar el circuito con los USB desconectados y, después de revisarlo, conectar ambas placas a la computadora.
3. Abrir PowerShell en la raíz del proyecto y cerrar los monitores seriales de Arduino IDE.
4. Instalar las dependencias y consultar los puertos disponibles:

```powershell
& "$env:USERPROFILE\asmvenv\Scripts\python.exe" -m pip install -r requirements_fisica.txt
& "$env:USERPROFILE\asmvenv\Scripts\python.exe" python\probar_dos_placas.py --listar-puertos
```

5. Ejecutar un modo o las cinco pruebas, sustituyendo `COM6` y `COM7` por los puertos reales:

```powershell
& "$env:USERPROFILE\asmvenv\Scripts\python.exe" python\probar_dos_placas.py --emisor COM6 --receptor COM7 --modo 4
& "$env:USERPROFILE\asmvenv\Scripts\python.exe" python\probar_dos_placas.py --emisor COM6 --receptor COM7 --todos
```

Si se utiliza otro entorno de Python, sustituir la ruta de `asmvenv` por el ejecutable correspondiente.

## Modos de señal

| Modo | Frecuencias esperadas |
| --- | --- |
| 1 | 256 Hz |
| 2 | 1024 Hz |
| 3 | 256, 512 y 1024 Hz |
| 4 | 256, 512, 1024 y 1792 Hz |
| 5 | 1792 Hz |

## Resultados obtenidos

En las pruebas con las dos ESP-32D se identificaron las frecuencias esperadas en los cinco modos. Cada captura contiene 1024 muestras; los reportes registraron cuatro muestras tardías por bloque y no indicaron saturación del ADC. Los resultados se encuentran en `datos/fisico_dos_placas/`:

- `captura_modo*.csv`: muestras adquiridas.
- `fft_modo*.png`: señal temporal y espectro.
- `reporte_modo*.json`: resultados de cada captura.
- `resumen_dos_placas.csv`: comparación de los cinco modos.

Para ejecutar las pruebas automáticas del analizador:

```powershell
& "$env:USERPROFILE\asmvenv\Scripts\python.exe" -m unittest discover -s pruebas -p "test_*.py" -v
```

## Limitaciones

La frecuencia de muestreo es nominal y se controla por software, por lo que puede existir variación en los intervalos de adquisición. La FFT se ejecuta en Python, **no en el receptor ESP32**. La integración del procesamiento en los microcontroladores queda para las siguientes etapas del proyecto grupal.
