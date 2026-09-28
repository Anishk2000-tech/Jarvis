/*
  JARVIS board firmware — ESP32 and ESP8266
  ==========================================
  Lets the JARVIS assistant switch pins, dim LEDs, move servos, drive DC and
  stepper motors and read sensors, over WiFi (HTTP) and over the USB cable.

  1. Arduino IDE → Boards Manager: install "esp32" (Espressif) or "esp8266".
  2. Fill in WIFI_SSID / WIFI_PASS below (leave empty for USB-only use).
  3. Adjust the motor / sensor pins to your wiring, pick your board, Upload.
  4. Open Serial Monitor at 115200 to see the IP, then tell JARVIS:
       "add my board at 192.168.1.50"      or just "discover my boards"
     (it also answers as http://jarvis-<name>.local).

  Line protocol (serial or http://<ip>/cmd?c=<line>):
    PING | STATUS | PIN <p> HIGH|LOW | TOGGLE <p> | PWM <p> <0-255>
    SERVO <p> <0-180> | MOTOR A|B <-255..255> | STEPPER <steps> [rpm]
    READ <p> | AREAD <p> | DIST | TEMP
  Every reply is one line starting with OK, VAL or ERR.
*/

// ─────────────────────────── configuration ────────────────────────────────
const char* WIFI_SSID = "";            // your WiFi name
const char* WIFI_PASS = "";            // your WiFi password
const char* BOARD_NAME = "esp32";      // advertised as jarvis-<name>.local

// DC motors through an L298N / L9110 / TB6612 (set a pin to -1 if unused)
const int MOTOR_A_IN1 = 26, MOTOR_A_IN2 = 27, MOTOR_A_EN = 14;
const int MOTOR_B_IN1 = 25, MOTOR_B_IN2 = 33, MOTOR_B_EN = 32;
// Stepper through an A4988 / DRV8825
const int STEPPER_STEP = 18, STEPPER_DIR = 19, STEPPER_EN = -1;
// HC-SR04 ultrasonic distance sensor
const int SONAR_TRIG = 5, SONAR_ECHO = 17;
// DHT11 / DHT22 temperature sensor (needs the "DHT sensor library" by Adafruit)
#define USE_DHT 0
const int DHT_PIN = 4;
#define DHT_TYPE DHT22
// ───────────────────────────────────────────────────────────────────────────

#define FW_VERSION "1.0"

#if defined(ESP8266)
  #include <ESP8266WiFi.h>
  #include <ESP8266WebServer.h>
  #include <ESP8266mDNS.h>
  #include <Servo.h>
  ESP8266WebServer server(80);
  #define BOARD_KIND "esp8266"
  #define ADC_MAX 1023
#else
  #include <WiFi.h>
  #include <WebServer.h>
  #include <ESPmDNS.h>
  WebServer server(80);
  #define BOARD_KIND "esp32"
  #define ADC_MAX 4095
#endif

#if USE_DHT
  #include <DHT.h>
  DHT dht(DHT_PIN, DHT_TYPE);
#endif

// ── PWM / servo helpers that work on ESP32 core 2.x, 3.x and ESP8266 ──────
#if defined(ESP8266)
  Servo servos[4];
  int servoPins[4] = {-1, -1, -1, -1};
  void pwmWrite(int pin, int v) { pinMode(pin, OUTPUT); analogWrite(pin, v); }
  void servoWrite(int pin, int angle) {
    int slot = -1;
    for (int i = 0; i < 4; i++) if (servoPins[i] == pin) slot = i;
    for (int i = 0; slot < 0 && i < 4; i++) if (servoPins[i] < 0) { slot = i; servoPins[i] = pin; servos[i].attach(pin); }
    if (slot < 0) return;
    servos[slot].write(angle);
  }
