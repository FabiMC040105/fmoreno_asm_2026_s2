#pragma once
// FFT exclusivamente diagnostica. No altera ni devuelve muestras de audio.
// Portatil C++11: sin malloc, sin Arduino y sin FFT del nodo receptor.
#include <cmath>
#include <cstddef>
#include <cstdint>

struct ResultadoFFTDiagnostica {
  float frecuenciaHz[5];
  float amplitud[5];
  float energiaBandas[4];
  uint8_t picosValidos;
};

class FFTDiagnosticaN1 {
public:
  static constexpr size_t N = 1024;
  static constexpr float FS = 8192.0f;
  static constexpr float RESOLUCION_HZ = FS / N;

  void preparar() {
    const float pi2 = 6.28318530717958647692f;
    for (size_t i = 0; i < N; ++i)
      ventana_[i] = 0.5f - 0.5f * cosf(pi2 * (float)i / (float)N);
  }

  void analizar(const float* senal, ResultadoFFTDiagnostica* resultado) {
    if (senal == nullptr || resultado == nullptr) return;
    for (size_t i = 0; i < 5; ++i) {
      resultado->frecuenciaHz[i] = 0.0f;
      resultado->amplitud[i] = 0.0f;
    }
    for (size_t i = 0; i < 4; ++i) resultado->energiaBandas[i] = 0.0f;
    resultado->picosValidos = 0;

    for (size_t i = 0; i < N; ++i) {
      real_[i] = senal[i] * ventana_[i];
      imag_[i] = 0.0f;
    }

    // FFT radix-2 iterativa en sitio: tiempo O(N log N).
    for (size_t i = 1, j = 0; i < N; ++i) {
      size_t bit = N >> 1;
      while (j & bit) { j ^= bit; bit >>= 1; }
      j ^= bit;
      if (i < j) {
        const float rr = real_[i], ii = imag_[i];
        real_[i] = real_[j]; imag_[i] = imag_[j];
        real_[j] = rr; imag_[j] = ii;
      }
    }
    for (size_t len = 2; len <= N; len <<= 1) {
      const float angulo = -6.28318530717958647692f / (float)len;
      const float pasoR = cosf(angulo), pasoI = sinf(angulo);
      for (size_t base = 0; base < N; base += len) {
        float wr = 1.0f, wi = 0.0f;
        for (size_t j = 0; j < len / 2; ++j) {
          const size_t u = base + j, v = u + len / 2;
          const float vr = real_[v] * wr - imag_[v] * wi;
          const float vi = real_[v] * wi + imag_[v] * wr;
          const float ur = real_[u], ui = imag_[u];
          real_[u] = ur + vr; imag_[u] = ui + vi;
          real_[v] = ur - vr; imag_[v] = ui - vi;
          const float siguienteR = wr * pasoR - wi * pasoI;
          wi = wr * pasoI + wi * pasoR;
          wr = siguienteR;
        }
      }
    }

    // Periodic Hann: ganancia coherente 0.5, energia media de ventana 3/8.
    // Energia reportada: potencia media estimada por bandas (unidades relativas^2).
    // Las amplitudes se expresan en las unidades normalizadas de salida del Nodo 1.
    constexpr float invN2Rms = 1.0f / (float)(N * N * 0.375f);
    constexpr float escalaAmplitud = 4.0f / (float)N;
    float magnitudes[N / 2 + 1];  // 2052 B de pila; FFT en memoria del objeto.
    for (size_t k = 0; k <= N / 2; ++k) {
      const float potencia = real_[k] * real_[k] + imag_[k] * imag_[k];
      magnitudes[k] = sqrtf(potencia);
      const float frec = (float)k * RESOLUCION_HZ;
      const size_t banda = frec < 500.0f ? 0 :
                           frec < 1500.0f ? 1 : frec < 3000.0f ? 2 : 3;
      const float factorDos = (k == 0 || k == N / 2) ? 1.0f : 2.0f;
      resultado->energiaBandas[banda] += factorDos * potencia * invN2Rms;
    }

    // Solo maximos locales para evitar reportar como tonos distintos los
    // dos bins laterales de una misma senoidal tras aplicar Hann.
    for (size_t k = 1; k < N / 2; ++k) {
      const float mag = magnitudes[k];
      if (!(mag > magnitudes[k - 1] && mag >= magnitudes[k + 1])) continue;
      const float amp = mag * escalaAmplitud;
      for (size_t i = 0; i < 5; ++i) {
        if (amp > resultado->amplitud[i]) {
          for (size_t j = 4; j > i; --j) {
            resultado->amplitud[j] = resultado->amplitud[j - 1];
            resultado->frecuenciaHz[j] = resultado->frecuenciaHz[j - 1];
          }
          resultado->amplitud[i] = amp;
          resultado->frecuenciaHz[i] = (float)k * RESOLUCION_HZ;
          if (resultado->picosValidos < 5) ++resultado->picosValidos;
          break;
        }
      }
    }
  }

private:
  float real_[N];
  float imag_[N];
  float ventana_[N];
};
