#ifndef FFT_OLA_V2_STREAM_H
#define FFT_OLA_V2_STREAM_H

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#ifdef ARDUINO
  #include <Arduino.h>
#else
  #include <chrono>
#endif

// Nodo 3: supresion espectral adaptativa en streaming.
// fs=8192 Hz, FFT=1024, hop=512, Hann periodica, historial maximo=8 frames.
// Variante streaming SIN look-back retroactivo: cada frame decide sus propias
// ganancias y el bloque emitido usa las dos ventanas solapadas ya decididas.
// Latencia de algoritmo: un hop (512 muestras = 62.5 ms), aparte de colas I/O.
class SpectralOLA1024V2Stream {
public:
  static constexpr size_t FFT_SIZE = 1024;
  static constexpr size_t HOP_SIZE = 512;
  static constexpr size_t BINS = 513;
  static constexpr size_t HISTORY = 8;

  struct Stats {
    uint32_t processing_us;
    uint32_t frames_processed;
    uint32_t outputs_produced;
  };

  SpectralOLA1024V2Stream()
      : history_write_(0), history_count_(0), has_previous_(false),
        frames_processed_(0), blocks_emitted_(0) {
    const float two_pi = 6.2831853071795864769f;
    for (size_t n = 0; n < FFT_SIZE; ++n) {
      window_[n] = 0.5f - 0.5f * cosf(two_pi * (float)n / (float)FFT_SIZE);
    }
    memset(previous_hop_, 0, sizeof(previous_hop_));
    memset(zero_hop_, 0, sizeof(zero_hop_));
    memset(history_spectrum_, 0, sizeof(history_spectrum_));
    memset(history_magnitude_, 0, sizeof(history_magnitude_));
  }

  void reset() {
    history_write_ = 0;
    history_count_ = 0;
    has_previous_ = false;
    frames_processed_ = 0;
    blocks_emitted_ = 0;
    memset(previous_hop_, 0, sizeof(previous_hop_));
    memset(zero_hop_, 0, sizeof(zero_hop_));
    memset(history_spectrum_, 0, sizeof(history_spectrum_));
    memset(history_magnitude_, 0, sizeof(history_magnitude_));
  }

  // Recibe 512 muestras consecutivas a 8192 Hz.
  // Devuelve true cuando hay 512 muestras filtradas disponibles.
  // La primera llamada solo llena el primer frame, por lo que no produce salida.
  bool pushHop(const float* input, float* output, Stats* stats = nullptr) {
    if (input == nullptr || output == nullptr) return false;
    const uint32_t t0 = clockMicros();

    // Frame de 1024: mitad anterior + mitad recibida.
    for (size_t i = 0; i < HOP_SIZE; ++i) {
      work_[i].re = previous_hop_[i] * window_[i];
      work_[i].im = 0.0f;
      work_[i + HOP_SIZE].re = input[i] * window_[i + HOP_SIZE];
      work_[i + HOP_SIZE].im = 0.0f;
    }
    fft(false);

    for (size_t k = 0; k < BINS; ++k) {
      current_spectrum_[k] = work_[k];
      current_magnitude_[k] = sqrtf(work_[k].re * work_[k].re +
                                    work_[k].im * work_[k].im);
    }
    decideGains();

    bool produced = false;
    if (has_previous_) {
      synthesizeHop(output);
      produced = true;
      ++blocks_emitted_;
    }

    // Guardar el frame actual para formar la siguiente ventana.
    memcpy(previous_spectrum_, current_spectrum_, sizeof(previous_spectrum_));
    memcpy(previous_gains_, current_gains_, sizeof(previous_gains_));
    has_previous_ = true;
    memcpy(previous_hop_, input, sizeof(previous_hop_));
    ++frames_processed_;

    if (stats) {
      stats->processing_us = clockMicros() - t0;
      stats->frames_processed = frames_processed_;
      stats->outputs_produced = blocks_emitted_;
    }
    return produced;
  }

  // Cierra un flujo finito: genera el ultimo frame con 512 ceros y devuelve
  // el ultimo hop pendiente. En flujo continuo NO llamar entre bloques.
  bool finish(float* output, Stats* stats = nullptr) {
    if (output == nullptr || !has_previous_) return false;
    const bool produced = pushHop(zero_hop_, output, stats);
    reset();
    return produced;
  }