#else
  // Each pin gets its own LEDC channel the first time it is used.
  int ledcPinOf[16]; int ledcFreqOf[16]; int ledcCount = 0;
  int channelFor(int pin, int freq, int bits) {
    for (int i = 0; i < ledcCount; i++) if (ledcPinOf[i] == pin) {
      if (ledcFreqOf[i] != freq) {
      #if ESP_ARDUINO_VERSION_MAJOR >= 3
        ledcDetach(pin); ledcAttach(pin, freq, bits);
      #else
        ledcSetup(i, freq, bits); ledcAttachPin(pin, i);
      #endif
        ledcFreqOf[i] = freq;
      }
      return i;
    }
    if (ledcCount >= 16) return -1;
    int ch = ledcCount++;
    ledcPinOf[ch] = pin; ledcFreqOf[ch] = freq;
  #if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(pin, freq, bits);
  #else
    ledcSetup(ch, freq, bits); ledcAttachPin(pin, ch);
  #endif
    return ch;
  }
  void ledcOut(int pin, int ch, uint32_t duty) {
  #if ESP_ARDUINO_VERSION_MAJOR >= 3
    (void)ch; ledcWrite(pin, duty);
  #else
    ledcWrite(ch, duty);
  #endif
  }
  void pwmWrite(int pin, int v) { int ch = channelFor(pin, 5000, 8); if (ch >= 0) ledcOut(pin, ch, v); }
  void servoWrite(int pin, int angle) {
    int ch = channelFor(pin, 50, 14);                 // 50 Hz, 14-bit
    if (ch < 0) return;
    uint32_t us = 500 + (uint32_t)angle * 2000 / 180; // 0.5–2.5 ms pulse
    ledcOut(pin, ch, us * 16384UL / 20000UL);
  }
#endif

void motor(char which, int speed) {
  int in1 = which == 'A' ? MOTOR_A_IN1 : MOTOR_B_IN1;
  int in2 = which == 'A' ? MOTOR_A_IN2 : MOTOR_B_IN2;
  int en  = which == 'A' ? MOTOR_A_EN  : MOTOR_B_EN;
  if (in1 < 0 || in2 < 0) return;
  pinMode(in1, OUTPUT); pinMode(in2, OUTPUT);
  digitalWrite(in1, speed > 0 ? HIGH : LOW);
  digitalWrite(in2, speed < 0 ? HIGH : LOW);
  int mag = abs(speed); if (mag > 255) mag = 255;
  if (en >= 0) pwmWrite(en, mag);
}

void stepper(long steps, int rpm) {
  if (STEPPER_STEP < 0) return;
  pinMode(STEPPER_STEP, OUTPUT); pinMode(STEPPER_DIR, OUTPUT);
  if (STEPPER_EN >= 0) { pinMode(STEPPER_EN, OUTPUT); digitalWrite(STEPPER_EN, LOW); }
  digitalWrite(STEPPER_DIR, steps >= 0 ? HIGH : LOW);
  if (rpm < 1) rpm = 60;
  unsigned long us = 60000000UL / (200UL * rpm) / 2;   // 200 steps / revolution
  for (long i = 0; i < labs(steps); i++) {
    digitalWrite(STEPPER_STEP, HIGH); delayMicroseconds(us);
    digitalWrite(STEPPER_STEP, LOW);  delayMicroseconds(us);
    if ((i & 63) == 0) yield();
  }
  if (STEPPER_EN >= 0) digitalWrite(STEPPER_EN, HIGH);
}

String statusJson() {
  String s = "{\"board\":\"" BOARD_KIND "\",\"name\":\"";
  s += BOARD_NAME; s += "\",\"fw\":\"" FW_VERSION "\",\"ip\":\"";
  s += WiFi.isConnected() ? WiFi.localIP().toString() : String("");
  s += "\",\"uptime_s\":"; s += String(millis() / 1000);
  s += ",\"rssi\":"; s += String(WiFi.isConnected() ? WiFi.RSSI() : 0);
  s += "}";
  return s;
}

