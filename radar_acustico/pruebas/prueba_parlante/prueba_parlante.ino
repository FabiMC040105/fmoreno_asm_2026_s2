const int DAC_PIN = 25;

const uint8_t seno[32] = {
  128,153,177,199,218,234,245,253,
  255,253,245,234,218,199,177,153,
  128,103,79,57,38,22,11,3,
  0,3,11,22,38,57,79,103
};

void setup() {}

void loop() {
  for (int i = 0; i < 32; i++) {
    dacWrite(DAC_PIN, seno[i]);
    delayMicroseconds(31);
  }
}