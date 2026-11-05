#pragma once

#include <stddef.h>

// FIR pasa-bajas equivalente a:
// scipy.signal.firwin(numtaps=129, cutoff=1350.0,
//                     window="hamming", fs=8192)
//
// Entrada y salida en las mismas unidades (por ejemplo, cuentas ADC).
// Inicializacion equivalente a scipy.signal.lfilter con estado inicial cero.
// Frecuencia de muestreo de diseno: 8192 Hz.
// Retardo de grupo: 64 muestras = 7.8125 ms.

namespace fir129_detail {
static const float COEFFICIENTS[129] = {
    -1.1543748199e-04f, 2.7456100915e-04f, 4.1298276602e-04f,
    1.4353240726e-04f, -3.0548060077e-04f, -4.9839155724e-04f,
    -1.9545804297e-04f, 3.7063567578e-04f, 6.4745818780e-04f,
    2.7992661571e-04f, -4.6943147106e-04f, -8.6870583385e-04f,
    -4.0669494793e-04f, 6.0043692576e-04f, 1.1709475349e-03f,
    5.8669088128e-04f, -7.6140870503e-04f, -1.5635009491e-03f,
    -8.3223258378e-04f, 9.4933628727e-04f, 2.0565487799e-03f,
    1.1573925033e-03f, -1.1605071555e-03f, -2.6617131823e-03f,
    -1.5785868878e-03f, 1.3905905874e-03f, 3.3929536612e-03f,
    2.1155220411e-03f, -1.6347380283e-03f, -4.2679712668e-03f,
    -2.7927185109e-03f, 1.8876975735e-03f, 5.3104374285e-03f,
    3.6420028038e-03f, -2.1439396918e-03f, -6.5536279985e-03f,
    -4.7066870655e-03f, 2.3977910018e-03f, 8.0465782203e-03f,
    6.0488454988e-03f, -2.6435726795e-03f, -9.8650384030e-03f,
    -7.7626297373e-03f, 2.8757399310e-03f, 1.2132246465e-02f,
    1.0000278463e-02f, -3.0890189180e-03f, -1.5061616842e-02f,
    -1.3027456176e-02f, 3.2785375725e-03f, 1.9054190398e-02f,
    1.7355263628e-02f, -3.4399468858e-03f, -2.4955356190e-02f,
    -2.4109882054e-02f, 3.5695294930e-03f, 3.4888897202e-02f,
    3.6352682419e-02f, -3.6642927045e-03f, -5.6093077938e-02f,
    -6.6340620170e-02f, 3.7220435360e-03f, 1.3928014926e-01f,
    2.7347245266e-01f, 3.2940972247e-01f, 2.7347245266e-01f,
    1.3928014926e-01f, 3.7220435360e-03f, -6.6340620170e-02f,
    -5.6093077938e-02f, -3.6642927045e-03f, 3.6352682419e-02f,
    3.4888897202e-02f, 3.5695294930e-03f, -2.4109882054e-02f,
    -2.4955356190e-02f, -3.4399468858e-03f, 1.7355263628e-02f,
    1.9054190398e-02f, 3.2785375725e-03f, -1.3027456176e-02f,
    -1.5061616842e-02f, -3.0890189180e-03f, 1.0000278463e-02f,
    1.2132246465e-02f, 2.8757399310e-03f, -7.7626297373e-03f,
    -9.8650384030e-03f, -2.6435726795e-03f, 6.0488454988e-03f,
    8.0465782203e-03f, 2.3977910018e-03f, -4.7066870655e-03f,
    -6.5536279985e-03f, -2.1439396918e-03f, 3.6420028038e-03f,
    5.3104374285e-03f, 1.8876975735e-03f, -2.7927185109e-03f,
    -4.2679712668e-03f, -1.6347380283e-03f, 2.1155220411e-03f,
    3.3929536612e-03f, 1.3905905874e-03f, -1.5785868878e-03f,
    -2.6617131823e-03f, -1.1605071555e-03f, 1.1573925033e-03f,
    2.0565487799e-03f, 9.4933628727e-04f, -8.3223258378e-04f,
    -1.5635009491e-03f, -7.6140870503e-04f, 5.8669088128e-04f,
    1.1709475349e-03f, 6.0043692576e-04f, -4.0669494793e-04f,
    -8.6870583385e-04f, -4.6943147106e-04f, 2.7992661571e-04f,
    6.4745818780e-04f, 3.7063567578e-04f, -1.9545804297e-04f,
    -4.9839155724e-04f, -3.0548060077e-04f, 1.4353240726e-04f,
    4.1298276602e-04f, 2.7456100915e-04f, -1.1543748199e-04f
};
}  // namespace fir129_detail

class FIRLowPass129 {
public:
    static const size_t TAPS = 129;

    FIRLowPass129() : writeIndex_(0) {
        reset();
    }

    // Usar al iniciar una nueva captura independiente para reproducir
    // la condicion inicial cero de scipy.signal.lfilter.
    void reset() {
        for (size_t i = 0; i < TAPS; ++i) {
            delay_[i] = 0.0f;
        }
        writeIndex_ = 0;
    }

    // Procesa una muestra y devuelve una muestra filtrada.
    // Para bloques consecutivos de una misma senal NO llamar reset()
    // entre bloques: el historial debe conservarse.
    float process(float sample) {
        delay_[writeIndex_] = sample;

        float accumulator = 0.0f;
        int index = static_cast<int>(writeIndex_);
        for (size_t k = 0; k < TAPS; ++k) {
            accumulator += fir129_detail::COEFFICIENTS[k] * delay_[index];
            --index;
            if (index < 0) {
                index = static_cast<int>(TAPS - 1);
            }
        }

        ++writeIndex_;
        if (writeIndex_ == TAPS) {
            writeIndex_ = 0;
        }
        return accumulator;
    }

private:
    float delay_[TAPS];
    size_t writeIndex_;
};
