/*
  JARVIS board firmware — Arduino Uno / Nano / Mega / Leonardo (USB serial)
  ========================================================================
  Upload with the Arduino IDE, leave the board plugged in, and tell JARVIS
  "add my Arduino" (it finds the COM port by itself).

  Same line protocol as the ESP32 firmware, at 115200 baud:
    PING | STATUS | PIN <p> HIGH|LOW | TOGGLE <p> | PWM <p> <0-255>
    SERVO <p> <0-180> | MOTOR A|B <-255..255> | STEPPER <steps> [rpm]
    READ <p> | AREAD <p> | DIST
  PWM works on the ~ pins (3, 5, 6, 9, 10, 11 on an Uno).
*/
#include <Servo.h>

// DC motors through an L298N (ENA/ENB must be PWM pins); -1 = unused
const int MOTOR_A_IN1 = 7, MOTOR_A_IN2 = 8, MOTOR_A_EN = 5;
const int MOTOR_B_IN1 = 12, MOTOR_B_IN2 = 13, MOTOR_B_EN = 6;
// Stepper through an A4988 / DRV8825
const int STEPPER_STEP = 2, STEPPER_DIR = 4;
// HC-SR04
const int SONAR_TRIG = A1, SONAR_ECHO = A2;

Servo servos[4];
int servoPins[4] = {-1, -1, -1, -1};

void servoWrite(int pin, int angle) {
  int slot = -1;
  for (int i = 0; i < 4; i++) if (servoPins[i] == pin) slot = i;
  for (int i = 0; slot < 0 && i < 4; i++) if (servoPins[i] < 0) { slot = i; servoPins[i] = pin; servos[i].attach(pin); }
  if (slot >= 0) servos[slot].write(angle);
}

void motor(char which, int speed) {
  int in1 = which == 'A' ? MOTOR_A_IN1 : MOTOR_B_IN1;
  int in2 = which == 'A' ? MOTOR_A_IN2 : MOTOR_B_IN2;
  int en  = which == 'A' ? MOTOR_A_EN  : MOTOR_B_EN;
  if (in1 < 0 || in2 < 0) return;
  pinMode(in1, OUTPUT); pinMode(in2, OUTPUT);
  digitalWrite(in1, speed > 0 ? HIGH : LOW);
  digitalWrite(in2, speed < 0 ? HIGH : LOW);
  if (en >= 0) { pinMode(en, OUTPUT); analogWrite(en, constrain(abs(speed), 0, 255)); }
}

void stepper(long steps, int rpm) {
  pinMode(STEPPER_STEP, OUTPUT); pinMode(STEPPER_DIR, OUTPUT);
  digitalWrite(STEPPER_DIR, steps >= 0 ? HIGH : LOW);
  if (rpm < 1) rpm = 60;
  unsigned long us = 60000000UL / (200UL * rpm) / 2;
  for (long i = 0; i < labs(steps); i++) {
    digitalWrite(STEPPER_STEP, HIGH); delayMicroseconds(us);
    digitalWrite(STEPPER_STEP, LOW);  delayMicroseconds(us);
  }
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

  if (cmd == "PING") return F("OK JARVIS arduino uno 1.0");
  if (cmd == "STATUS") return String("{\"board\":\"arduino\",\"fw\":\"1.0\",\"uptime_s\":") + (millis() / 1000) + "}";
  if (cmd == "PIN") { int p = a1.toInt(); pinMode(p, OUTPUT); bool h = (a2 == "HIGH" || a2 == "1" || a2 == "ON"); digitalWrite(p, h); return "OK PIN " + String(p) + (h ? " HIGH" : " LOW"); }
  if (cmd == "TOGGLE") { int p = a1.toInt(); pinMode(p, OUTPUT); int v = !digitalRead(p); digitalWrite(p, v); return "OK PIN " + String(p) + (v ? " HIGH" : " LOW"); }
  if (cmd == "PWM") { int p = a1.toInt(); int v = constrain(a2.toInt(), 0, 255); pinMode(p, OUTPUT); analogWrite(p, v); return "OK PWM " + String(p) + " " + String(v); }
  if (cmd == "SERVO") { int p = a1.toInt(); int v = constrain(a2.toInt(), 0, 180); servoWrite(p, v); return "OK SERVO " + String(p) + " " + String(v); }
  if (cmd == "MOTOR") { char m = a1.length() ? a1[0] : 'A'; int v = constrain(a2.toInt(), -255, 255); motor(m, v); return "OK MOTOR " + String(m) + " " + String(v); }
  if (cmd == "STEPPER") { long st = a1.toInt(); int rpm = a2.length() ? a2.toInt() : 60; stepper(st, rpm); return "OK STEPPER " + String(st); }
  if (cmd == "READ") { int p = a1.toInt(); pinMode(p, INPUT); return "VAL " + String(digitalRead(p)); }
  if (cmd == "AREAD") { int p = a1.toInt(); return "VAL " + String(analogRead(p)) + " /1023"; }
  if (cmd == "DIST") {
    pinMode(SONAR_TRIG, OUTPUT); pinMode(SONAR_ECHO, INPUT);
    digitalWrite(SONAR_TRIG, LOW); delayMicroseconds(2);
    digitalWrite(SONAR_TRIG, HIGH); delayMicroseconds(10); digitalWrite(SONAR_TRIG, LOW);
    unsigned long d = pulseIn(SONAR_ECHO, HIGH, 30000UL);
    if (d == 0) return F("ERR no echo");
    return "VAL " + String(d / 58.0, 1) + " cm";
  }
  if (cmd == "TEMP") return F("ERR no temperature sensor in this build");
  return "ERR unknown command: " + line;
}

String buf;
void setup() { Serial.begin(115200); Serial.println(F("# JARVIS arduino ready")); }
void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') { if (buf.length()) { Serial.println(handle(buf)); buf = ""; } }
    else if (buf.length() < 80) buf += c;
  }
}
