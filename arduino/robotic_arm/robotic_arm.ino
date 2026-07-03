#include <Arduino.h>
#include <BluetoothSerial.h>

#define MAX_SERVOS 6
#define BT_NAME "Brazo-Robotico"
#define MAX_LINE 128
#define CMD_TIMEOUT_MS 500
#define LEDC_FREQ 50
#define LEDC_BIT 10
#define SERVO_MIN_US 544
#define SERVO_MAX_US 2400
#define BT_WATCHDOG_MS 20000

struct ServoConfig {
  int pin;
  int channel;
  int currentAngle;
};

int numServos = 0;
ServoConfig servos[MAX_SERVOS];
int ledcFreq;

BluetoothSerial SerialBT;
volatile bool btConnected = false;
unsigned long lastBtActivity = 0;

int pulseToDuty(int us) {
  return (int)((unsigned long)us * (1 << LEDC_BIT) / 20000UL);
}

int cmdToDuty(int cmdAngle) {
  int physical = map(cmdAngle, -90, 90, 0, 180);
  int pulseUs = map(physical, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  return pulseToDuty(pulseUs);
}

void configureServos(int n, int pins[]) {
  for (int i = 0; i < numServos; i++) {
    ledcDetachPin(servos[i].pin);
  }

  delay(100);

  numServos = (n > MAX_SERVOS) ? MAX_SERVOS : (n < 0 ? 0 : n);

  for (int i = 0; i < numServos; i++) {
    servos[i].pin = pins[i];
    servos[i].channel = i;
    servos[i].currentAngle = 0;
    ledcSetup(i, LEDC_FREQ, LEDC_BIT);
    ledcAttachPin(pins[i], i);
    delay(150);
    ledcWrite(i, cmdToDuty(0));
    delay(150);
  }

  String msg = "CONFIG OK - " + String(numServos) + " servos en pines:";
  for (int i = 0; i < numServos; i++) {
    msg += " " + String(pins[i]);
  }
  Serial.println(msg);
  if (SerialBT.hasClient()) {
    SerialBT.println(msg);
  }
}

void homeAllServos() {
  for (int i = 0; i < numServos; i++) {
    servos[i].currentAngle = 0;
    ledcWrite(servos[i].channel, cmdToDuty(0));
    delay(200);
  }
  String msg = "HOME - todos los servos a 0 deg";
  Serial.println(msg);
  if (SerialBT.hasClient()) {
    SerialBT.println(msg);
  }
}

void respond(const String &msg, bool fromSerial) {
  if (fromSerial) {
    Serial.println(msg);
  } else if (SerialBT.hasClient()) {
    SerialBT.println(msg);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  ledcFreq = ledcSetup(0, LEDC_FREQ, LEDC_BIT);
  ledcDetachPin(0);

  SerialBT.begin(BT_NAME);
  SerialBT.register_callback([](esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
    if (event == ESP_SPP_SRV_OPEN_EVT) {
      btConnected = true;
      lastBtActivity = millis();
      Serial.println("Cliente Bluetooth conectado");
    } else if (event == ESP_SPP_CLOSE_EVT) {
      btConnected = false;
      Serial.println("Cliente Bluetooth desconectado");
      esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
    }
  });
  Serial.println("Bluetooth SPP iniciado - nombre: " + String(BT_NAME));

  int defaultPins[MAX_SERVOS] = {13, 12, 14, 27, 25, 26};
  configureServos(MAX_SERVOS, defaultPins);
  homeAllServos();

  Serial.println("Brazo listo - ESP32 DevKit v1 (Serial + Bluetooth)");
}

void loop() {
  static String serialBuffer = "";
  static String btBuffer = "";
  static unsigned long serialLastChar = 0;
  static unsigned long btLastChar = 0;

  processStream("Serial", Serial, serialBuffer, serialLastChar);

  if (btConnected) {
    if (SerialBT.hasClient()) {
      processStream("BT", SerialBT, btBuffer, btLastChar);
      if (btLastChar > 0) {
        lastBtActivity = btLastChar;
      }
      if (millis() - lastBtActivity > BT_WATCHDOG_MS) {
        Serial.println("BT watchdog: cliente inactivo");
        SerialBT.end();
        delay(100);
        SerialBT.begin(BT_NAME);
        btConnected = false;
        btBuffer = "";
        btLastChar = 0;
      }
    } else {
      btConnected = false;
      Serial.println("BT cliente perdido");
    }
  }
}

void processStream(const char *source, Stream &stream, String &buffer, unsigned long &lastCharTime) {
  while (stream.available()) {
    char c = (char)stream.read();
    lastCharTime = millis();
    if (c == '\n') {
      processCommand(buffer, source);
      buffer = "";
    } else if (c != '\r') {
      if (buffer.length() < MAX_LINE) {
        buffer += c;
      }
    }
  }
  if (buffer.length() > 0 && (millis() - lastCharTime) > CMD_TIMEOUT_MS) {
    Serial.print("Timeout - buffer descartado por ");
    Serial.print(source);
    Serial.print(": ");
    Serial.println(buffer);
    buffer = "";
  }
}

void processCommand(const String &input, const char *source) {
  if (input.length() == 0) return;

  bool fromSerial = (strcmp(source, "Serial") == 0);

  if (input.equalsIgnoreCase("PING")) {
    respond("PONG", fromSerial);
    return;
  }

  if (input.equalsIgnoreCase("CHECK")) {
    respond("CHECKED", fromSerial);
    return;
  }

  if (input.equalsIgnoreCase("STATUS")) {
    String resp = "STATUS OK " + String(numServos);
    for (int i = 0; i < numServos; i++) {
      resp += " " + String(servos[i].currentAngle);
    }
    respond(resp, fromSerial);
    return;
  }

  if (input.startsWith("CONFIG ")) {
    String rest = input.substring(7);
    rest.trim();
    int firstSpace = rest.indexOf(' ');
    int n = rest.substring(0, firstSpace).toInt();
    if (n < 1 || n > MAX_SERVOS) {
      respond("Error: CONFIG n invalido -> " + String(n), fromSerial);
      return;
    }
    int pins[MAX_SERVOS];
    String pinStr = rest.substring(firstSpace + 1);
    pinStr.trim();
    int count = 0;
    int startIdx = 0;
    while (true) {
      int sp = pinStr.indexOf(' ', startIdx);
      String token = (sp < 0) ? pinStr.substring(startIdx) : pinStr.substring(startIdx, sp);
      token.trim();
      if (token.length() > 0 && count < MAX_SERVOS) {
        pins[count++] = token.toInt();
      }
      if (sp < 0) break;
      startIdx = sp + 1;
    }
    if (count != n) {
      respond("Error: CONFIG esperaba " + String(n) + " pines, recibio " + String(count), fromSerial);
      return;
    }
    configureServos(n, pins);
    return;
  }

  int separator = input.indexOf(' ');
  if (separator < 0) {
    respond("Error: formato invalido -> " + input, fromSerial);
    return;
  }

  int servoId = input.substring(0, separator).toInt();
  int cmdAngle = input.substring(separator + 1).toInt();

  if (servoId < 0 || servoId >= numServos) {
    respond("Error: servo fuera de rango -> " + String(servoId), fromSerial);
    return;
  }

  cmdAngle = constrain(cmdAngle, -90, 90);
  servos[servoId].currentAngle = cmdAngle;
  ledcWrite(servos[servoId].channel, cmdToDuty(cmdAngle));

  respond("OK servo " + String(servoId) + " -> " + String(cmdAngle) + " deg", fromSerial);
}
