// SuoKuulo MCU sketch: LED matrix + Modulino Buzzer, driven over the Bridge.
//
// Matrix (13 x 8): soundscape health only, as digits (3x5 font, rows 0-4,
// columns 0-10) and a bar (row 7, columns 0-10). Columns 11-12 are kept free
// for a small machinery/gunshot alert block (rows 0-1). Disturbance never
// changes the health digits.
//
// Bridge functions (called from python/main.py):
//   show_score(int 0..100)  health; -1 = no score (off season), shown as "--"
//   alarm(bool)             machinery/gunshot alert: corner block + 2-tone siren
//   chirp(int kind)         0 = one chirp, 1 = two chirps (headline species),
//                           2 = startup beep (plays even when muted)
//   mute(bool)              chirps and siren off; the matrix keeps working
//
// Bridge handlers run on a separate thread from loop() (RouterBridge README).
// They only store values in volatile variables; loop() does every matrix and
// I2C write, so no locking is needed. Nothing here calls delay().

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>

const int ROWS = 8, COLS = 13;
const uint8_t DIGIT_LEVEL = 4, BAR_LEVEL = 2, ALERT_LEVEL = 7;  // grayscale 0..7
const unsigned long SIREN_STEP_MS = 250;  // alternate 1000/1500 Hz
const int SIREN_LOW_HZ = 1000, SIREN_HIGH_HZ = 1500;
const int CHIRP_HZ = 2000, CHIRP_MS = 80;
const unsigned long SECOND_CHIRP_MS = 160;
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
volatile bool alarmOn = false;
volatile bool muted = false;
volatile int chirpRequest = -1;    // -1 none, 0 single, 1 double, 2 startup beep

// Owned by loop().
uint8_t frame[ROWS * COLS], shown[ROWS * COLS];
unsigned long sirenStepAt = 0, firstChirpAt = 0;
bool sirenPlaying = false, sirenHigh = false, secondChirpDue = false;

void show_score(int s) { score = s < 0 ? -1 : constrain(s, 0, 100); }
void alarm(bool on) { alarmOn = on; }
void chirp(int kind) { chirpRequest = kind; }
void mute(bool on) { muted = on; }

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
  Bridge.provide("alarm", alarm);
  Bridge.provide("chirp", chirp);
  Bridge.provide("mute", mute);
  // No beep here: python/main.py sends chirp(2) once the whole app is up, if
  // buzzer_startup is set in the config.
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
  if (alarmOn)  // steady 2x2 block, top right
    for (int r = 0; r < 2; r++)
      for (int c = 11; c < COLS; c++) frame[r * COLS + c] = ALERT_LEVEL;

  if (memcmp(frame, shown, sizeof(frame)) != 0) {
    matrix.draw(frame);
    memcpy(shown, frame, sizeof(frame));
  }
}

void sound(unsigned long now) {
  bool sirenWanted = alarmOn && !muted;
  if (sirenWanted && (!sirenPlaying || now - sirenStepAt >= SIREN_STEP_MS)) {
    sirenHigh = !sirenHigh;
    // tone() is one I2C write; the module firmware times the note, so it does not block.
    buzzer.tone(sirenHigh ? SIREN_HIGH_HZ : SIREN_LOW_HZ, SIREN_STEP_MS);
    sirenStepAt = now;
  } else if (!sirenWanted && sirenPlaying) {
    buzzer.noTone();
  }
  sirenPlaying = sirenWanted;

  int kind = chirpRequest;
  if (kind >= 0) {
    chirpRequest = -1;
    if (kind == 2) {
      buzzer.tone(BEEP_HZ, BEEP_MS);  // startup beep, ignores mute
    } else if (!muted && !sirenPlaying) {  // the siren wins over chirps
      buzzer.tone(CHIRP_HZ, CHIRP_MS);
      secondChirpDue = (kind == 1);
      firstChirpAt = now;
    }
  }
  if (secondChirpDue && now - firstChirpAt >= SECOND_CHIRP_MS) {
    secondChirpDue = false;
    if (!muted && !sirenPlaying) buzzer.tone(CHIRP_HZ, CHIRP_MS);
  }
}

void loop() {
  render();
  sound(millis());
}
