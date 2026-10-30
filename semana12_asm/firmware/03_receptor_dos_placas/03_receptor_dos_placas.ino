#include <Arduino.h>

#if defined(CONFIG_IDF_TARGET_ESP32)
  constexpr uint8_t PIN_ADC = 34;
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  constexpr uint8_t PIN_ADC = 4;
#else
  #error "Se requiere ESP32 clasico o ESP32-S3"
#endif
constexpr uint32_t FS = 8192;
constexpr size_t N = 1024;
uint16_t datos[N];

void capturar(uint8_t modo) {
  uint32_t proximo = micros() + 3000;
  uint32_t t0 = proximo;
  uint32_t frac=0, tardias=0;
  for (size_t i=0; i<N; ++i) {
    while ((int32_t)(micros() - proximo) < 0) {}
    if ((int32_t)(micros()-proximo)>35) ++tardias;
    datos[i] = analogRead(PIN_ADC);
    proximo += 1000000UL / FS;
    frac += 1000000UL % FS;
    if (frac >= FS) { ++proximo; frac -= FS; }
  }
  uint32_t duracion = micros()-t0;
  Serial.printf("BEGIN,%u,%lu,%u\n",(unsigned)N,(unsigned long)FS,(unsigned)modo);
  for (size_t i=0; i<N; ++i) Serial.println(datos[i]);
  Serial.printf("END,%lu,%lu\n",(unsigned long)tardias,(unsigned long)duracion);
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_ADC, ADC_11db);
  delay(300);
  Serial.println("RECEPTOR listo. Enviar numero 1..5 para recibir bloque del emisor.");
}

void loop() {
  if (Serial.available()) {
    char c=(char)Serial.read();
    if (c >= '1' && c <= '5') capturar((uint8_t)(c-'0'));
  }
}
