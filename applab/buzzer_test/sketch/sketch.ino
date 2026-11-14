// SuoKuulo buzzer test: proves the Qwiic wiring and Arduino_Modulino library.
// Loops: startup beep, indicator chirp, golden plover double chirp, 2 s siren.
// No delay(): a step table advanced with millis(), same pattern as the app.
// If the buzzer is not found on Wire1, the LED matrix shows an X.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>

struct Step { int hz; unsigned long ms; const char* label; };  // hz 0 = silence

const Step SEQ[] = {
  {1000, 120, "beep"},   {0, 880, nullptr},
  {2000, 80, "chirp"},   {0, 920, nullptr},
  {2000, 80, "chirp x2"}, {0, 80, nullptr}, {2000, 80, nullptr}, {0, 760, nullptr},
  {1000, 250, "siren"}, {1500, 250, nullptr}, {1000, 250, nullptr}, {1500, 250, nullptr},
  {1000, 250, nullptr}, {1500, 250, nullptr}, {1000, 250, nullptr}, {1500, 250, nullptr},
  {0, 1500, nullptr},
};
const int N = sizeof(SEQ) / sizeof(SEQ[0]);

Arduino_LED_Matrix matrix;
ModulinoBuzzer buzzer;
int step = 0;
unsigned long stepAt = 0;

void play(int i) {
  if (SEQ[i].hz) buzzer.tone(SEQ[i].hz, SEQ[i].ms);
  if (SEQ[i].label) Monitor.println(SEQ[i].label);
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  matrix.clear();
  Bridge.begin();
  Monitor.begin(115200);

  Modulino.begin(Wire1);
  if (!buzzer.begin()) {
    Monitor.println("buzzer NOT found on Qwiic (Wire1): check the cable");
    uint8_t x[8 * 13] = {0};
    for (int r = 0; r < 8; r++) x[r * 13 + 2 + r] = x[r * 13 + 10 - r] = 7;
    matrix.draw(x);
  } else {
    Monitor.println("buzzer found");
  }
  stepAt = millis();
  play(step);
}

void loop() {
  unsigned long now = millis();
  if (now - stepAt >= SEQ[step].ms) {
    step = (step + 1) % N;
    stepAt = now;
    play(step);
  }
}
