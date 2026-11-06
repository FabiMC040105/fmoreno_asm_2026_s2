#include <Arduino.h>
#include <string.h>
#include "fir_esp32.h"

// Prueba de equivalencia FIR en ESP32.
// Este firmware recibe bloques float32 desde el PC por USB serial,
// los procesa con FIRLowPass129 y devuelve la salida float32.
// No realiza todavía adquisición ADC ni salida DAC/PWM.

static const uint32_t SERIAL_BAUD = 921600;
static const size_t MAX_BLOCK = 1024;
static const uint32_t SERIAL_TIMEOUT_MS = 5000;

static_assert(sizeof(float) == 4, "Este protocolo requiere float32 de 4 bytes");

FIRLowPass129 fir;
float inputBuffer[MAX_BLOCK];
float outputBuffer[MAX_BLOCK];

bool readExact(uint8_t* destination, size_t length) {
    size_t received = Serial.readBytes(
        reinterpret_cast<char*>(destination), length
    );
    return received == length;
}

void sendError(uint8_t code) {
    const uint8_t header[4] = {'E', 'R', 'R', '1'};
    Serial.write(header, sizeof(header));
    Serial.write(&code, 1);
    Serial.flush();
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    Serial.setTimeout(SERIAL_TIMEOUT_MS);
    fir.reset();
    // No imprimir mensajes de texto: la comunicación utiliza tramas binarias.
}

void loop() {
    if (Serial.available() < 4) {
        return;
    }

    uint8_t command[4];
    if (!readExact(command, sizeof(command))) {
        sendError('H');
        return;
    }

    if (memcmp(command, "RST1", 4) == 0) {
        fir.reset();
        const uint8_t response[4] = {'A', 'C', 'K', '1'};
        Serial.write(response, sizeof(response));
        Serial.flush();
        return;
    }

    if (memcmp(command, "BLK1", 4) != 0) {
        sendError('C');
        return;
    }

    uint8_t countBytes[2];
    if (!readExact(countBytes, sizeof(countBytes))) {
        sendError('N');
        return;
    }

    const uint16_t count =
        static_cast<uint16_t>(countBytes[0]) |
        (static_cast<uint16_t>(countBytes[1]) << 8);

    if (count == 0 || count > MAX_BLOCK) {
        sendError('L');
        return;
    }

    const size_t dataBytes = static_cast<size_t>(count) * sizeof(float);
    if (!readExact(reinterpret_cast<uint8_t*>(inputBuffer), dataBytes)) {
        sendError('D');
        return;
    }

    // Se mide únicamente el cálculo FIR; no incluye serial ni adquisición ADC.
    const uint32_t startUs = micros();
    for (uint16_t i = 0; i < count; ++i) {
        outputBuffer[i] = fir.process(inputBuffer[i]);
    }
    const uint32_t processingUs = micros() - startUs;

    const uint8_t response[4] = {'O', 'U', 'T', '1'};
    Serial.write(response, sizeof(response));
    Serial.write(reinterpret_cast<const uint8_t*>(&count), sizeof(count));
    Serial.write(reinterpret_cast<const uint8_t*>(outputBuffer), dataBytes);
    Serial.write(reinterpret_cast<const uint8_t*>(&processingUs), sizeof(processingUs));
    Serial.flush();
}
