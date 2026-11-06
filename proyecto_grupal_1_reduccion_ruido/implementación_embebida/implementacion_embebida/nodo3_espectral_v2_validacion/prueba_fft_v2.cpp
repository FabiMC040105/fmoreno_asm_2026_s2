#include <cstdio>
#include <cstdlib>
#include <vector>
#include "fft_ola_v2_stream.h"

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "Uso: prueba_fft_v2 entrada_float32.bin salida_float32.bin\n");
    return 2;
  }
  FILE* in = std::fopen(argv[1], "rb");
  if (!in) { std::perror("entrada"); return 3; }
  std::vector<float> x;
  float value;
  while (std::fread(&value, sizeof(float), 1, in) == 1) x.push_back(value);
  std::fclose(in);
  if (x.empty() || x.size() % 512 != 0) {
    std::fprintf(stderr, "La entrada debe contener bloques completos de 512 muestras.\n");
    return 4;
  }

  SpectralOLA1024V2Stream filter;
  std::vector<float> y;
  float hop_out[512];
  SpectralOLA1024V2Stream::Stats stats{};
  uint64_t total_us = 0;
  uint32_t max_call_us = 0;
  for (size_t i = 0; i < x.size(); i += 512) {
    const bool produced = filter.pushHop(&x[i], hop_out, &stats);
    total_us += stats.processing_us;
    if (stats.processing_us > max_call_us) max_call_us = stats.processing_us;
    if (produced) y.insert(y.end(), hop_out, hop_out + 512);
  }
  if (filter.finish(hop_out, &stats)) y.insert(y.end(), hop_out, hop_out + 512);
  const uint32_t total_frames = stats.frames_processed;

  FILE* out = std::fopen(argv[2], "wb");
  if (!out) { std::perror("salida"); return 5; }
  if (std::fwrite(y.data(), sizeof(float), y.size(), out) != y.size()) {
    std::fprintf(stderr, "Error escribiendo salida.\n"); std::fclose(out); return 6;
  }
  std::fclose(out);
  std::printf("OK: entrada=%zu, salida=%zu, llamadas=%u, tiempo_total=%llu us, max_llamada=%u us\n",
      x.size(), y.size(), (unsigned)total_frames,
      (unsigned long long)total_us, max_call_us);
  return y.size() == x.size() ? 0 : 7;
}
