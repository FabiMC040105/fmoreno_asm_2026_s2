/*
 * Nodo 2 + Nodo 3 en una ESP32 clasica (procesamiento paralelo).
 * Entrada UART2 RX GPIO16: paquetes N1B2 desde Nodo1 TX GPIO17.
 * FIR129 -> DAC GPIO25. FFT espectral v2 -> DAC GPIO26.
 * Frecuencia nominal: 8192 muestras/s, bloques de 1024 float32.
 *
 * Arduino-ESP32 3.x / ESP-IDF 5.x; ESP32 clasico (no S2/S3/C3).
 * Usa driver/i2s.h legado para I2S0 + DAC interno en GPIO25/26.
 */
#include <Arduino.h>
#include <math.h>
#include <new>
#include <string.h>
#include "sdkconfig.h"
#include "driver/i2s.h"
#include "esp_err.h"
#include "fir_esp32.h"
#include "fft_ola_v2_stream.h"

#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Este firmware usa el DAC e I2S0 del ESP32 clasico; no usar en S2/S3/C3."
#endif

static constexpr uint32_t LINK_BAUD = 921600;
static constexpr int LINK_RX_PIN = 16;
static constexpr int LINK_TX_PIN = 17; // reservado; enlace actual es unidireccional
static constexpr uint32_t FS_HZ = 8192; // frecuencia efectiva de la senal procesada
// En DAC interno, el reloj I2S a 8192 Hz no es admitido por este core.
// Reproducimos 4 veces cada muestra a 32768 Hz, sin cambiar el DSP.
static constexpr size_t DAC_REPEAT = 4;
static constexpr uint32_t DAC_FS_HZ = FS_HZ * DAC_REPEAT;
static constexpr size_t BLOCK_SAMPLES = 1024;
static constexpr size_t HOP_SAMPLES = 512;
static constexpr size_t FIR_ALIGNMENT_DELAY = 448; // FIR ya aporta 64: total 512 muestras
static constexpr size_t HEADER_BYTES = 26;
static constexpr size_t PAYLOAD_BYTES = BLOCK_SAMPLES * sizeof(float);
static constexpr size_t CRC_BYTES = 4;
static constexpr size_t PACKET_DATA_BYTES = HEADER_BYTES + PAYLOAD_BYTES;
static constexpr uint32_t PACKET_TIMEOUT_MS = 180;

static HardwareSerial Link(2);
static uint8_t packetData[PACKET_DATA_BYTES];
static uint8_t headerRest[HEADER_BYTES - 4];
static uint8_t payload[PAYLOAD_BYTES];
static float inputBlock[BLOCK_SAMPLES];
static float firBlock[BLOCK_SAMPLES];
static float fftBlock[BLOCK_SAMPLES];
static float firDelay[FIR_ALIGNMENT_DELAY] = {0};
static size_t firDelayIndex = 0;
static uint16_t stereoDac[BLOCK_SAMPLES * DAC_REPEAT * 2];

static FIRLowPass129 fir;
// El estado FFT (~87 KiB) se reserva en el heap para evitar desbordar .dram0.bss.
static SpectralOLA1024V2Stream* spectral = nullptr;

static bool haveSequence = false;
static uint32_t lastSequence = 0;
static uint32_t packetsOk = 0;
static uint32_t packetsBadCrc = 0;
static uint32_t packetsBadFormat = 0;
static uint32_t sequenceGaps = 0;
static uint32_t dacErrors = 0;

static uint16_t readU16LE(const uint8_t* p) {
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}
static uint32_t readU32LE(const uint8_t* p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint32_t crc32Ieee(const uint8_t* data, size_t length) {
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = (uint32_t)(-(int32_t)(crc & 1U));
      crc = (crc >> 1U) ^ (0xEDB88320U & mask);
    }
  }
  return ~crc;
}

