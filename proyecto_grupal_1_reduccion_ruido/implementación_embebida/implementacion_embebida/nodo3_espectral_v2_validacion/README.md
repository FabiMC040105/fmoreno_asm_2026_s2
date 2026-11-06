# Validación del port C++ del Nodo 3

Esta carpeta permite comparar el algoritmo C++ streaming con la referencia Python sin look-back.

Requisitos: Python 3, NumPy y un compilador C++11 (`g++`). En PowerShell, desde esta carpeta:

```powershell
py -m pip install numpy
py .\validar_port_cpp.py
```

El script compila `prueba_fft_v2.cpp`, ejecuta las 15 entradas incluidas en `datos_prueba` y genera/actualiza `validacion_cpp_vs_python.csv`.

Criterio configurado: error máximo absoluto menor que `1e-4`. La ejecución de desarrollo registrada obtuvo un error máximo de `2.18e-6`.

`filtrado_espectral_v2_nolookback.py` es la referencia Python causal que corresponde al flujo en vivo. Se diferencia de la v2 offline con look-back: no reescribe ganancias de una ventana anterior después de observar una futura. Esta restricción reduce la mejora tonal de unos +32 dB a unos +19 dB, pero permite decidir y emitir ventanas en streaming con un hop de retención.

El ejecutable C++ que genera este script mide tiempo en la PC y no sustituye una medición en ESP32.
