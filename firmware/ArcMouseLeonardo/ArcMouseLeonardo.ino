// Arduino Leonardo / Micro (ATmega32u4). No macros stored on the MCU.
// Optional physical emergency-stop button: D2 -> GND (INPUT_PULLUP).
#include <Mouse.h>
#include <stdlib.h>
#include <string.h>

constexpr uint8_t KILL_PIN = 2;
constexpr unsigned long WATCHDOG_MS = 150;
char line[64];
uint8_t used = 0;
bool overflowed = false;
bool armed = false;
unsigned long lastCommand = 0;

void releaseAll() {
  Mouse.release(MOUSE_LEFT | MOUSE_RIGHT | MOUSE_MIDDLE);
  armed = false;
}

void reply(unsigned long sequence, const char *text) {
  Serial.print(sequence);
  Serial.print(' ');
  Serial.println(text);
}

bool integer(const char *text, long &result) {
  if (!text || !*text) return false;
  char *end;
  result = strtol(text, &end, 10);
  return *end == '\0';
}

void execute(char *text) {
  char *seqText = strtok(text, " ");
  char *command = strtok(nullptr, " ");
  long sequence;
  if (!integer(seqText, sequence) || sequence < 0 || !command) { releaseAll(); return; }
  if (!strcmp(command, "STOP")) { releaseAll(); reply(sequence, "OK"); return; }
  if (!strcmp(command, "HELLO")) { releaseAll(); reply(sequence, "ARCMOUSE/1"); return; }
  if (digitalRead(KILL_PIN) == LOW) { releaseAll(); reply(sequence, "ERR KILL"); return; }
  if (!strcmp(command, "ARM")) {
    armed = true;
    lastCommand = millis();
    reply(sequence, "OK");
    return;
  }
  if (!armed || millis() - lastCommand > WATCHDOG_MS) {
    releaseAll(); reply(sequence, "ERR DISARMED"); return;
  }
  lastCommand = millis();
  if (!strcmp(command, "MOVE")) {
    long dx, dy;
    char *a = strtok(nullptr, " ");
    char *b = strtok(nullptr, " ");
    if (!integer(a, dx) || !integer(b, dy) || strtok(nullptr, " ") ||
        dx < -127 || dx > 127 || dy < -127 || dy > 127) {
      releaseAll(); reply(sequence, "ERR MOVE"); return;
    }
    Mouse.move((signed char)dx, (signed char)dy, 0);
  } else if (!strcmp(command, "CLICK")) {
    long button;
    if (!integer(strtok(nullptr, " "), button) || strtok(nullptr, " ") ||
        (button != 1 && button != 2 && button != 4)) {
      releaseAll(); reply(sequence, "ERR CLICK"); return;
    }
    Mouse.press(button);
    delay(5);
    Mouse.release(button);
  } else {
    releaseAll(); reply(sequence, "ERR COMMAND"); return;
  }
  reply(sequence, "OK");
}

void setup() {
  pinMode(KILL_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  Mouse.begin();
  releaseAll();
}

void loop() {
  if (digitalRead(KILL_PIN) == LOW || (armed && millis() - lastCommand > WATCHDOG_MS)) releaseAll();
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (!overflowed) { line[used] = '\0'; execute(line); }
      else releaseAll();
      used = 0;
      overflowed = false;
    } else if (c != '\r') {
      if (used < sizeof(line) - 1 && !overflowed) line[used++] = c;
      else { overflowed = true; releaseAll(); }
    }
  }
}