static bool readExact(uint8_t* destination, size_t count, uint32_t timeout_ms) {
  size_t received = 0;
  const uint32_t started = millis();
  while (received < count) {
    int available = Link.available();
    if (available > 0) {
      size_t take = (size_t)available;
      if (take > count - received) take = count - received;
      const size_t got = Link.readBytes(destination + received, take);
      received += got;
    } else {
      if ((uint32_t)(millis() - started) >= timeout_ms) return false;
      delay(1);
    }
  }
  return true;
}

static bool seekPacketMagic() {
  uint8_t window[4] = {0, 0, 0, 0};
  size_t used = 0;
  uint32_t lastStatus = millis();
  while (true) {
    if (Link.available() <= 0) {
      // Cedemos tiempo al planificador para evitar una espera activa indefinida.
      delay(1);
      if ((uint32_t)(millis() - lastStatus) >= 5000U) {
        Serial.println("Nodo 2/3 activo, esperando N1B2 por GPIO16...");
        lastStatus = millis();
      }
      continue;
    }
    const int value = Link.read();
    if (value < 0) continue;
    if (used < 4) {
      window[used++] = (uint8_t)value;
    } else {
      window[0] = window[1]; window[1] = window[2];
      window[2] = window[3]; window[3] = (uint8_t)value;
    }
    if (used == 4 && memcmp(window, "N1B2", 4) == 0) return true;
  }
}

static bool receiveN1B2(uint32_t* sequence, uint8_t* flags) {
  if (!seekPacketMagic()) return false;
  if (!readExact(headerRest, sizeof(headerRest), PACKET_TIMEOUT_MS)) {
    ++packetsBadFormat;
    Serial.println("ERROR: timeout leyendo cabecera N1B2");
    return false;
  }
  if (!readExact(payload, sizeof(payload), PACKET_TIMEOUT_MS)) {
    ++packetsBadFormat;
    Serial.println("ERROR: timeout leyendo payload N1B2");
    return false;
  }
  uint8_t crcBytes[4];
  if (!readExact(crcBytes, sizeof(crcBytes), PACKET_TIMEOUT_MS)) {
    ++packetsBadFormat;
    Serial.println("ERROR: timeout leyendo CRC N1B2");
    return false;
  }

  memcpy(packetData, "N1B2", 4);
  memcpy(packetData + 4, headerRest, sizeof(headerRest));
  memcpy(packetData + HEADER_BYTES, payload, sizeof(payload));
  const uint32_t receivedCrc = readU32LE(crcBytes);
  const uint32_t calculatedCrc = crc32Ieee(packetData, sizeof(packetData));
  if (receivedCrc != calculatedCrc) {
    ++packetsBadCrc;
    Serial.printf("ERROR CRC seq=%lu recibido=%08lX calculado=%08lX\n",
                  (unsigned long)readU32LE(headerRest + 2),
                  (unsigned long)receivedCrc, (unsigned long)calculatedCrc);
    return false;
  }

  const uint8_t version = headerRest[0];
  *flags = headerRest[1];
  *sequence = readU32LE(headerRest + 2);
  const uint32_t fsOutput = readU32LE(headerRest + 10);
  const uint16_t rawSamples = readU16LE(headerRest + 14);
  const uint16_t outputSamples = readU16LE(headerRest + 16);
  if (version != 1 || fsOutput != FS_HZ || rawSamples != 3072 ||
      outputSamples != BLOCK_SAMPLES) {
    ++packetsBadFormat;
    Serial.printf("ERROR formato N1B2: v=%u fs=%lu raw=%u out=%u\n",
                  version, (unsigned long)fsOutput, rawSamples, outputSamples);
    return false;
  }

  // ESP32 clasico usa little-endian; el payload son float32 little-endian.
  memcpy(inputBlock, payload, sizeof(inputBlock));
  for (size_t i = 0; i < BLOCK_SAMPLES; ++i) {
    if (!isfinite(inputBlock[i])) {
      ++packetsBadFormat;
      Serial.println("ERROR: muestra no finita en N1B2");
      return false;
    }
  }
  return true;
}