  uint32_t framesProcessed() const { return frames_processed_; }
  uint32_t blocksEmitted() const { return blocks_emitted_; }

private:
  struct Complex32 { float re; float im; };

  float window_[FFT_SIZE];
  float previous_hop_[HOP_SIZE];
  float zero_hop_[HOP_SIZE];
  float left_[HOP_SIZE];
  Complex32 work_[FFT_SIZE];

  Complex32 previous_spectrum_[BINS];
  float previous_gains_[BINS];
  Complex32 current_spectrum_[BINS];
  float current_magnitude_[BINS];
  float current_gains_[BINS];

  Complex32 history_spectrum_[HISTORY][BINS];
  float history_magnitude_[HISTORY][BINS];
  size_t history_write_;
  size_t history_count_;
  bool has_previous_;
  uint32_t frames_processed_;
  uint32_t blocks_emitted_;

  float mean_magnitude_[BINS];
  float coherence_integer_[BINS];
  float coherence_fractional_[BINS];
  uint8_t protected_[BINS];
  uint16_t tone_bins_[64];

  static uint32_t clockMicros() {
#ifdef ARDUINO
    return micros();
#else
    using namespace std::chrono;
    return (uint32_t)duration_cast<microseconds>(
      steady_clock::now().time_since_epoch()).count();
#endif
  }

  static Complex32 multiply(const Complex32& a, const Complex32& b) {
    Complex32 z = {a.re * b.re - a.im * b.im,
                   a.re * b.im + a.im * b.re};
    return z;
  }

  static Complex32 conjugate(const Complex32& a) {
    Complex32 z = {a.re, -a.im};
    return z;
  }

