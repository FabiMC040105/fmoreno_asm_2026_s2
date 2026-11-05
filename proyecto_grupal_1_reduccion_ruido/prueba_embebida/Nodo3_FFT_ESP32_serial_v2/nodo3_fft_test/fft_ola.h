#ifndef FFT_OLA_H
#define FFT_OLA_H

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

#ifdef ARDUINO
  #include <Arduino.h>
#else
  #include <chrono>
#endif

// Nodo 3: FFT 1024, Hann periodica, hop 512, umbral relativo y OLA.
// processInPlace() recibe y devuelve el resultado en el mismo arreglo.
// La mascara se almacena empaquetada: 1 bit por bin (65 bytes por frame).

class SpectralOLA1024 {
public:
  static constexpr size_t FFT_SIZE = 1024;
  static constexpr size_t HOP_SIZE = FFT_SIZE / 2;
  static constexpr size_t MAX_SAMPLES = 16384;
  static constexpr size_t MAX_FRAMES = 33;
  static constexpr size_t BINS = FFT_SIZE / 2 + 1;
  static constexpr size_t MASK_BYTES = (BINS + 7) / 8;

  struct Stats {
    uint32_t total_us;
    uint32_t max_frame_us;
    uint32_t frame_count;
  };

  SpectralOLA1024()
    : mask_ready_(false), mask_frames_(0), mask_length_(0),
      mask_threshold_(0.0f), emitted_(0) {
    const float two_pi = 6.2831853071795864769f;
    for (size_t n = 0; n < FFT_SIZE; ++n) {
      window_[n] = 0.5f - 0.5f *
        cosf(two_pi * (float)n / (float)FFT_SIZE);
    }
    memset(mask_, 0, sizeof(mask_));
    memset(accumulator_, 0, sizeof(accumulator_));
  }

  bool processInPlace(float* data, size_t length,
                      float relative_threshold, bool learn_mask,
                      Stats* stats = nullptr) {
    if (data == nullptr || length == 0 || length > MAX_SAMPLES) return false;
    if (!(relative_threshold >= 0.0f && relative_threshold <= 1.0f)) return false;

    const size_t padded_length = paddedLength(length);
    const size_t frame_count = (padded_length - FFT_SIZE) / HOP_SIZE + 1;
    if (frame_count > MAX_FRAMES) return false;

    if (learn_mask) {
      mask_ready_ = false;
    } else {
      if (!mask_ready_ || mask_length_ != length || mask_frames_ != frame_count)
        return false;
      if (fabsf(relative_threshold - mask_threshold_) > 1e-6f)
        return false;
    }

    memset(accumulator_, 0, sizeof(accumulator_));
    emitted_ = 0;
    const uint32_t total_start = clockMicros();
    uint32_t max_frame_us = 0;
    size_t frame_index = 0;

    for (size_t start = 0; start + FFT_SIZE <= padded_length;
         start += HOP_SIZE, ++frame_index) {
      const uint32_t frame_start = clockMicros();

      // Primero se copia la ventana completa al arreglo complejo.
      // Así es seguro sobrescribir muestras ya procesadas más adelante.
      for (size_t i = 0; i < FFT_SIZE; ++i) {
        const size_t padded_index = start + i;
        float sample = 0.0f;
        if (padded_index >= HOP_SIZE && padded_index < HOP_SIZE + length)
          sample = data[padded_index - HOP_SIZE];
        frame_[i].re = sample * window_[i];
        frame_[i].im = 0.0f;
      }

      fft(false);

      if (learn_mask) {
        float maximum = 0.0f;
        for (size_t k = 0; k < BINS; ++k) {
          const float mag = sqrtf(frame_[k].re * frame_[k].re +
                                  frame_[k].im * frame_[k].im);
          if (mag > maximum) maximum = mag;
        }
        const float threshold = maximum * relative_threshold;
        for (size_t k = 0; k < BINS; ++k) {
          const float mag = sqrtf(frame_[k].re * frame_[k].re +
                                  frame_[k].im * frame_[k].im);
          setMaskBit(frame_index, k, mag < threshold);
        }
      }

      // Aplicar la máscara simétricamente para conservar simetría hermítica.
      for (size_t k = 0; k < BINS; ++k) {
        const float gain = getMaskBit(frame_index, k) ? 0.1f : 1.0f;
        frame_[k].re *= gain;
        frame_[k].im *= gain;
        if (k > 0 && k < FFT_SIZE / 2) {
          const size_t mirror = FFT_SIZE - k;
          frame_[mirror].re *= gain;
          frame_[mirror].im *= gain;
        }
      }

      fft(true);

      // Acumular solo las muestras que pertenecen a la señal original.
      for (size_t i = 0; i < FFT_SIZE; ++i) {
        const size_t padded_index = start + i;
        if (padded_index >= HOP_SIZE && padded_index < HOP_SIZE + length) {
          const size_t original_index = padded_index - HOP_SIZE;
          accumulator_[original_index % FFT_SIZE] += frame_[i].re;
        }
      }

      // La siguiente ventana comienza en la muestra original 'start'.
      // Por tanto, las muestras anteriores a 'start' ya no recibirán
      // contribuciones futuras y pueden escribirse en el mismo buffer.
      size_t safe_end = start;
      if (safe_end > length) safe_end = length;
      while (emitted_ < safe_end) {
        const size_t slot = emitted_ % FFT_SIZE;
        data[emitted_] = accumulator_[slot];
        accumulator_[slot] = 0.0f;
        ++emitted_;
      }

      const uint32_t elapsed = clockMicros() - frame_start;
      if (elapsed > max_frame_us) max_frame_us = elapsed;
    }

    // Vaciar las últimas muestras que quedan pendientes.
    while (emitted_ < length) {
      const size_t slot = emitted_ % FFT_SIZE;
      data[emitted_] = accumulator_[slot];
      accumulator_[slot] = 0.0f;
      ++emitted_;
    }

    const uint32_t total_us = clockMicros() - total_start;

    if (learn_mask) {
      mask_ready_ = true;
      mask_frames_ = frame_count;
      mask_length_ = length;
      mask_threshold_ = relative_threshold;
    }

    if (stats) {
      stats->total_us = total_us;
      stats->max_frame_us = max_frame_us;
      stats->frame_count = (uint32_t)frame_count;
    }
    return true;
  }

