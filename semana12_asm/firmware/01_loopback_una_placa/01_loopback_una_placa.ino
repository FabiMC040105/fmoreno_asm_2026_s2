#include <Arduino.h>
#include <math.h>

#if defined(CONFIG_IDF_TARGET_ESP32)
  constexpr uint8_t PIN_SALIDA = 25;  // DAC real
  constexpr uint8_t PIN_ADC = 34;     // ADC1
  #define USAR_DAC 1
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  constexpr uint8_t PIN_SALIDA = 17;  // PWM filtrado con RC
  constexpr uint8_t PIN_ADC = 4;      // ADC1
  #define USAR_DAC 0
#else
  #error "Este ejemplo admite ESP32 clasico o ESP32-S3. Verifique el modelo de placa."
#endif

constexpr uint32_t FS = 8192;
constexpr size_t N = 1024;
constexpr size_t PERIODO_LUT = 32;
constexpr float DOS_PI = 6.2831853071795864769f;
uint8_t tablas[6][PERIODO_LUT]; // indices 1..5
uint16_t lectura[N];

void configurarSalida() {
#if USAR_DAC
  dacWrite(PIN_SALIDA, 128);
#else
  // Arduino-ESP32 3.x; PWM de frecuencia alta, suavizado mediante filtro RC.
  if (!ledcAttach(PIN_SALIDA, 62500, 8)) {
    Serial.println("ERROR: no se pudo iniciar PWM");
    while (true) delay(500);
  }
  ledcWrite(PIN_SALIDA, 128);
#endif
}

void escribirSalida(uint8_t valor) {
#if USAR_DAC
  dacWrite(PIN_SALIDA, valor);
#else
  ledcWrite(PIN_SALIDA, valor);
#endif
}

void prepararTablas() {
  // 8192/256=32 muestras/ciclo. Todas las frecuencias elegidas son
  // multiplos de 256 Hz: 512=2x, 1024=4x, 1792=7x.
  for (size_t i = 0; i < PERIODO_LUT; ++i) {
    float f1 = sinf(DOS_PI * i / 32.0f);
    float f2 = sinf(DOS_PI * 2.0f * i / 32.0f);
    float f3 = sinf(DOS_PI * 4.0f * i / 32.0f);
    float f4 = sinf(DOS_PI * 7.0f * i / 32.0f);
    const float amplitudes[6] = {
      0, 70*f1, 70*f3,
      40*f1 + 24*f2 + 14*f3,
      40*f1 + 24*f2 + 14*f3 + 14*f4,
      70*f4
    };
    for (uint8_t modo=1; modo<=5; ++modo) {
      int dato = (int)lroundf(128.0f + amplitudes[modo]);
      tablas[modo][i] = (uint8_t)constrain(dato, 0, 255);
    }
  }
}

void capturar(uint8_t modo) {
  uint32_t siguiente = micros() + 3000; // margen para preparar el primer tick
  uint32_t t_inicio = siguiente;
  uint32_t fraccion = 0;
  uint32_t tardias = 0;
  for (size_t n=0; n<N; ++n) {
    // La comparacion con signo soporta el desbordamiento de micros().
    while ((int32_t)(micros() - siguiente) < 0) {}
    if ((int32_t)(micros() - siguiente) > 35) ++tardias;
    escribirSalida(tablas[modo][n & 31]);
    delayMicroseconds(25); // esperar algo de asentamiento del RC
    lectura[n] = analogRead(PIN_ADC);
    // Intervalos de 122/123 us alternados: media EXACTA 1e6/8192 us.
    siguiente += 1000000UL / FS;
    fraccion += 1000000UL % FS;
    if (fraccion >= FS) { ++siguiente; fraccion -= FS; }
  }
  uint32_t duracion_us = micros() - t_inicio;
  escribirSalida(128); // tension media al finalizar
  Serial.printf("BEGIN,%u,%lu,%u\n", (unsigned)N, (unsigned long)FS, (unsigned)modo);
  for (size_t n=0; n<N; ++n) Serial.println(lectura[n]);
  Serial.printf("END,%lu,%lu\n", (unsigned long)tardias, (unsigned long)duracion_us);
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_ADC, ADC_11db);
  configurarSalida();
  prepararTablas();
  delay(300);
  Serial.println("READY: enviar 1..5 seguido de Enter para capturar 1024 muestras");
}

void loop() {
  if (Serial.available()) {
    char c = (char)Serial.read();
    if (c >= '1' && c <= '5') capturar((uint8_t)(c-'0'));
  }
}