  void decideGains() {
    float current_max = 0.0f;
    for (size_t k = 0; k < BINS; ++k) {
      if (current_magnitude_[k] > current_max) current_max = current_magnitude_[k];
    }
    const float threshold = current_max * 0.10f;
    for (size_t k = 0; k < BINS; ++k) {
      current_gains_[k] = current_magnitude_[k] < threshold ? 0.10f : 1.0f;
    }

    // Añadir el espectro actual al historial antes de calcular coherencia.
    for (size_t k = 0; k < BINS; ++k) {
      history_spectrum_[history_write_][k] = current_spectrum_[k];
      history_magnitude_[history_write_][k] = current_magnitude_[k];
    }
    history_write_ = (history_write_ + 1) % HISTORY;
    if (history_count_ < HISTORY) ++history_count_;

    if (history_count_ < 2) return;

    const size_t oldest = (history_write_ + HISTORY - history_count_) % HISTORY;
    float pass_max = 0.0f;
    for (size_t k = 0; k < BINS; ++k) {
      float sum_mag = 0.0f;
      for (size_t h = 0; h < history_count_; ++h) {
        const size_t idx = (oldest + h) % HISTORY;
        sum_mag += history_magnitude_[idx][k];
      }
      mean_magnitude_[k] = sum_mag / (float)history_count_;
      const float freq = (float)k * 8.0f;
      if (freq <= 1350.0f && mean_magnitude_[k] > pass_max)
        pass_max = mean_magnitude_[k];
    }

    // Coherencia de fase a bin exacto y con compensacion sub-bin.
    for (size_t k = 0; k < BINS; ++k) {
      float sum_re = 0.0f, sum_im = 0.0f;
      for (size_t h = 0; h < history_count_; ++h) {
        const size_t idx = (oldest + h) % HISTORY;
        float sign = ((k & 1U) && (h & 1U)) ? -1.0f : 1.0f;
        sum_re += history_spectrum_[idx][k].re * sign;
        sum_im += history_spectrum_[idx][k].im * sign;
      }
      const float denominator = (float)history_count_ * (mean_magnitude_[k] + 1e-15f);
      coherence_integer_[k] = sqrtf(sum_re * sum_re + sum_im * sum_im) /
                              ((float)history_count_ * (mean_magnitude_[k] + 1e-15f));

      float product_re = 0.0f, product_im = 0.0f;
      for (size_t h = 1; h < history_count_; ++h) {
        const size_t idx_now = (oldest + h) % HISTORY;
        const size_t idx_prev = (oldest + h - 1) % HISTORY;
        Complex32 a = history_spectrum_[idx_now][k];
        Complex32 b = conjugate(history_spectrum_[idx_prev][k]);
        Complex32 p = multiply(a, b);
        if (k & 1U) { p.re = -p.re; p.im = -p.im; }
        product_re += p.re;
        product_im += p.im;
      }
      const float residual_step = atan2f(product_im, product_re);
      float frac_re = 0.0f, frac_im = 0.0f;
      const float step_re = cosf(-residual_step);
      const float step_im = sinf(-residual_step);
      float rot_re = 1.0f, rot_im = 0.0f;
      for (size_t h = 0; h < history_count_; ++h) {
        const size_t idx = (oldest + h) % HISTORY;
        const float sign = ((k & 1U) && (h & 1U)) ? -1.0f : 1.0f;
        const float xr = history_spectrum_[idx][k].re * sign;
        const float xi = history_spectrum_[idx][k].im * sign;
        frac_re += xr * rot_re - xi * rot_im;
        frac_im += xr * rot_im + xi * rot_re;
        const float next_rot_re = rot_re * step_re - rot_im * step_im;
        const float next_rot_im = rot_re * step_im + rot_im * step_re;
        rot_re = next_rot_re; rot_im = next_rot_im;
      }
      coherence_fractional_[k] = sqrtf(frac_re * frac_re + frac_im * frac_im) /
                                 denominator;
    }

    memset(protected_, 0, sizeof(protected_));
    const float coherent_peak_threshold = 0.05f * pass_max;
    for (size_t k = 0; k < BINS; ++k) {
      const float freq = (float)k * 8.0f;
      if (freq <= 1350.0f && coherence_integer_[k] >= 0.80f &&
          mean_magnitude_[k] >= coherent_peak_threshold) {
        const size_t lo = k > 2 ? k - 2 : 0;
        const size_t hi = (k + 2 < BINS) ? k + 2 : BINS - 1;
        for (size_t q = lo; q <= hi; ++q) protected_[q] = 1;
      }
    }

    // Piso elevado en 850-1300 Hz frente a bandas de guarda.
    float band_sum = 0.0f, guard_sum = 0.0f;
    size_t band_count = 0, guard_count = 0;
    for (size_t k = 0; k < BINS; ++k) {
      const float freq = (float)k * 8.0f;
      if (freq >= 850.0f && freq <= 1300.0f && !protected_[k]) {
        band_sum += mean_magnitude_[k];
        ++band_count;
      }
      if ((freq >= 700.0f && freq < 850.0f) ||
          (freq >= 1300.0f && freq <= 1450.0f)) {
        guard_sum += mean_magnitude_[k];
        ++guard_count;
      }
    }
    const float band_floor = band_count ? band_sum / (float)band_count : 0.0f;
    const float guard_floor = guard_count ? guard_sum / (float)guard_count : 0.0f;
    const float band_ratio = band_floor / (guard_floor + 1e-15f);
    const bool band_noise_present = band_ratio >= 3.0f;
    if (band_noise_present) {
      for (size_t k = 0; k < BINS; ++k) {
        const float freq = (float)k * 8.0f;
        if (freq >= 850.0f && freq <= 1300.0f &&
            coherence_integer_[k] < 0.65f && !protected_[k]) {
          current_gains_[k] *= 0.10f;
        }
        if (protected_[k]) current_gains_[k] = 1.0f;
      }
    }

    // Picos tonales persistentes fuera de la banda util protegida (>1500 Hz).
    float high_max = 0.0f;
    for (size_t k = 0; k < BINS; ++k) {
      if ((float)k * 8.0f >= 1500.0f && mean_magnitude_[k] > high_max)
        high_max = mean_magnitude_[k];
    }
    const float high_floor = 0.15f * high_max;
    size_t tone_count = 0;
    for (size_t k = 188; k + 6 < BINS; ++k) {
      if (!(mean_magnitude_[k] >= mean_magnitude_[k - 1] &&
            mean_magnitude_[k] > mean_magnitude_[k + 1])) continue;
      float neighbors = 0.0f;
      for (size_t q = k - 6; q <= k - 2; ++q) neighbors += mean_magnitude_[q];
      for (size_t q = k + 2; q <= k + 6; ++q) neighbors += mean_magnitude_[q];
      const float local_floor = neighbors / 10.0f + 1e-15f;
      const float prominence = mean_magnitude_[k] / local_floor;
      if (mean_magnitude_[k] < high_floor || prominence < 6.0f ||
          coherence_fractional_[k] < 0.90f) continue;
      bool duplicate = false;
      for (size_t j = 0; j < tone_count; ++j) {
        const int diff = (int)k - (int)tone_bins_[j];
        if (diff >= -2 && diff <= 2) { duplicate = true; break; }
      }
      if (!duplicate && tone_count < 64) tone_bins_[tone_count++] = (uint16_t)k;
    }
    for (size_t t = 0; t < tone_count; ++t) {
      const size_t k = tone_bins_[t];
      const size_t lo = k > 2 ? k - 2 : 0;
      const size_t hi = (k + 2 < BINS) ? k + 2 : BINS - 1;
      for (size_t q = lo; q <= hi; ++q) {
        if (current_gains_[q] > 0.005f) current_gains_[q] = 0.005f;
      }
    }
  }

