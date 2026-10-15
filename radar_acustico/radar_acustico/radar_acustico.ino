#include <math.h>
#include <arduinoFFT.h>

const int DAC_PIN = 25;
const int MIC_PIN = 34;

const int FS = 20000;
const int N = 2000;              // 100 ms

const int CHIRP_MS = 1;
const int N_CHIRP = FS * CHIRP_MS / 1000;

const float F1 = 2000.0;
const float F2 = 5000.0;

// ---------- FFT ----------
const int FFT_N = 1024;

float vReal[FFT_N];
float vImag[FFT_N];

ArduinoFFT<float> FFT =
  ArduinoFFT<float>(vReal, vImag, FFT_N, FS);

// ---------- Radar ----------
uint16_t muestras[N];
int16_t chirp[N_CHIRP];
long long corr[N - N_CHIRP];

void setup() {

  Serial.begin(115200);
  analogReadResolution(12);

  float fase = 0;

  // Crear chirp de referencia
  for (int n = 0; n < N_CHIRP; n++) {

    float f = F1 +
              (F2 - F1) *
              ((float)n / N_CHIRP);

    fase += 2.0 * PI * f / FS;

    chirp[n] = 100 * sin(fase);
  }

  delay(2000);
}

void loop() {

  unsigned long siguiente = micros();

  // ============================
  // EMITIR CHIRP Y CAPTURAR
  // ============================

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

  // ============================
  // QUITAR COMPONENTE DC
  // ============================

  long suma = 0;

  for (int i = 0; i < N; i++)
    suma += muestras[i];

  int media = suma / N;

  // ============================
  // FFT
  // ============================

  for (int i = 0; i < FFT_N; i++) {

    vReal[i] = (float)muestras[i] - media;
    vImag[i] = 0.0;
  }

  // Ventana Hamming
  FFT.windowing(
    FFTWindow::Hamming,
    FFTDirection::Forward
  );

  // Calcular FFT
  FFT.compute(
    FFTDirection::Forward
  );

  // Obtener magnitudes
  FFT.complexToMagnitude();

  // Buscar el pico únicamente dentro
  // del rango del chirp: 2 kHz - 5 kHz

  int binInicio =
    (int)ceil(F1 * FFT_N / FS);

  int binFin =
    (int)floor(F2 * FFT_N / FS);

  int picoFFT = binInicio;

  for (int i = binInicio;
       i <= binFin;
       i++) {

    if (vReal[i] > vReal[picoFFT])
      picoFFT = i;
  }

  float frecuenciaPico =
    ((float)picoFFT * FS) / FFT_N;

  // ============================
  // CORRELACIÓN
  // ============================

  for (int lag = 0;
       lag < N - N_CHIRP;
       lag++) {

    long long c = 0;

    for (int k = 0;
         k < N_CHIRP;
         k++) {

      c +=
        (long long)
        (muestras[lag + k] - media)
        * chirp[k];
    }

    corr[lag] = llabs(c);
  }

  // ============================
  // SONIDO DIRECTO
  // ============================

  int directo = 0;

  for (int i = 1; i < 50; i++) {

    if (corr[i] > corr[directo])
      directo = i;
  }

  // ============================
  // ECO
  // ============================

  const int GUARD =
    N_CHIRP + 4;

  int eco =
    directo + GUARD;

  for (int i = directo + GUARD;
       i < N - N_CHIRP;
       i++) {

    if (corr[i] > corr[eco])
      eco = i;
  }

  // ============================
  // TIEMPO Y DISTANCIA
  // ============================

  int deltaN =
    eco - directo;

  float tau =
    (float)deltaN / FS;

  float distancia_m =
    (343.0 * tau) / 2.0;

  // ============================
  // RESULTADOS
  // ============================

  Serial.println("----------------");

  Serial.print("Pico FFT: ");
  Serial.print(frecuenciaPico, 1);
  Serial.println(" Hz");

  Serial.print("Directo: ");
  Serial.println(directo);

  Serial.print("Eco: ");
  Serial.println(eco);

  Serial.print("Atraso: ");
  Serial.print(deltaN);
  Serial.println(" muestras");

  Serial.print("Tau: ");
  Serial.print(tau * 1000.0, 3);
  Serial.println(" ms");

  Serial.print("Distancia: ");
  Serial.print(distancia_m * 100.0, 1);
  Serial.println(" cm");

  delay(2000);
}