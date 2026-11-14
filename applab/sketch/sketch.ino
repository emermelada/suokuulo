// SuoKuulo MCU sketch: LED matrix + Modulino Buzzer, driven over the Bridge.
//
// Matrix (13 x 8): soundscape health only, as digits (3x5 font, rows 0-4,
// columns 0-10) and a bar (row 7, columns 0-10).
//
// Bridge functions (called from python/main.py):
//   show_score(int 0..100)  health; -1 = no score (off season), shown as "--"
//   beep(int)               startup beep, the buzzer's only sound
//
// Bridge handlers run on a separate thread from loop() (RouterBridge README).
// They only store values in volatile variables; loop() does every matrix and
// I2C write, so no locking is needed. Nothing here calls delay().

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>

const int ROWS = 8, COLS = 13;
const uint8_t DIGIT_LEVEL = 4, BAR_LEVEL = 2;  // grayscale 0..7
const int BEEP_HZ = 1000, BEEP_MS = 120;

// 3x5 digits, one byte per row, bit 2 = left column. Index 10 = "-".
const uint8_t FONT[11][5] = {
  {7,5,5,5,7}, {2,6,2,2,7}, {7,1,7,4,7}, {7,1,7,1,7}, {5,5,7,1,1},
  {7,4,7,1,7}, {7,4,7,5,7}, {7,1,1,1,1}, {7,5,7,5,7}, {7,5,7,1,7},
  {0,0,7,0,0},
};

Arduino_LED_Matrix matrix;
ModulinoBuzzer buzzer;

// Written by Bridge handlers, read by loop().
volatile int score = -1;           // -1 = no score yet / off season
volatile bool beepRequest = false;

// Owned by loop().
uint8_t frame[ROWS * COLS], shown[ROWS * COLS];

void show_score(int s) { score = s < 0 ? -1 : constrain(s, 0, 100); }
void beep(int) { beepRequest = true; }

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);  // brightness 0..7
  matrix.clear();
  memset(shown, 0, sizeof(shown));

  Modulino.begin(Wire1);  // Qwiic connector; official UNO Q examples pass Wire1 explicitly
  bool haveBuzzer = buzzer.begin();

  Bridge.begin();
  Monitor.begin(115200);
  Monitor.println(haveBuzzer ? "buzzer found" : "buzzer NOT found on Qwiic (Wire1)");
  Bridge.provide("show_score", show_score);
  Bridge.provide("beep", beep);
}

// Draws glyph g of FONT with its left column at col.
void drawGlyph(int g, int col) {
  for (int r = 0; r < 5; r++)
    for (int c = 0; c < 3; c++)
      if (FONT[g][r] & (4 >> c)) frame[r * COLS + col + c] = DIGIT_LEVEL;
}

void render() {
  memset(frame, 0, sizeof(frame));
  int s = score;
  if (s < 0) {
    drawGlyph(10, 4);  // "--"
    drawGlyph(10, 8);
  } else {
    // Right-aligned in columns 0-10: hundreds at 0, tens at 4, units at 8.
    if (s >= 100) drawGlyph(s / 100, 0);
    if (s >= 10) drawGlyph((s / 10) % 10, 4);
    drawGlyph(s % 10, 8);
    int lit = (s * 11 + 50) / 100;
    for (int c = 0; c < lit; c++) frame[7 * COLS + c] = BAR_LEVEL;
  }
  if (memcmp(frame, shown, sizeof(frame)) != 0) {
    matrix.draw(frame);
    memcpy(shown, frame, sizeof(frame));
  }
}

void loop() {
  if (beepRequest) {
    beepRequest = false;
    buzzer.tone(BEEP_HZ, BEEP_MS);  // one I2C write; the module times the note
  }
  render();
}
