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
#define GRIPPER_SERVO_ID 5
#define GRIPPER_MIN_ANGLE -20
#define GRIPPER_MAX_ANGLE 45

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

int clampAngle(int angle, int servoId) {
  angle = constrain(angle, -90, 90);
  if (servoId == GRIPPER_SERVO_ID) {
    angle = constrain(angle, GRIPPER_MIN_ANGLE, GRIPPER_MAX_ANGLE);
  }
  return angle;
}

void setServoImmediate(int servoId, int angle) {
  angle = clampAngle(angle, servoId);
  servos[servoId].currentAngle = angle;
  ledcWrite(servos[servoId].channel, cmdToDuty(angle));
}

void rampAllServos(int targets[], int stepSize, int delayMs, bool fromSerial) {
  if (numServos <= 0) {
    respond("Error: no hay servos configurados", fromSerial);
    return;
  }

  int startAngles[MAX_SERVOS];
  int diffs[MAX_SERVOS];
  int stepsNeeded[MAX_SERVOS];
  int maxSteps = 0;

  for (int i = 0; i < numServos; i++) {
    startAngles[i] = servos[i].currentAngle;
    int t = clampAngle(targets[i], i);
    diffs[i] = t - startAngles[i];
    stepsNeeded[i] = (abs(diffs[i]) + stepSize - 1) / stepSize;
    if (stepsNeeded[i] < 1) stepsNeeded[i] = 1;
    if (stepsNeeded[i] > maxSteps) maxSteps = stepsNeeded[i];
  }

  if (maxSteps <= 1) {
    for (int i = 0; i < numServos; i++) {
      setServoImmediate(i, targets[i]);
    }
    respond("RAMP_OK", fromSerial);
    return;
  }

  for (int step = 1; step <= maxSteps; step++) {
    for (int i = 0; i < numServos; i++) {
      int angle;
      if (maxSteps == 1) {
        angle = targets[i];
      } else {
        angle = startAngles[i] + (diffs[i] * step + maxSteps / 2) / maxSteps;
      }
      setServoImmediate(i, angle);
    }

    if (step < maxSteps) {
      unsigned long stepStart = millis();
      while (millis() - stepStart < (unsigned long)delayMs) {
        if (Serial.available() || (SerialBT.hasClient() && SerialBT.available())) {
          respond("RAMP_CANCELLED", fromSerial);
          return;
        }
        delay(2);
      }
    }
  }

  respond("RAMP_OK", fromSerial);
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

  if (input.startsWith("RAMPALL ")) {
    String rest = input.substring(8);
    rest.trim();
    int angles[MAX_SERVOS];
    int count = 0;
    int startIdx = 0;
    while (count < MAX_SERVOS + 2) {
      int sp = rest.indexOf(' ', startIdx);
      String token = (sp < 0) ? rest.substring(startIdx) : rest.substring(startIdx, sp);
      token.trim();
      if (token.length() > 0) {
        if (count < numServos) {
          angles[count] = token.toInt();
        } else if (count == numServos) {
          int stepSize = token.toInt();
          if (stepSize < 1) stepSize = 5;
          int delayMs = 100;
          if (sp >= 0) {
            int sp2 = rest.indexOf(' ', sp + 1);
            String delayToken = (sp2 < 0) ? rest.substring(sp + 1) : rest.substring(sp + 1, sp2);
            delayToken.trim();
            if (delayToken.length() > 0) {
              delayMs = delayToken.toInt();
              if (delayMs < 1) delayMs = 100;
            }
          }
          rampAllServos(angles, stepSize, delayMs, fromSerial);
          return;
        }
        count++;
      }
      if (sp < 0) break;
      startIdx = sp + 1;
    }
    respond("Error: RAMPALL esperaba " + String(numServos) + " angulos + stepSize + delayMs", fromSerial);
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

  if (servoId == GRIPPER_SERVO_ID) {
    cmdAngle = constrain(cmdAngle, GRIPPER_MIN_ANGLE, GRIPPER_MAX_ANGLE);
  }

  setServoImmediate(servoId, cmdAngle);

  respond("OK servo " + String(servoId) + " -> " + String(cmdAngle) + " deg", fromSerial);
}
