# Análisis automático de resultados CE1110

## Uso rápido en Windows

1. Copia `analizar_resultados_asm.py` y `EJECUTAR_ANALISIS_ASM.bat` a la carpeta que contiene `Resultados_ASM`.
2. Termina las pruebas normales con `Pruebas_ASM_Sencillas.pyw`.
3. Haz doble clic en `EJECUTAR_ANALISIS_ASM.bat`.
4. Abre la carpeta nueva `Resultados_ASM/Reporte_metricas/`.

El `.bat` busca el intérprete de Python en `%USERPROFILE%\asmvenv\Scripts\python.exe` y, si no existe, utiliza `python` del PATH. Puedes arrastrar `Resultados_ASM.zip` sobre el `.bat` para analizar directamente el ZIP. NumPy se necesita si existen archivos de muestras `.npz` o `capturas_medidas.csv` para MSE/SNR; para consolidar la telemetría existente no se necesita NumPy.

Si quieres incorporar automáticamente **la validación de software**, coloca también la carpeta `nodo3_espectral_v2_validacion/datos_prueba` junto al `.bat` (como está organizada en el proyecto). Se generará una salida **claramente separada** de las pruebas físicas.

## Uso desde PowerShell

```powershell
python analizar_resultados_asm.py "Resultados_ASM"
python analizar_resultados_asm.py "Resultados_ASM.zip"
python analizar_resultados_asm.py "Resultados_ASM" --validacion-software "nodo3_espectral_v2_validacion\datos_prueba"
```

Para instalar NumPy, si hace falta:

```powershell
python -m pip install numpy
```

## Archivos generados

- `telemetria_por_repeticion.csv`: un renglón por ensayo, con promedios de MTR, contadores y memoria.
- `telemetria_por_prueba.csv`: promedios y desviaciones **entre repeticiones** P1–P5, sin confundir mediciones MTR sucesivas con repeticiones.
- `mse_snr_capturas_fisicas.csv`: MSE y SNR solo si existen muestras sincronizadas; en las carpetas actuales, deja explícito `NO_CALCULABLE_SIN_MUESTRAS`.
- `mse_snr_validacion_software.csv`: 15 casos de simulación si se indica `--validacion-software`.
- `reporte_metricas.md`: explicación con tabla resumida.

## Cómo habilitar MSE/SNR de las mediciones físicas

Dentro de cada subcarpeta de ejecución `Resultados_ASM/Sesion_.../P1_rep1/`, se puede guardar **una captura real** llamada `capturas_medidas.csv`, con cuatro columnas (filas de muestras sincronizadas):

```csv
limpia,entrada,fir,fft
0.012,0.081,0.015,0.010
0.031,0.099,0.032,0.027
...
```

O guardar `senales_medidas.npz` con cuatro arreglos NumPy: `limpia`, `entrada`, `fir`, `fft`. El script acepta también los nombres de variables `limpia_nodo1`, `entrada_nodo1`, `salida_fir` y `salida_fft_v2`.

Las muestras **deben** proceder de la señal limpia de referencia, la captura ADC contaminada y las salidas físicas FIR y FFT medidas, todas con la misma frecuencia de muestreo, escala y tiempo alineado. La PC no puede reconstruir las salidas físicas desde `estimulo.wav` y `telemetria.csv`.

Si conoces por una medición independiente los retardos entre los canales, puedes añadir `--desfase-fir 128 --desfase-fft 512`, por ejemplo. Estos números son ejemplos de la sintaxis, **no los retardos medidos de este proyecto**. Un desfase positivo significa que la salida registrada está retrasada respecto a la referencia.

**Aclaración para la defensa:** el profesor autorizó a la computadora a graficar métricas, no a ejecutar el procesamiento del sistema durante la operación. Este script sirve para analizar las evidencias guardadas y verificar resultados posteriormente; no sustituye el cálculo embebido que sea requerido durante la demostración.

## Limitaciones del análisis

- No puede deducir MSE, SNR ni ΔSNR físicas solo a partir de RMS, energía total y atenuación tonal. `estimulo.wav` **no es la captura física**.
- No debe interpretarse energía total relativa como energía útil conservada.
- Las métricas SNR y MSE con referencia se calculan por muestras con las fórmulas del proyecto, sin ajustar artificialmente ganancia ni fase. Los retardos deben conocerse y corregirse.
- Si `atenuacion_tono_*` contiene `NaN`, se registra como dato no disponible.
- Si una prueba contiene un solo ensayo, no puede calcularse una desviación estándar *entre repeticiones*.
