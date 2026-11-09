/*
 * Nodo 1 - Adquisicion ADC continua + DMA + antialias + decimacion 3:1.
 * Objetivo nominal: 24576 Hz ADC -> 8192 Hz de salida.
 * Placa: ESP32 clasico (por ejemplo ESP32 Dev Module / ESP-32D).
 * Entrada: GPIO34 = ADC1_CHANNEL_6.
 * Salida hacia Nodo 2/3: UART2 TX GPIO17, 921600 baudios, float32 little-endian.
 *
 * IMPORTANTE:
 * - Requiere Arduino-ESP32 3.x / ESP-IDF 5.x con esp_adc/adc_continuous.h.
 * - La frecuencia configurada en ADC no sustituye una calibracion real del reloj.
 * - La salida anuncia 8192 Hz NOMINALES hasta verificar la frecuencia con señal conocida.
 * - Nodo1 envia bloques N1B2 de 1024 muestras float32 despues de FIR antialias y DC.
 */

#include <Arduino.h>
#include <math.h>
#include <string.h>
#include "sdkconfig.h"
#include "soc/soc_caps.h"
#include "esp_adc/adc_continuous.h"
#include "hal/adc_types.h"
#include "esp_err.h"
#include "acondicionamiento_nodo1.h"
#include "fft_diagnostico_n1.h"
#include "estadisticas_tiempo.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Este firmware esta escrito para ESP32 clasico; no usar en ESP32-S2/S3/C3."
#endif

// ---------------- Configuracion de hardware y muestreo ----------------
static constexpr int ADC_GPIO = 34;
static constexpr adc_channel_t ADC_CHANNEL = ADC_CHANNEL_6;
static constexpr uint32_t ADC_FS_CONFIGURED_HZ = 24576;
static constexpr uint32_t OUTPUT_FS_NOMINAL_HZ = 8192;

static constexpr uint32_t ADC_RAW_SAMPLES_PER_BLOCK = 3072;
static constexpr uint32_t OUTPUT_SAMPLES_PER_BLOCK = 1024;
static constexpr uint32_t ADC_READ_BYTES = 256;     // 128 resultados de 2 bytes en ESP32 clasico.
static constexpr uint32_t ADC_POOL_BYTES = 16384;
static constexpr uint32_t UART_BAUD = 921600;
static constexpr int UART2_RX_PIN = 16;
static constexpr int UART2_TX_PIN = 17;
// Validacion opcional: estos pines NO se conectan salvo medicion con analizador.
static constexpr bool DIAG_GPIO_HABILITADOS = false;
static constexpr int DIAG_N1_BLOQUE_GPIO = 32; // pulso: fin de lectura DMA del bloque
static constexpr int DIAG_N1_UART_GPIO = 33;   // alto durante Serial2.write (solo API)
static constexpr bool DIAG_FFT_HABILITADA = true;
static constexpr uint32_t DIAG_FFT_CADA_BLOQUES = 8;
static constexpr uint32_t DIAG_TIEMPOS_CADA_BLOQUES = 32;

// Header N1B2: magic[4], version[1], flags[1], seq[4], fs_adc[4],
// fs_output[4], n_raw[2], n_output[2], capture_us[4] = 26 bytes.
static constexpr size_t PACKET_HEADER_BYTES = 26;
static constexpr size_t PACKET_PAYLOAD_BYTES = OUTPUT_SAMPLES_PER_BLOCK * sizeof(float);
static constexpr size_t PACKET_CRC_BYTES = 4;
static constexpr size_t PACKET_TOTAL_BYTES = PACKET_HEADER_BYTES + PACKET_PAYLOAD_BYTES + PACKET_CRC_BYTES;

static adc_continuous_handle_t adc_handle = nullptr;
static adc_digi_pattern_config_t adc_pattern = {};
static Nodo1Decimator3 decimator;
static uint16_t raw_block[ADC_RAW_SAMPLES_PER_BLOCK];
static float output_block[OUTPUT_SAMPLES_PER_BLOCK];
static uint8_t dma_buffer[ADC_READ_BYTES];
static uint8_t packet_buffer[PACKET_TOTAL_BYTES];
static uint32_t sequence_number = 0;
static uint32_t adc_pool_overflows = 0;
static uint32_t invalid_adc_records = 0;
static uint32_t adc_clipped_records = 0;
// Diagnostico: cadencia entre bloques transmitidos (incluye procesamiento y UART).
static uint32_t last_successful_tx_us = 0;
// Estadisticas internas: NO reemplazan mediciones externas del osciloscopio.
static EstadisticasTiempo periodoAdquisicion;
static EstadisticasTiempo duracionLecturaADC;
static EstadisticasTiempo duracionApiUART;
static uint32_t ultimaAdquisicionUs = 0;
static uint32_t ultimaApiUARTUs = 0;
static uint32_t bloquesAdquiridos = 0;
static uint32_t capturasFallidas = 0; // intentos fallidos, NO numero exacto de muestras perdidas

