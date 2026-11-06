#pragma once

#include <stddef.h>
#include <stdint.h>
#include <math.h>

// Referencia C++ del acondicionamiento del Nodo 1.
// ESP32 clasico: ADC continuo nominal 24576 Hz -> 8192 Hz (decimacion 3:1).
// Antialias: FIR 61 taps, ventana Hamming, corte 3000 Hz.
// Los bloques de entrada deben contener 3072 muestras; la salida contiene 1024.
// Mantener el objeto vivo entre bloques para preservar estado y fase.

class Nodo1Decimator3 {
public:
    static constexpr size_t TAPS = 61;
    static constexpr size_t DECIMATION = 3;
    static constexpr size_t RAW_BLOCK = 3072;
    static constexpr size_t OUTPUT_BLOCK = 1024;
    static constexpr float FS_ADC_HZ = 24576.0f;
    static constexpr float FS_OUTPUT_HZ = 8192.0f;
    static constexpr float CUTOFF_HZ = 3000.0f;
    static constexpr size_t GROUP_DELAY_RAW = 30;

    Nodo1Decimator3() : write_index_(0), phase_(0), initialized_(false) {
        for (size_t i = 0; i < TAPS; ++i) delay_[i] = 0.0f;
    }

    void reset() {
        write_index_ = 0;
        phase_ = 0;
        initialized_ = false;
        for (size_t i = 0; i < TAPS; ++i) delay_[i] = 0.0f;
    }

    // Procesa n_raw muestras y escribe las muestras decimadas en output.
    // Devuelve false ante punteros invalidos, entrada vacia o falta de capacidad.
    bool process(const uint16_t* raw, size_t n_raw,
                 float* output, size_t output_capacity,
                 size_t* output_count) {
        if (raw == nullptr || output == nullptr || output_count == nullptr || n_raw == 0)
            return false;
        const size_t first_output_index = (DECIMATION - phase_) % DECIMATION;
        const size_t needed = (first_output_index < n_raw)
            ? (1 + (n_raw - 1 - first_output_index) / DECIMATION)
            : 0;
        if (output_capacity < needed) return false;

        if (!initialized_) {
            const float first = static_cast<float>(raw[0]);
            for (size_t i = 0; i < TAPS; ++i) delay_[i] = first;
            initialized_ = true;
        }

        size_t produced = 0;
        for (size_t n = 0; n < n_raw; ++n) {
            delay_[write_index_] = static_cast<float>(raw[n]);
            float acc = 0.0f;
            int idx = static_cast<int>(write_index_);
            for (size_t k = 0; k < TAPS; ++k) {
                acc += coefficients()[k] * delay_[static_cast<size_t>(idx)];
                --idx;
                if (idx < 0) idx = static_cast<int>(TAPS - 1);
            }
            ++write_index_;
            if (write_index_ == TAPS) write_index_ = 0;

            if (phase_ == 0) output[produced++] = acc;
            phase_ = (phase_ + 1) % DECIMATION;
        }
        *output_count = produced;
        return true;
    }

    // Elimina DC por bloque y normaliza cuentas ADC a escala aproximada [-1,1].
    // No usar esta función para inferir la calibración en voltios del ADC.
    static bool removeDcAndNormalize(float* block, size_t length,
                                     float adc_full_scale = 2048.0f) {
        if (block == nullptr || length == 0 || !(adc_full_scale > 0.0f)) return false;
        double sum = 0.0;
        for (size_t i = 0; i < length; ++i) sum += block[i];
        const float mean = static_cast<float>(sum / static_cast<double>(length));
        const float inv_scale = 1.0f / adc_full_scale;
        for (size_t i = 0; i < length; ++i) block[i] = (block[i] - mean) * inv_scale;
        return true;
    }

private:
    float delay_[TAPS];
    size_t write_index_;
    size_t phase_;
    bool initialized_;

    static const float* coefficients() {
        static const float values[TAPS] = {
    -0.000722427483767f, -0.000225397265609f, 0.000504437999381f,
    0.00115829309021f, 0.00130113637106f, 0.000575968110035f,
    -0.000951530193294f, -0.00256380640177f, -0.00308690622279f,
    -0.00158658505463f, 0.00177509783098f, 0.00535831030616f,
    0.00665081405238f, 0.00378523245858f, -0.00283994949489f,
    -0.0100018129703f, -0.0129253199717f, -0.00808066913089f,
    0.00396329885327f, 0.0175602487319f, 0.0240882685f,
    0.0166417364222f, -0.00494810065479f, -0.0317536294158f,
    -0.0480811057797f, -0.0381684968708f, 0.00561951832499f,
    0.0772491990755f, 0.157399263196f, 0.220272650015f,
    0.244064527146f, 0.220272650015f, 0.157399263196f,
    0.0772491990755f, 0.00561951832499f, -0.0381684968708f,
    -0.0480811057797f, -0.0317536294158f, -0.00494810065479f,
    0.0166417364222f, 0.0240882685f, 0.0175602487319f,
    0.00396329885327f, -0.00808066913089f, -0.0129253199717f,
    -0.0100018129703f, -0.00283994949489f, 0.00378523245858f,
    0.00665081405238f, 0.00535831030616f, 0.00177509783098f,
    -0.00158658505463f, -0.00308690622279f, -0.00256380640177f,
    -0.000951530193294f, 0.000575968110035f, 0.00130113637106f,
    0.00115829309021f, 0.000504437999381f, -0.000225397265609f,
    -0.000722427483767f,
        };
        return values;
    }
};