  bool maskAttenuates(size_t frame, size_t bin) const {
    return frame < mask_frames_ && bin < BINS && getMaskBit(frame, bin);
  }

  size_t learnedFrameCount() const { return mask_frames_; }

  void resetMask() {
    mask_ready_ = false;
    mask_frames_ = 0;
    mask_length_ = 0;
    mask_threshold_ = 0.0f;
    emitted_ = 0;
    memset(mask_, 0, sizeof(mask_));
    memset(accumulator_, 0, sizeof(accumulator_));
  }

private:
  struct Complex32 { float re; float im; };

  // Memoria aproximada de los buffers internos:
  // frame 8192 B + ventana 4096 B + acumulador 4096 B
  // + mascara 2145 B, además de variables de control.
  Complex32 frame_[FFT_SIZE];
  float window_[FFT_SIZE];
  float accumulator_[FFT_SIZE];
  uint8_t mask_[MAX_FRAMES][MASK_BYTES];
  bool mask_ready_;
  size_t mask_frames_;
  size_t mask_length_;
  float mask_threshold_;
  size_t emitted_;

  void setMaskBit(size_t frame, size_t bin, bool value) {
    const uint8_t bit = (uint8_t)(1U << (bin & 7U));
    uint8_t& byte = mask_[frame][bin >> 3U];
    if (value) byte |= bit;
    else byte &= (uint8_t)~bit;
  }

  bool getMaskBit(size_t frame, size_t bin) const {
    return (mask_[frame][bin >> 3U] & (uint8_t)(1U << (bin & 7U))) != 0;
  }

  static uint32_t clockMicros() {
#ifdef ARDUINO
    return micros();
#else
    using namespace std::chrono;
    return (uint32_t)duration_cast<microseconds>(
      steady_clock::now().time_since_epoch()).count();
#endif
  }

  static size_t paddedLength(size_t length) {
    const size_t total = HOP_SIZE + length + HOP_SIZE;
    const size_t remainder = (total - FFT_SIZE) % HOP_SIZE;
    const size_t extra = (HOP_SIZE - remainder) % HOP_SIZE;
    return total + extra;
  }

  void fft(bool inverse) {
    size_t j = 0;
    for (size_t i = 1; i < FFT_SIZE; ++i) {
      size_t bit = FFT_SIZE >> 1;
      while (j & bit) {
        j ^= bit;
        bit >>= 1;
      }
      j ^= bit;
      if (i < j) {
        const Complex32 temp = frame_[i];
        frame_[i] = frame_[j];
        frame_[j] = temp;
      }
    }

    const float pi = 3.14159265358979323846f;
    for (size_t len = 2; len <= FFT_SIZE; len <<= 1) {
      const float angle = (inverse ? 2.0f : -2.0f) * pi / (float)len;
      const float wlen_re = cosf(angle);
      const float wlen_im = sinf(angle);
      for (size_t base = 0; base < FFT_SIZE; base += len) {
        float w_re = 1.0f;
        float w_im = 0.0f;
        const size_t half = len >> 1;
        for (size_t k = 0; k < half; ++k) {
          const Complex32 u = frame_[base + k];
          const Complex32 z = frame_[base + k + half];
          const Complex32 v = {
            z.re * w_re - z.im * w_im,
            z.re * w_im + z.im * w_re
          };
          frame_[base + k].re = u.re + v.re;
          frame_[base + k].im = u.im + v.im;
          frame_[base + k + half].re = u.re - v.re;
          frame_[base + k + half].im = u.im - v.im;
          const float next_re = w_re * wlen_re - w_im * wlen_im;
          const float next_im = w_re * wlen_im + w_im * wlen_re;
          w_re = next_re;
          w_im = next_im;
        }
      }
    }

    if (inverse) {
      const float scale = 1.0f / (float)FFT_SIZE;
      for (size_t i = 0; i < FFT_SIZE; ++i) {
        frame_[i].re *= scale;
        frame_[i].im *= scale;
      }
    }
  }
};

#endif
