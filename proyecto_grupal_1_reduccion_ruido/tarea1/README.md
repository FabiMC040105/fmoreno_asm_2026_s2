# CE1110 — Tarea 1: señales, filtros y métricas

Integración para las secciones 2.2 y 2.5 del proyecto. Se conservan los datos sintéticos de la persona 2, el algoritmo SOS de la persona 3 y la regla espectral de la persona 4. El módulo espectral integrado corrige dos defectos de reconstrucción por bloques detectados durante las pruebas: cola sin procesar y ausencia de compensación de la ventana al solapar.

## Ejecutar en Windows (PowerShell)

Abrir la terminal **en la carpeta `tarea1`**, donde están `notebook.ipynb`, `src/`, `pruebas/` y `requirements.txt`.

```powershell
py -m pip install -r requirements.txt
py src/comparar_metodos.py
py -m unittest discover -s pruebas -p "test_*.py" -v
```

El comando `py src/comparar_metodos.py` **no requiere abrir Jupyter**. Usa los tres conjuntos de señales `.npy` existentes y escribe `resultados/metricas.csv`.

Para volver a generar **también las señales originales y sus gráficas**:

```powershell
py src/generacion_senales.py
py src/comparar_metodos.py
```

Para ejecutar el notebook visualmente, abrir `notebook.ipynb` en VS Code con extensión Jupyter y elegir *Run All*, o instalar Jupyter Notebook:

```powershell
py -m pip install notebook
py -m notebook notebook.ipynb
```

> Alternativa Linux/macOS: cambiar `py` por `python3` o `python` según instalación.

## Qué produce

| Archivo | Contenido |
|---|---|
| `resultados/metricas_generacion.csv` | SNR objetivo y observada de casos 1–3 (sección 2.2) |
| `resultados/metricas.csv` | **9 filas** comparativas (3 casos × sin filtrar, temporal y espectral) |
| `resultados/espectral_compromiso.csv` | Umbrales 0.10 y 0.85 sobre caso 3 para compromisos de señal útil |
| `resultados/metricas_metodologia.json` | Definiciones matemáticas, limitaciones y entorno de medición |
| `resultados/temporal/caso_*/filtrada.npy` | Salidas IIR en 64 bits |
| `resultados/espectral/caso_*/filtrada.npy` | Salidas FFT/IFFT en 64 bits |
| `resultados/figuras/comparacion_metodos.png` | Comparación temporal/espectral de los tres casos |
| `resultados/figuras/espectral_compromiso.png` | Ejemplo de umbral agresivo caso 3 |
| `resultados/notebook_validacion_ejecutado.ipynb` | Notebook ejecutado como evidencia (opcional en entrega) |

## Parámetros y datos

- `fs=8192 Hz`, `N=1024`, longitud del registro `L=16384`, duración `2 s`.
- Referencia útil: tonos de `256, 512 y 1024 Hz`.
- Semillas `20261021`, `20261022` y `20261023`.
- Ruido: caso 1 senoidal `1792 Hz`, caso 2 blanco gaussiano, caso 3 banda aprox. `850–1300 Hz`.
- SNR de entrada objetivo `5`, `3` y `0 dB`.
- Filtro temporal: IIR Butterworth de orden 12 representado mediante **6 SOS**; se mantiene el estado entre bloques.
- Filtro espectral: umbral de **magnitud** relativo 0.10, ganancia 0.1 para bins bajo umbral; se aplican ventanas Hann periódicas, solapamiento 50 %, padding de extremos y normalización por suma de ventanas; 0.85 solo para prueba adicional de compromiso caso 3.

## Métricas y límites

Se compara la salida temporal **sin alinear** con la referencia limpia, por lo que el retardo de fase del IIR puede reducir MSE/SNR aparente a pesar de una gran atenuación de la interferencia.

El porcentaje `energia_util_conservada_pct` es `100*E(s_filtrada)/E(s)` donde `s_filtrada` resulta de aplicar el filtro a la referencia limpia. En FFT/IFFT se aplica la **misma máscara calculada SOLO de la mezcla**, de manera que la limpia no interviene en la detección del ruido. En la práctica, medirla requiere una referencia conocida. La columna `atenuacion_ruido_inyectado_db` utiliza el ruido sintetizado conocido para medir `10 log10(E(r)/E(r_filtrado))`; no son valores estimables sin esa referencia. Los porcentajes pueden superar marginalmente 100 % por suma de bloques.

Los tiempos por bloque son **medianas medidas en PC con Python, no en ESP32**. Temporal: total/16 bloques de 125 ms. Espectral: total/33 ventanas con salto de 512 muestras y plazo de 62.5 ms. Los presupuestos de memoria son aproximaciones teóricas de buffers en float64, no mediciones de heap ni de SRAM.

## Cambios respecto a las entregas recibidas

- Se han elegido las señales del ZIP base de la persona 2. En el ZIP temporal había pequeñas diferencias de redondeo en estas señales; **las salidas temporal y espectral ahora se regeneran siempre desde las mismas entradas**.
- Se preservó sin cambios `src/filtrado_espectral_original.py`, copia exacta del código de la persona 4.
- La función equivalente en `src/filtrado_espectral.py` tiene cobertura completa, OLA normalizado y reconstrucción real mediante `rfft/irfft`; mantiene la regla original del umbral.
- Se utilizó umbral 0.10 para comparar los tres casos, sin forzar al caso 3 a un umbral más agresivo. La prueba 0.85 se informa **por separado**.
- Se dejó `resultados/metricas.csv` generado desde código y se añadió `src/comparar_metodos.py` junto con `pruebas/test_integracion_metodos.py`.

**Pendiente de coordinación:** la persona 4 debe revisar y aprobar la corrección de reconstrucción espectral antes de integrar este cambio a `development`. El equipo debe adaptar el análisis y la tabla LaTeX a los resultados medidos, escoger hardware y protocolo físico y generar el tag `tarea1_prototipo` una vez aprobada la integración. No se ha interactuado con GitHub, creado ramas ni configurado hardware desde este paquete.
