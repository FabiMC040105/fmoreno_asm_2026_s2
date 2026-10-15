#include <math.h>

const int DAC_PIN = 25;
const int MIC_PIN = 34;

const int FS = 20000;
const int N = 2000;              // 100 ms

const int CHIRP_MS = 20;
const int N_CHIRP = FS * CHIRP_MS / 1000;

const float F1 = 2000.0;
const float F2 = 5000.0;

uint16_t muestras[N];

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  delay(2000);
}

void loop() {

  float fase = 0;
  unsigned long siguiente = micros();

  // Emitir chirp y capturar micrófono
  for (int n = 0; n < N; n++) {

    if (n < N_CHIRP) {

      float f = F1 + (F2 - F1) *
                ((float)n / N_CHIRP);

      fase += 2.0 * PI * f / FS;

      int salida = 128 + 100 * sin(fase);

      dacWrite(DAC_PIN, salida);

    } else {
      dacWrite(DAC_PIN, 128);
    }

    muestras[n] = analogRead(MIC_PIN);

    siguiente += 1000000 / FS;

    while ((long)(micros() - siguiente) < 0) {}
  }

  dacWrite(DAC_PIN, 128);

  // Mostrar las muestras capturadas
  for (int i = 0; i < N; i++) {
    Serial.println(muestras[i]);
  }

  Serial.println("FIN");
  delay(2000);
}