// Buzon de una sola copia. La FFT corre en tarea secundaria de baja prioridad.
// No espera a que finalice: si esta ocupada, se omite solo el diagnostico.
static FFTDiagnosticaN1 fftDiagnostica;
static float copiaParaFFT[FFTDiagnosticaN1::N];
static TaskHandle_t tareaFFT = nullptr;
static volatile uint32_t estadoFFT = 0; // 0 libre, 1 copiando, 2 lista/en ejecucion
static uint32_t secuenciaFFT = 0;
static uint32_t diagnosticosOmitidos = 0;

static void tareaDiagnosticoFFT(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (__atomic_load_n(&estadoFFT, __ATOMIC_ACQUIRE) != 2U) continue;
    ResultadoFFTDiagnostica resultado = {};
    const uint32_t sec = secuenciaFFT;
    const uint32_t inicio = micros();
    fftDiagnostica.analizar(copiaParaFFT, &resultado);
    const uint32_t duracionUs = micros() - inicio;
    __atomic_store_n(&estadoFFT, 0U, __ATOMIC_RELEASE);
    // USB de esta placa, NUNCA UART2. Se registra memoria reservada y heap libre.
    Serial.printf(
        "FFT1,seq=%lu,fft_us=%lu,ram_est=%u,heap=%u,min_heap=%u,"
        "f1=%.0f:%.4f,f2=%.0f:%.4f,f3=%.0f:%.4f,f4=%.0f:%.4f,f5=%.0f:%.4f,"
        "E_0_500=%.6g,E_500_1500=%.6g,E_1500_3000=%.6g,E_3000_4096=%.6g,omitidas=%lu\n",
        (unsigned long)sec, (unsigned long)duracionUs,
        (unsigned)(sizeof(fftDiagnostica) + sizeof(copiaParaFFT) + 8192U),
        (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap(),
        (double)resultado.frecuenciaHz[0], (double)resultado.amplitud[0],
        (double)resultado.frecuenciaHz[1], (double)resultado.amplitud[1],
        (double)resultado.frecuenciaHz[2], (double)resultado.amplitud[2],
        (double)resultado.frecuenciaHz[3], (double)resultado.amplitud[3],
        (double)resultado.frecuenciaHz[4], (double)resultado.amplitud[4],
        (double)resultado.energiaBandas[0], (double)resultado.energiaBandas[1],
        (double)resultado.energiaBandas[2], (double)resultado.energiaBandas[3],
        (unsigned long)diagnosticosOmitidos);
  }
}

// ---------------- Funciones auxiliares de protocolo ----------------
static void putU16LE(uint8_t *dst, uint16_t value) {
  dst[0] = static_cast<uint8_t>(value & 0xFFU);
  dst[1] = static_cast<uint8_t>((value >> 8) & 0xFFU);
}

static void putU32LE(uint8_t *dst, uint32_t value) {
  dst[0] = static_cast<uint8_t>(value & 0xFFU);
  dst[1] = static_cast<uint8_t>((value >> 8) & 0xFFU);
  dst[2] = static_cast<uint8_t>((value >> 16) & 0xFFU);
  dst[3] = static_cast<uint8_t>((value >> 24) & 0xFFU);
}

static uint32_t crc32(const uint8_t *data, size_t length) {
  uint32_t crc = 0xFFFFFFFFU;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = static_cast<uint32_t>(-(static_cast<int32_t>(crc & 1U)));
      crc = (crc >> 1U) ^ (0xEDB88320U & mask);
    }
  }
  return ~crc;
}

