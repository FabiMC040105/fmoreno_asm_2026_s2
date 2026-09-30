#include <math.h>

const int DAC_PIN = 25;

const float F_INICIO = 2000.0;
const float F_FINAL  = 5000.0;

const int FS = 20000;
const int DURACION_MS = 20;

void setup() {
}

void loop() {

  const int N = FS * DURACION_MS / 1000;

  float fase = 0;

  for (int n = 0; n < N; n++) {

    float f = F_INICIO +
              (F_FINAL - F_INICIO) *
              ((float)n / N);

    fase += 2.0 * PI * f / FS;

    int salida = 128 + 120 * sin(fase);

    dacWrite(DAC_PIN, salida);

    delayMicroseconds(50);
  }

  dacWrite(DAC_PIN, 128);

  delay(1000);
}