String handle(String line) {
  line.trim();
  String up = line; up.toUpperCase();
  int sp1 = up.indexOf(' ');
  String cmd = sp1 < 0 ? up : up.substring(0, sp1);
  String rest = sp1 < 0 ? "" : up.substring(sp1 + 1);
  rest.trim();
  int sp2 = rest.indexOf(' ');
  String a1 = sp2 < 0 ? rest : rest.substring(0, sp2);
  String a2 = sp2 < 0 ? "" : rest.substring(sp2 + 1);
  a2.trim();

  if (cmd == "PING") return String("OK JARVIS " BOARD_KIND " ") + BOARD_NAME + " " FW_VERSION;
  if (cmd == "STATUS") return statusJson();
  if (cmd == "PIN") {
    int p = a1.toInt(); pinMode(p, OUTPUT);
    bool high = (a2 == "HIGH" || a2 == "1" || a2 == "ON");
    digitalWrite(p, high ? HIGH : LOW);
    return "OK PIN " + String(p) + (high ? " HIGH" : " LOW");
  }
  if (cmd == "TOGGLE") {
    int p = a1.toInt(); pinMode(p, OUTPUT);
    int v = !digitalRead(p); digitalWrite(p, v);
    return "OK PIN " + String(p) + (v ? " HIGH" : " LOW");
  }
  if (cmd == "PWM") { int p = a1.toInt(); int v = constrain(a2.toInt(), 0, 255); pwmWrite(p, v); return "OK PWM " + String(p) + " " + String(v); }
  if (cmd == "SERVO") { int p = a1.toInt(); int v = constrain(a2.toInt(), 0, 180); servoWrite(p, v); return "OK SERVO " + String(p) + " " + String(v); }
  if (cmd == "MOTOR") { char m = a1.length() ? a1[0] : 'A'; int v = constrain(a2.toInt(), -255, 255); motor(m, v); return "OK MOTOR " + String(m) + " " + String(v); }
  if (cmd == "STEPPER") { long st = a1.toInt(); int rpm = a2.length() ? a2.toInt() : 60; stepper(st, rpm); return "OK STEPPER " + String(st); }
  if (cmd == "READ") { int p = a1.toInt(); pinMode(p, INPUT); return "VAL " + String(digitalRead(p)); }
  if (cmd == "AREAD") { int p = a1.toInt(); return "VAL " + String(analogRead(p)) + " /" + String(ADC_MAX); }
  if (cmd == "DIST") {
    if (SONAR_TRIG < 0) return "ERR no sonar pins set";
    pinMode(SONAR_TRIG, OUTPUT); pinMode(SONAR_ECHO, INPUT);
    digitalWrite(SONAR_TRIG, LOW); delayMicroseconds(2);
    digitalWrite(SONAR_TRIG, HIGH); delayMicroseconds(10); digitalWrite(SONAR_TRIG, LOW);
    unsigned long d = pulseIn(SONAR_ECHO, HIGH, 30000UL);
    if (d == 0) return "ERR no echo";
    return "VAL " + String(d / 58.0, 1) + " cm";
  }
  if (cmd == "TEMP") {
  #if USE_DHT
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (isnan(t)) return "ERR sensor not answering";
    return "VAL " + String(t, 1) + " C " + String(h, 0) + " %";
  #else
    return "ERR DHT support is off (set USE_DHT 1)";
  #endif
  }
  return "ERR unknown command: " + line;
}

void setup() {
  Serial.begin(115200);
  delay(200);
#if USE_DHT
  dht.begin();
#endif
  if (strlen(WIFI_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) { delay(300); Serial.print("# ."); }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("# WiFi connected, IP "); Serial.println(WiFi.localIP());
      String host = String("jarvis-") + BOARD_NAME;
      if (MDNS.begin(host.c_str())) MDNS.addService("jarvis", "tcp", 80);
      server.on("/cmd", []() {
        String line = server.hasArg("c") ? server.arg("c") : "";
        server.sendHeader("Access-Control-Allow-Origin", "*");
        server.send(200, "text/plain", handle(line));
      });
      server.on("/status", []() { server.send(200, "application/json", statusJson()); });
      server.on("/", []() { server.send(200, "text/plain", String("JARVIS board ") + BOARD_NAME + " — use /cmd?c=PING"); });
      server.begin();
    } else {
      Serial.println("# WiFi not connected — USB serial only");
    }
  }
  Serial.println(String("# JARVIS ") + BOARD_KIND + " ready");
}

String serialBuf;
void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    server.handleClient();
  #if defined(ESP8266)
    MDNS.update();
  #endif
  }
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuf.length()) { Serial.println(handle(serialBuf)); serialBuf = ""; }
    } else if (serialBuf.length() < 120) {
      serialBuf += c;
    }
  }
}