  void synthesizeHop(float* output) {
    // IFFT del frame previo: usar mitad derecha.
    buildFullSpectrum(previous_spectrum_, previous_gains_);
    fft(true);
    for (size_t i = 0; i < HOP_SIZE; ++i) left_[i] = work_[i + HOP_SIZE].re;

    // IFFT del frame actual: usar mitad izquierda y sumar OLA.
    buildFullSpectrum(current_spectrum_, current_gains_);
    fft(true);
    for (size_t i = 0; i < HOP_SIZE; ++i) {
      const float norm = window_[i + HOP_SIZE] + window_[i];
      const float sum = left_[i] + work_[i].re;
      output[i] = (norm > 1e-8f) ? sum / norm : 0.0f;
    }
  }

  void buildFullSpectrum(const Complex32 positive[BINS], const float gains[BINS]) {
    for (size_t k = 0; k < BINS; ++k) {
      work_[k].re = positive[k].re * gains[k];
      work_[k].im = positive[k].im * gains[k];
    }
    work_[0].im = 0.0f;
    work_[FFT_SIZE / 2].im = 0.0f;
    for (size_t k = 1; k < FFT_SIZE / 2; ++k) {
      work_[FFT_SIZE - k].re = work_[k].re;
      work_[FFT_SIZE - k].im = -work_[k].im;
    }
  }

  void fft(bool inverse) {
    size_t j = 0;
    for (size_t i = 1; i < FFT_SIZE; ++i) {
      size_t bit = FFT_SIZE >> 1;
      while (j & bit) { j ^= bit; bit >>= 1; }
      j ^= bit;
      if (i < j) {
        const Complex32 temp = work_[i];
        work_[i] = work_[j];
        work_[j] = temp;
      }
    }
    const float pi = 3.14159265358979323846f;
    for (size_t len = 2; len <= FFT_SIZE; len <<= 1) {
      const float angle = (inverse ? 2.0f : -2.0f) * pi / (float)len;
      const float wlen_re = cosf(angle), wlen_im = sinf(angle);
      for (size_t base = 0; base < FFT_SIZE; base += len) {
        float wr = 1.0f, wi = 0.0f;
        const size_t half = len >> 1;
        for (size_t q = 0; q < half; ++q) {
          const Complex32 u = work_[base + q];
          const Complex32 z = work_[base + q + half];
          const Complex32 v = {z.re * wr - z.im * wi,
                               z.re * wi + z.im * wr};
          work_[base + q].re = u.re + v.re;
          work_[base + q].im = u.im + v.im;
          work_[base + q + half].re = u.re - v.re;
          work_[base + q + half].im = u.im - v.im;
          const float next_wr = wr * wlen_re - wi * wlen_im;
          const float next_wi = wr * wlen_im + wi * wlen_re;
          wr = next_wr; wi = next_wi;
        }
      }
    }
    if (inverse) {
      const float scale = 1.0f / (float)FFT_SIZE;
      for (size_t i = 0; i < FFT_SIZE; ++i) {
        work_[i].re *= scale;
        work_[i].im *= scale;
      }
    }
  }
};

#endif
