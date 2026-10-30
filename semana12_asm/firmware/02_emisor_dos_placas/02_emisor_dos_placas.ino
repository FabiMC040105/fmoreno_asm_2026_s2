#include <Arduino.h>
#include <math.h>

#if defined(CONFIG_IDF_TARGET_ESP32)
  constexpr uint8_t PIN_SALIDA = 25;
  #define USAR_DAC 1
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
  constexpr uint8_t PIN_SALIDA = 17;
  #define USAR_DAC 0
#else
  #error "Se requiere ESP32 clasico o ESP32-S3"
#endif

constexpr uint32_t FS = 8192;
constexpr float DOS_PI = 6.2831853071795864769f;
uint8_t ondas[6][32];
uint8_t modo = 1;
uint8_t indice = 0;
uint32_t proximo = 0, fraccion = 0;
uint32_t atrasos = 0;

void salida(uint8_t valor) {
#if USAR_DAC
  dacWrite(PIN_SALIDA, valor);
#else
  ledcWrite(PIN_SALIDA, valor);
#endif
}

void iniciarSalida() {
#if USAR_DAC
  dacWrite(PIN_SALIDA, 128);
#else
  if (!ledcAttach(PIN_SALIDA, 62500, 8)) {
    Serial.println("ERROR LEDC");
    while (true) delay(500);
  }
  ledcWrite(PIN_SALIDA, 128);
#endif
}

void prepararOndas() {
  for (int i = 0; i < 32; ++i) {
    float s1=sinf(DOS_PI*i/32.0f), s2=sinf(DOS_PI*2*i/32.0f);
    float s3=sinf(DOS_PI*4*i/32.0f), s4=sinf(DOS_PI*7*i/32.0f);
    float v[6] = {0, 70*s1, 70*s3, 40*s1+24*s2+14*s3,
                  40*s1+24*s2+14*s3+14*s4, 70*s4};
    for (uint8_t m=1; m<=5; ++m) {
      ondas[m][i] = (uint8_t)constrain((int)lroundf(128+v[m]),0,255);
    }
  }
}

void setup() {
  Serial.begin(115200);
  iniciarSalida();
  prepararOndas();
  proximo = micros();
  Serial.println("EMISOR listo. 1=256, 2=1024, 3=multitono, 4=multitono+1792, 5=1792, 0=pausa");
}

void loop() {
  uint32_t ahora = micros();
  if ((int32_t)(ahora - proximo) >= 0) {
    if ((int32_t)(ahora - proximo) > 35) ++atrasos;
    salida(modo == 0 ? 128 : ondas[modo][indice]);
    indice = (indice + 1) & 31;
    proximo += 1000000UL / FS;
    fraccion += 1000000UL % FS;
    if (fraccion >= FS) { ++proximo; fraccion -= FS; }
    // Si un mensaje serial atraso mucho el lazo, saltar al tiempo actual.
    if ((int32_t)(micros() - proximo) > 1000) proximo = micros() + 122;
  }
  // Nunca imprimir durante la emision continua: produciria jitter.
  if (Serial.available()) {
    char c = (char)Serial.read();
    if (c >= '0' && c <= '5') { modo = (uint8_t)(c - '0'); indice = 0; }
  }
}
