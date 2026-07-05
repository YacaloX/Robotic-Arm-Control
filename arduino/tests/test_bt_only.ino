/**
 * Brazo Robótico N DOF — ESP32 DevKit v1
 * MODO TEST: Sin PWM para aislar conflicto LEDC vs Bluetooth
 */

#include <Arduino.h>
#include <BluetoothSerial.h>

#define BT_NAME "Brazo-Robotico"

BluetoothSerial SerialBT;

void processCommand(String input);
void processStream(Stream &stream, String &buffer);

void setup() {
  Serial.begin(115200);
  delay(500);

  SerialBT.begin(BT_NAME);
  SerialBT.register_callback([](esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
    if (event == ESP_SPP_SRV_OPEN_EVT) {
      Serial.println("Cliente Bluetooth conectado");
    } else if (event == ESP_SPP_CLOSE_EVT) {
      Serial.println("Cliente Bluetooth desconectado");
    }
  });

  Serial.println("Bluetooth SPP iniciado (modo test — sin PWM)");
  Serial.println("Brazo listo — modo test BT");
}

void loop() {
  static String serialBuffer = "";
  static String btBuffer = "";

  processStream(Serial, serialBuffer);

  if (SerialBT.hasClient()) {
    processStream(SerialBT, btBuffer);
  }
}

void processStream(Stream &stream, String &buffer) {
  while (stream.available()) {
    char c = (char)stream.read();
    if (c == '\n') {
      processCommand(buffer);
      buffer = "";
    } else if (c != '\r') {
      buffer += c;
    }
  }
}

void processCommand(String input) {
  if (input.length() == 0) return;

  if (input.equalsIgnoreCase("PING")) {
    if (SerialBT.hasClient()) {
      SerialBT.println("PONG");
    } else {
      Serial.println("PONG");
    }
    return;
  }

  String resp = "ECHO: " + input;
  if (SerialBT.hasClient()) {
    SerialBT.println(resp);
  } else {
    Serial.println(resp);
  }
}