static bool sendOutputPacket(const float *samples, uint32_t capture_us, uint8_t flags) {
  if (samples == nullptr) return false;

  uint8_t *p = packet_buffer;
  memcpy(p, "N1B2", 4); p += 4;
  *p++ = 1;                         // version del protocolo
  *p++ = flags;                     // bit0: ADC raw tuvo muestras en limite
  putU32LE(p, sequence_number++); p += 4;
  putU32LE(p, ADC_FS_CONFIGURED_HZ); p += 4;
  putU32LE(p, OUTPUT_FS_NOMINAL_HZ); p += 4;
  putU16LE(p, static_cast<uint16_t>(ADC_RAW_SAMPLES_PER_BLOCK)); p += 2;
  putU16LE(p, static_cast<uint16_t>(OUTPUT_SAMPLES_PER_BLOCK)); p += 2;
  putU32LE(p, capture_us); p += 4;

  // ESP32 clasico es little-endian; payload float32 compatible con UART receptor.
  memcpy(p, samples, PACKET_PAYLOAD_BYTES);
  p += PACKET_PAYLOAD_BYTES;

  const uint32_t crc = crc32(packet_buffer, PACKET_HEADER_BYTES + PACKET_PAYLOAD_BYTES);
  putU32LE(p, crc);

  if (DIAG_GPIO_HABILITADOS) digitalWrite(DIAG_N1_UART_GPIO, HIGH);
  const uint32_t inicioUART = micros();
  const size_t written = Serial2.write(packet_buffer, PACKET_TOTAL_BYTES);
  ultimaApiUARTUs = micros() - inicioUART;
  if (DIAG_GPIO_HABILITADOS) digitalWrite(DIAG_N1_UART_GPIO, LOW);
  duracionApiUART.agregar(ultimaApiUARTUs);
  // NO es tiempo real de bits sobre el cable: Serial2.write puede encolar bytes.
  return written == PACKET_TOTAL_BYTES;
}

// ---------------- Configuracion e inicio permanente del ADC ----------------
static bool initContinuousAdc() {
  adc_continuous_handle_cfg_t handle_cfg = {};
  handle_cfg.max_store_buf_size = ADC_POOL_BYTES;
  handle_cfg.conv_frame_size = ADC_READ_BYTES;

  esp_err_t err = adc_continuous_new_handle(&handle_cfg, &adc_handle);
  if (err != ESP_OK) {
    Serial.printf("ERROR adc_continuous_new_handle: %s (0x%08X)\n",
                  esp_err_to_name(err), static_cast<unsigned int>(err));
    return false;
  }

  adc_pattern = {};
  adc_pattern.atten = ADC_ATTEN_DB_11;
  adc_pattern.channel = ADC_CHANNEL;
  adc_pattern.unit = ADC_UNIT_1;
  adc_pattern.bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;

  adc_continuous_config_t adc_cfg = {};
  adc_cfg.sample_freq_hz = ADC_FS_CONFIGURED_HZ;
  adc_cfg.conv_mode = ADC_CONV_SINGLE_UNIT_1;
  adc_cfg.format = ADC_DIGI_OUTPUT_FORMAT_TYPE1;
  adc_cfg.pattern_num = 1;
  adc_cfg.adc_pattern = &adc_pattern;

  err = adc_continuous_config(adc_handle, &adc_cfg);
  if (err != ESP_OK) {
    Serial.printf("ERROR adc_continuous_config: %s (0x%08X)\n",
                  esp_err_to_name(err), static_cast<unsigned int>(err));
    adc_continuous_deinit(adc_handle);
    adc_handle = nullptr;
    return false;
  }

  err = adc_continuous_start(adc_handle);
  if (err != ESP_OK) {
    Serial.printf("ERROR adc_continuous_start: %s (0x%08X)\n",
                  esp_err_to_name(err), static_cast<unsigned int>(err));
    adc_continuous_deinit(adc_handle);
    adc_handle = nullptr;
    return false;
  }

  return true;
}

static bool restartContinuousAdcAfterOverflow() {
  if (adc_handle == nullptr) return false;
  adc_continuous_stop(adc_handle);
  adc_continuous_flush_pool(adc_handle);
  decimator.reset();
  esp_err_t err = adc_continuous_start(adc_handle);
  if (err != ESP_OK) {
    Serial.printf("ERROR reiniciando ADC: %s (0x%08X)\n",
                  esp_err_to_name(err), static_cast<unsigned int>(err));
    return false;
  }
  return true;
}

