#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
#include "acondicionamiento_nodo1.h"

int main() {
    const double PI = 3.14159265358979323846;
    const size_t total = 24576 * 2;
    std::vector<uint16_t> raw(total);
    const double fs = 24576.0;
    for (size_t n = 0; n < total; ++n) {
        const double t = static_cast<double>(n) / fs;
        double v = 2048.0
            + 500.0 * std::sin(2.0 * PI * 256.0 * t)
            + 310.0 * std::sin(2.0 * PI * 512.0 * t + 0.4)
            + 180.0 * std::sin(2.0 * PI * 1024.0 * t + 0.9)
            + 160.0 * std::sin(2.0 * PI * 5000.0 * t + 0.2);
        raw[n] = static_cast<uint16_t>(std::lround(v));
    }

    Nodo1Decimator3 decimator;
    std::vector<float> output;
    for (size_t offset = 0; offset < total; offset += Nodo1Decimator3::RAW_BLOCK) {
        float block[Nodo1Decimator3::OUTPUT_BLOCK];
        size_t count = 0;
        if (!decimator.process(raw.data() + offset, Nodo1Decimator3::RAW_BLOCK,
                               block, Nodo1Decimator3::OUTPUT_BLOCK, &count)) {
            std::cerr << "Error procesando bloque\n";
            return 1;
        }
        if (count != Nodo1Decimator3::OUTPUT_BLOCK) {
            std::cerr << "Cantidad de salida incorrecta: " << count << "\n";
            return 2;
        }
        Nodo1Decimator3::removeDcAndNormalize(block, count);
        output.insert(output.end(), block, block + count);
    }
    std::ofstream csv("salida_cpp_nodo1.csv");
    csv << "muestra,valor_normalizado\n";
    for (size_t i = 0; i < output.size(); ++i) csv << i << "," << output[i] << "\n";
    std::cout << "OK: " << output.size() << " muestras a 8192 Hz; bloques="
              << output.size() / 1024 << "\n";
    std::cout << "Salida CSV: salida_cpp_nodo1.csv\n";
    return 0;
}
