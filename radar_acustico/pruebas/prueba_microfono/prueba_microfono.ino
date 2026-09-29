const int MIC_PIN = 34;

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
}

void loop() {
  int muestra = analogRead(MIC_PIN);
  Serial.println(muestra);
  delay(2);
}