// ---------------- Recoleccion exacta de 3072 conversiones DMA ----------------
static bool acquireRawBlock(uint32_t *elapsed_us, uint8_t *frame_flags) {
  if (elapsed_us == nullptr || frame_flags == nullptr || adc_handle == nullptr) return false;
  uint32_t filled = 0;
  const uint32_t start_us = micros();
  *frame_flags = 0;
  adc_clipped_records = 0;

  while (filled < ADC_RAW_SAMPLES_PER_BLOCK) {
    uint32_t bytes_read = 0;
    esp_err_t err = adc_continuous_read(
        adc_handle, dma_buffer, sizeof(dma_buffer), &bytes_read, 1000);

    if (err == ESP_ERR_TIMEOUT) continue;
    if (err == ESP_ERR_INVALID_STATE) {
      ++adc_pool_overflows;
      Serial.printf("ADC_POOL_OVERFLOW count=%lu; se descarta bloque parcial\n",
                    static_cast<unsigned long>(adc_pool_overflows));
      restartContinuousAdcAfterOverflow();
      return false;
    }
    if (err != ESP_OK) {
      Serial.printf("ERROR adc_continuous_read: %s (0x%08X)\n",
                    esp_err_to_name(err), static_cast<unsigned int>(err));
      return false;
    }

    if ((bytes_read % SOC_ADC_DIGI_RESULT_BYTES) != 0) {
      Serial.println("ERROR: bytes DMA no alineados con SOC_ADC_DIGI_RESULT_BYTES");
      return false;
    }

    for (uint32_t offset = 0; offset < bytes_read; offset += SOC_ADC_DIGI_RESULT_BYTES) {
      if (filled >= ADC_RAW_SAMPLES_PER_BLOCK) break;
      const adc_digi_output_data_t *sample =
          reinterpret_cast<const adc_digi_output_data_t *>(&dma_buffer[offset]);
      const uint16_t channel = sample->type1.channel;
      const uint16_t value = sample->type1.data;

      if (channel != ADC_CHANNEL) {
        ++invalid_adc_records;
        Serial.printf("ADC_CHANNEL_INVALID esperado=%u recibido=%u; reiniciando captura\n",
                      static_cast<unsigned int>(ADC_CHANNEL),
                      static_cast<unsigned int>(channel));
        restartContinuousAdcAfterOverflow();
        return false;
      }
      if (value <= 2U || value >= 4093U) {
        ++adc_clipped_records;
        *frame_flags |= 0x01U;
      }
      raw_block[filled++] = value;
    }
  }

  *elapsed_us = micros() - start_us;
  return true;
}

// ---------------- Arduino ----------------
void setup() {
  Serial.begin(115200);  // Diagnostico por USB; no transporta paquetes binarios.
  Serial2.begin(UART_BAUD, SERIAL_8N1, UART2_RX_PIN, UART2_TX_PIN);
  if (DIAG_GPIO_HABILITADOS) {
    pinMode(DIAG_N1_BLOQUE_GPIO, OUTPUT);
    pinMode(DIAG_N1_UART_GPIO, OUTPUT);
    digitalWrite(DIAG_N1_BLOQUE_GPIO, LOW);
    digitalWrite(DIAG_N1_UART_GPIO, LOW);
  }
  if (DIAG_FFT_HABILITADA) {
    fftDiagnostica.preparar(); // ventana precalculada antes de iniciar ADC
    const BaseType_t ok = xTaskCreatePinnedToCore(
        tareaDiagnosticoFFT, "FFT_diag_N1", 8192, nullptr, 1, &tareaFFT, 0);
    if (ok != pdPASS) {
      tareaFFT = nullptr;
      Serial.println("AVISO: FFT diagnostica deshabilitada: sin memoria para tarea");
    }
  }
  delay(500);

  Serial.println();
  Serial.println("NODE1_ADC_DMA_DECIMATOR3");
  Serial.printf("ADC GPIO%d / ADC1_CHANNEL_6 | fs configurada=%lu Hz\n",
                ADC_GPIO, static_cast<unsigned long>(ADC_FS_CONFIGURED_HZ));
  Serial.printf("Salida nominal=%lu Hz | bloque ADC=%lu | bloque salida=%lu\n",
                static_cast<unsigned long>(OUTPUT_FS_NOMINAL_HZ),
                static_cast<unsigned long>(ADC_RAW_SAMPLES_PER_BLOCK),
                static_cast<unsigned long>(OUTPUT_SAMPLES_PER_BLOCK));
  Serial.printf("UART2 TX GPIO%d a %lu baudios\n", UART2_TX_PIN,
                static_cast<unsigned long>(UART_BAUD));

  if (!initContinuousAdc()) {
    Serial.println("FATAL: no se pudo iniciar ADC continuo.");
    while (true) delay(1000);
  }
  Serial.println("ADC DMA iniciado continuamente.");
}

