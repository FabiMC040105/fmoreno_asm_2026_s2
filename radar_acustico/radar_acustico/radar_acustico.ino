#include <math.h>

const int DAC_PIN = 25;
const int MIC_PIN = 34;

const int FS = 20000;
const int N = 2000;              // 100 ms

const int CHIRP_MS = 1;
const int N_CHIRP = FS * CHIRP_MS / 1000;

const float F1 = 2000.0;
const float F2 = 5000.0;

uint16_t muestras[N];
int16_t chirp[N_CHIRP];
long long corr[N - N_CHIRP];

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);

  float fase = 0;

  // Crear chirp de referencia
  for (int n = 0; n < N_CHIRP; n++) {
    float f = F1 + (F2 - F1) * ((float)n / N_CHIRP);
    fase += 2.0 * PI * f / FS;
    chirp[n] = 100 * sin(fase);
  }

  delay(2000);
}

void loop() {

  unsigned long siguiente = micros();

  // Emitir chirp y capturar
  for (int n = 0; n < N; n++) {

    if (n < N_CHIRP)
      dacWrite(DAC_PIN, 128 + chirp[n]);
    else
      dacWrite(DAC_PIN, 128);

    muestras[n] = analogRead(MIC_PIN);

    siguiente += 1000000 / FS;

    while ((long)(micros() - siguiente) < 0) {}
  }

  dacWrite(DAC_PIN, 128);

  // Quitar componente DC
  long suma = 0;

  for (int i = 0; i < N; i++)
    suma += muestras[i];

  int media = suma / N;

  // Correlación
  for (int lag = 0; lag < N - N_CHIRP; lag++) {

    long long c = 0;

    for (int k = 0; k < N_CHIRP; k++)
      c += (long long)(muestras[lag + k] - media) * chirp[k];

    corr[lag] = llabs(c);
  }

  // Buscar sonido directo
  int directo = 0;

  for (int i = 1; i < 50; i++) {
    if (corr[i] > corr[directo])
      directo = i;
  }

  // Ignorar zona alrededor del sonido directo
  const int GUARD = N_CHIRP + 4;

  // Buscar eco
  int eco = directo + GUARD;

  for (int i = directo + GUARD;
       i < N - N_CHIRP;
       i++) {

    if (corr[i] > corr[eco])
      eco = i;
  }

  int deltaN = eco - directo;

  Serial.println("----------------");

  Serial.print("Directo: ");
  Serial.println(directo);

  Serial.print("Eco: ");
  Serial.println(eco);

  Serial.print("Atraso: ");
  Serial.print(deltaN);
  Serial.println(" muestras");

  delay(2000);
}