static bool initDacI2s() {
  i2s_config_t config = {};
  config.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN);
  config.sample_rate = DAC_FS_HZ;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_MSB;
  config.intr_alloc_flags = 0;
  config.dma_buf_count = 8;
  config.dma_buf_len = 256;
  config.use_apll = false;
  config.tx_desc_auto_clear = true;
  config.fixed_mclk = 0;

  esp_err_t err = i2s_driver_install(I2S_NUM_0, &config, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_driver_install: %s\n", esp_err_to_name(err));
    return false;
  }
  err = i2s_set_pin(I2S_NUM_0, nullptr); // DAC interno GPIO25 y GPIO26
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_set_pin: %s\n", esp_err_to_name(err));
    return false;
  }
  err = i2s_set_dac_mode(I2S_DAC_CHANNEL_BOTH_EN);
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_set_dac_mode: %s\n", esp_err_to_name(err));
    return false;
  }
  const float actualRate = i2s_get_clk(I2S_NUM_0);
  Serial.printf("DAC I2S: solicitado=%lu Hz, reloj reportado=%.1f Hz\n",
                (unsigned long)DAC_FS_HZ, (double)actualRate);
  if (!isfinite(actualRate) ||
      actualRate < (float)DAC_FS_HZ * 0.98f ||
      actualRate > (float)DAC_FS_HZ * 1.02f) {
    Serial.println("ERROR: reloj I2S/DAC no valido; no se reproducira audio.");
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }
  err = i2s_zero_dma_buffer(I2S_NUM_0);
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_zero_dma_buffer: %s\n", esp_err_to_name(err));
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }
  return true;
}

static uint16_t toDacWord(float sample) {
  // Señal centrada en 128, amplitud 110/127 para dejar margen de recorte.
  float value = 128.0f + 110.0f * sample;
  if (value < 0.0f) value = 0.0f;
  if (value > 255.0f) value = 255.0f;
  const uint16_t code = (uint16_t)lrintf(value);
  return (uint16_t)(code << 8); // DAC I2S toma los 8 bits mas significativos.
}

