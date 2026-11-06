#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include "fft_ola.h"

static constexpr size_t MAX_SAMPLES = SpectralOLA1024::MAX_SAMPLES;
// Un solo buffer de 64 KiB: la salida se reconstruye in-place.
static float samples[MAX_SAMPLES];
static SpectralOLA1024 spectralFilter;

static void sendError(const char* message) {
  Serial.print("ERR,");
  Serial.println(message);
  Serial.flush();
}

// Lee exactamente 'expected' bytes. El temporizador se reinicia con cada byte.
static bool readExact(uint8_t* destination, size_t expected,
                      uint32_t idleTimeoutMs) {
  size_t received = 0;
  uint32_t lastByteMs = millis();

  while (received < expected) {
    while (Serial.available() > 0 && received < expected) {
      const int value = Serial.read();
      if (value >= 0) {
        destination[received++] = (uint8_t)value;
        lastByteMs = millis();
      }
    }

    if ((uint32_t)(millis() - lastByteMs) > idleTimeoutMs) {
      return false;
    }
    delay(0); // Cede tiempo al sistema mientras llegan más bytes.
  }
  return true;
}

void setup() {
  // Importante: el tamaño RX debe configurarse ANTES de Serial.begin().
  Serial.setRxBufferSize(8192);
  Serial.begin(921600);
  Serial.setTimeout(15000);
  delay(500);
  Serial.println("READY,NODE3_FFT_OLA,1024,512,16384");
}

void loop() {
  if (!Serial.available()) return;

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (command == "PING") {
    Serial.println("PONG,NODE3_FFT_OLA");
    return;
  }
  if (command == "RESET") {
    spectralFilter.resetMask();
    Serial.println("OK,RESET");
    return;
  }

  char operation[12] = {0};
  unsigned long sampleCount = 0;
  unsigned long blockSize = 0;
  float threshold = 0.0f;
  const int parsed = sscanf(command.c_str(), "%11[^,],%lu,%lu,%f",
                            operation, &sampleCount, &blockSize, &threshold);

  if (parsed != 4) {
    sendError("Comando invalido. Use LEARN,n,1024,umbral o REPLAY,n,1024,umbral");
    return;
  }

  const bool learn = (strcmp(operation, "LEARN") == 0);
  const bool replay = (strcmp(operation, "REPLAY") == 0);
  if (!learn && !replay) {
    sendError("Operacion desconocida");
    return;
  }
  if (sampleCount == 0 || sampleCount > MAX_SAMPLES || blockSize != 1024 ||
      !(threshold >= 0.0f && threshold <= 1.0f)) {
    sendError("Parametros fuera de rango");
    return;
  }

  const size_t bytesExpected = (size_t)sampleCount * sizeof(float);

  // Handshake: Python espera esta confirmación ANTES de mandar el arreglo.
  Serial.printf("READY_DATA,%lu\n", sampleCount);
  Serial.flush();

  const bool received = readExact((uint8_t*)samples, bytesExpected, 10000);
  if (!received) {
    sendError("Bloque de entrada incompleto o tiempo de recepcion agotado");
    return;
  }

  SpectralOLA1024::Stats stats = {0, 0, 0};
  const bool ok = spectralFilter.processInPlace(
      samples, (size_t)sampleCount, threshold, learn, &stats);

  if (!ok) {
    sendError(learn ? "Error procesando LEARN" :
              "Mascara ausente o incompatible en REPLAY");
    return;
  }

  Serial.printf("BEGIN,%lu,%lu,%lu,%lu\n",
                sampleCount,
                (unsigned long)stats.total_us,
                (unsigned long)stats.max_frame_us,
                (unsigned long)stats.frame_count);
  Serial.write((const uint8_t*)samples, bytesExpected);
  Serial.println("END");
  Serial.flush();
}