void loop() {
  uint32_t capture_us = 0;
  uint8_t flags = 0;
  if (!acquireRawBlock(&capture_us, &flags)) {
    ++capturasFallidas;
    delay(1); // ruta de error ya existente; no se agrega demora en ruta normal
    return;
  }
  const uint32_t finAdquisicionUs = micros();
  if (ultimaAdquisicionUs != 0) {
    periodoAdquisicion.agregar((uint32_t)(finAdquisicionUs - ultimaAdquisicionUs));
  }
  ultimaAdquisicionUs = finAdquisicionUs;
  duracionLecturaADC.agregar(capture_us);
  ++bloquesAdquiridos;
  if (DIAG_GPIO_HABILITADOS) {
    digitalWrite(DIAG_N1_BLOQUE_GPIO, HIGH);
    digitalWrite(DIAG_N1_BLOQUE_GPIO, LOW);
  }

  size_t output_count = 0;
  if (!decimator.process(raw_block, ADC_RAW_SAMPLES_PER_BLOCK,
                         output_block, OUTPUT_SAMPLES_PER_BLOCK, &output_count)) {
    Serial.println("ERROR: fallo del decimador FIR 3:1.");
    decimator.reset();
    return;
  }
  if (output_count != OUTPUT_SAMPLES_PER_BLOCK) {
    Serial.printf("ERROR: decimador produjo %u muestras, se esperaban %u.\n",
                  static_cast<unsigned int>(output_count), OUTPUT_SAMPLES_PER_BLOCK);
    decimator.reset();
    return;
  }

  Nodo1Decimator3::removeDcAndNormalize(output_block, output_count, 2048.0f);

  if (!sendOutputPacket(output_block, capture_us, flags)) {
    Serial.println("ERROR: UART2 no acepto el paquete completo.");
  } else {
    const uint32_t now_us = micros();
    const uint32_t period_us = last_successful_tx_us == 0 ? 0 :
                               (uint32_t)(now_us - last_successful_tx_us);
    last_successful_tx_us = now_us;
    // Evitar imprimir cada 125 ms: el USB puede introducir bloqueo temporal.
    if (bloquesAdquiridos % DIAG_TIEMPOS_CADA_BLOQUES == 0U) {
      // Tiempo por bloque nominal: 1024/8192 s = 125000 us.
      // Un promedio interno correcto no prueba el reloj fisico del ADC.
      Serial.printf("T1,adquiridos=%lu,periodo_media=%.1f,min=%lu,max=%lu,sd=%.1f,"
                    "lectura_adc_media=%.1f,uart_api_media=%.1f,uart_api_ultimo=%lu,"
                    "uart_nominal_cable_us=%.1f,overflow=%lu,fallos_captura=%lu,fft_omitidas=%lu\n",
                    (unsigned long)bloquesAdquiridos,
                    periodoAdquisicion.media,
                    (unsigned long)periodoAdquisicion.minSeguro(),
                    (unsigned long)periodoAdquisicion.maximo,
                    periodoAdquisicion.desviacion(), duracionLecturaADC.media,
                    duracionApiUART.media, (unsigned long)ultimaApiUARTUs,
                    (double)(10000000.0 * PACKET_TOTAL_BYTES / UART_BAUD),
                    (unsigned long)adc_pool_overflows, (unsigned long)capturasFallidas,
                    (unsigned long)diagnosticosOmitidos);
    }
    if (((sequence_number - 1) % 8U) == 0U) {
      const float fs_out_estimado = period_us ?
          (1000000.0f * OUTPUT_SAMPLES_PER_BLOCK / period_us) : 0.0f;
      Serial.printf("TX seq=%lu | ADC=%lu us | tx_period_us=%lu | fs_out_est=%.1f | raw_limite=%lu | flags=0x%02X | invalidos=%lu\n",
                    (unsigned long)(sequence_number - 1),
                    (unsigned long)capture_us,
                    (unsigned long)period_us,
                    (double)fs_out_estimado,
                    (unsigned long)adc_clipped_records, flags,
                    (unsigned long)invalid_adc_records);
    }
  }

  // Copiar despues de construir el paquete; nunca escribir sobre output_block.
  if (DIAG_FFT_HABILITADA && tareaFFT != nullptr &&
      (bloquesAdquiridos % DIAG_FFT_CADA_BLOQUES) == 0U) {
    uint32_t libre = 0U;
    if (__atomic_compare_exchange_n(&estadoFFT, &libre, 1U, false,
                                    __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) {
      memcpy(copiaParaFFT, output_block, sizeof(copiaParaFFT));
      secuenciaFFT = sequence_number - 1U;
      __atomic_store_n(&estadoFFT, 2U, __ATOMIC_RELEASE);
      xTaskNotifyGive(tareaFFT);
    } else {
      ++diagnosticosOmitidos; // sacrifica diagnostico, NO el audio
    }
  }
}