static bool processAndOutput(uint8_t flags) {
  // Si el numero de secuencia saltó, se reinicia el estado temporal para no
  // filtrar usando muestras separadas por una discontinuidad desconocida.
  // El contador de secuencia se verifica en loop() antes de esta funcion.
  const uint32_t processingStart = micros();

  // Nodo 2: FIR129 por muestra y retardo extra 448 para igualar 512 muestras
  // (64 del FIR + 448 de alineacion) con la latencia del Nodo 3.
  for (size_t i = 0; i < BLOCK_SAMPLES; ++i) {
    const float filtered = fir.process(inputBlock[i]);
    firBlock[i] = firDelay[firDelayIndex];
    firDelay[firDelayIndex] = filtered;
    firDelayIndex = (firDelayIndex + 1) % FIR_ALIGNMENT_DELAY;
  }

  // Nodo 3: dos frames por bloque de entrada, cada uno consume 512 muestras.
  // La primera mitad del primer bloque no tiene salida hasta tener dos frames.
  SpectralOLA1024V2Stream::Stats statsA = {};
  SpectralOLA1024V2Stream::Stats statsB = {};
  const bool firstReady = spectral->pushHop(inputBlock, fftBlock, &statsA);
  if (!firstReady) memset(fftBlock, 0, HOP_SAMPLES * sizeof(float));
  const bool secondReady = spectral->pushHop(inputBlock + HOP_SAMPLES,
                                             fftBlock + HOP_SAMPLES, &statsB);
  if (!secondReady) {
    Serial.println("ERROR: Nodo3 no produjo el segundo hop esperado");
    memset(fftBlock + HOP_SAMPLES, 0, HOP_SAMPLES * sizeof(float));
  }

  // 8192 Hz DSP -> 32768 Hz DAC por retencion de orden cero (4x).
  // Repetir el PAR estereo completo evita intercambiar canales.
  // LEFT -> DAC2 GPIO26 (FFT); RIGHT -> DAC1 GPIO25 (FIR).
  for (size_t i = 0; i < BLOCK_SAMPLES; ++i) {
    const uint16_t fftWord = toDacWord(fftBlock[i]);
    const uint16_t firWord = toDacWord(firBlock[i]);
    for (size_t rep = 0; rep < DAC_REPEAT; ++rep) {
      const size_t index = (i * DAC_REPEAT + rep) * 2;
      stereoDac[index] = fftWord;
      stereoDac[index + 1] = firWord;
    }
  }

  const uint32_t processingUs = micros() - processingStart;
  size_t bytesWritten = 0;
  const uint32_t i2sStart = micros();
  const esp_err_t err = i2s_write(I2S_NUM_0, stereoDac, sizeof(stereoDac),
                                  &bytesWritten, portMAX_DELAY);
  const uint32_t i2sWriteUs = micros() - i2sStart;
  if (err != ESP_OK || bytesWritten != sizeof(stereoDac)) {
    ++dacErrors;
    Serial.printf("ERROR I2S write: %s bytes=%u/%u\n",
                  esp_err_to_name(err), (unsigned)bytesWritten,
                  (unsigned)sizeof(stereoDac));
    return false;
  }

  ++packetsOk;
  if ((packetsOk % 8U) == 0U || flags != 0) {
    Serial.printf("Bloques=%lu | DSP+DAC pack=%lu us | I2S write=%lu us | FFT frames=%lu | flags_N1=%02X | CRC errores=%lu | gaps=%lu\n",
                  (unsigned long)packetsOk,
                  (unsigned long)processingUs,
                  (unsigned long)i2sWriteUs,
                  (unsigned long)statsB.frames_processed,
                  flags, (unsigned long)packetsBadCrc,
                  (unsigned long)sequenceGaps);
  }
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("NODE2_FIR + NODE3_FFT_V2_STREAM");
  Serial.printf("Entrada UART2 RX GPIO%d @ %lu baudios\n", LINK_RX_PIN,
                (unsigned long)LINK_BAUD);
  Serial.println("Nodo2 FIR129 -> DAC GPIO25; Nodo3 FFT v2 -> DAC GPIO26");

  Link.setRxBufferSize(8192);
  Link.begin(LINK_BAUD, SERIAL_8N1, LINK_RX_PIN, LINK_TX_PIN);
  Link.setTimeout(30);

  if (!initDacI2s()) {
    Serial.println("FATAL: no se pudo iniciar I2S/DAC interno.");
    while (true) delay(1000);
  }

  // Primero se reservan UART e I2S; despues se crea el historial FFT en heap.
  // No cambia los tamanos FFT, los 8 frames de historial ni el algoritmo.
  spectral = new (std::nothrow) SpectralOLA1024V2Stream();
  if (spectral == nullptr) {
    Serial.printf("FATAL: sin memoria para FFT (%u bytes). Heap libre: %u bytes\n",
                  (unsigned)sizeof(SpectralOLA1024V2Stream),
                  (unsigned)ESP.getFreeHeap());
    while (true) delay(1000);
  }
  Serial.printf("FFT reservada: %u bytes | Heap libre: %u bytes\n",
                (unsigned)sizeof(SpectralOLA1024V2Stream),
                (unsigned)ESP.getFreeHeap());
  Serial.printf("DSP a %lu Hz; I2S/DAC a %lu Hz (%u repeticiones/muestra). Esperando N1B2...\n",
                (unsigned long)FS_HZ, (unsigned long)DAC_FS_HZ,
                (unsigned)DAC_REPEAT);
}

void loop() {
  uint32_t sequence = 0;
  uint8_t flags = 0;
  if (!receiveN1B2(&sequence, &flags)) return;

  if (haveSequence) {
    const uint32_t expected = lastSequence + 1U;
    if (sequence != expected) {
      ++sequenceGaps;
      Serial.printf("SECUENCIA perdida: esperada=%lu recibida=%lu; reseteando filtros\n",
                    (unsigned long)expected, (unsigned long)sequence);
      fir.reset();
      spectral->reset();
      memset(firDelay, 0, sizeof(firDelay));
      firDelayIndex = 0;
    }
  }
  lastSequence = sequence;
  haveSequence = true;
  processAndOutput(flags);
}
