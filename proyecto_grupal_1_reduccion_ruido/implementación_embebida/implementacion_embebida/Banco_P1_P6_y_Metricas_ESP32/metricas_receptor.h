#pragma once
// Telemetria de banco P1-P6 para ESP32 clasica.
// No cambia el FIR, FFT, I2S, UART ni buffers existentes.
// Emite 1 fila de telemetria cada 8 bloques (~1 segundo nominal).
// MSE y SNR reales requieren referencia limpia: calcular fuera del firmware.
#include <Arduino.h>
#include <math.h>
#include <stddef.h>

namespace metricas_asm {
static constexpr uint32_t CADA_N_BLOQUES = 8;
static constexpr float FS = 8192.0f;
// Solo es una prueba de atenuacion tonAL cuando la interferencia ES este tono.
// Para P1 cambie al valor conocido que realmente inyecten.
static constexpr float TONO_INTERFERENCIA_HZ = 1792.0f;

static float energia(const float* x, size_t n) {
  double e = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double v = x[i];
    e += v * v;
  }
  return static_cast<float>(e);
}

// Amplitud DFT en frecuencia conocida mediante Goertzel, sin crear buffers.
// La magnitud no depende del retardo de fase para un tono estacionario.
static float tonoAmplitud(const float* x, size_t n, float hz) {
  const float omega = 6.283185307179586f * hz / FS;
  const float c = 2.0f * cosf(omega);
  float q1 = 0.0f, q2 = 0.0f;
  for (size_t i = 0; i < n; ++i) {
    const float q0 = x[i] + c * q1 - q2;
    q2 = q1;
    q1 = q0;
  }
  float power = q1*q1 + q2*q2 - c*q1*q2;
  if (power < 0.0f) power = 0.0f;
  return sqrtf(power) / static_cast<float>(n);
}

static void registrar(const float* entrada, const float* fir,
                      const float* fft, size_t n,
                      uint32_t seq, uint8_t adcFlags,
                      uint32_t bloques, uint32_t erroresCRC,
                      uint32_t erroresFormato, uint32_t gaps,
                      uint32_t erroresDAC, uint32_t adcCapturaUs,
                      uint32_t dspUs, uint32_t i2sWriteUs,
                      size_t bytesFFT) {
  if (n == 0 || bloques % CADA_N_BLOQUES != 0) return;

  const float ein = energia(entrada, n);
  const float efir = energia(fir, n);
  const float efft = energia(fft, n);
  const float rmsIn = sqrtf(ein / n);
  const float rmsFir = sqrtf(efir / n);
  const float rmsFft = sqrtf(efft / n);
  const float pctFir = ein > 1e-12f ? (100.0f * efir / ein) : NAN;
  const float pctFft = ein > 1e-12f ? (100.0f * efft / ein) : NAN;

  const float ain = tonoAmplitud(entrada, n, TONO_INTERFERENCIA_HZ);
  const float afir = tonoAmplitud(fir, n, TONO_INTERFERENCIA_HZ);
  const float afft = tonoAmplitud(fft, n, TONO_INTERFERENCIA_HZ);
  // Si el tono no esta presente no inventar atenuacion: dejar nan.
  const float attenFir = ain >= 1e-3f ?
      20.0f * log10f(ain / fmaxf(afir, 1e-10f)) : NAN;
  const float attenFft = ain >= 1e-3f ?
      20.0f * log10f(ain / fmaxf(afft, 1e-10f)) : NAN;

  // Un registro en el puerto USB: el host lo guarda en CSV.
  // La energia_total NO es energia_util_conservada.
  Serial.printf(
    "MTR,%lu,%u,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%u,%u,%u,%.6f,%.6f,%.6f,%.2f,%.2f,%.1f,%.2f,%.2f\n",
    (unsigned long)seq, (unsigned)adcFlags,
    (unsigned long)bloques, (unsigned long)erroresCRC,
    (unsigned long)erroresFormato, (unsigned long)gaps,
    (unsigned long)erroresDAC, (unsigned long)adcCapturaUs,
    (unsigned long)dspUs, (unsigned long)i2sWriteUs,
    (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
    (unsigned)bytesFFT, (double)rmsIn, (double)rmsFir, (double)rmsFft,
    (double)pctFir, (double)pctFft, (double)TONO_INTERFERENCIA_HZ,
    (double)attenFir, (double)attenFft);
}
} // namespace metricas_asm
