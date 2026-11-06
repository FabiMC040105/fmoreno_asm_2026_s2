# Implementación embebida

- `nodo1_adquisicion`: firmware de captura ADC/DMA, antialias y decimación para la primera ESP32.
- `nodo2_nodo3_procesamiento`: firmware receptor que ejecuta FIR y FFT v2 en paralelo en la segunda ESP32 y entrega dos salidas DAC.
- `nodo3_espectral_v2_validacion`: referencia Python y pruebas C++ nativas para comprobar el port streaming del algoritmo espectral.

Leer primero el `README.md` de la raíz del paquete.
