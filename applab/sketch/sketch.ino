// SuoKuulo MCU sketch: LED matrix + Modulino Buzzer, driven over the Bridge.
//
// Bridge functions (called from python/main.py):
//   show_score(int 0..100)  bar on the bottom 2 rows, 0..13 lit columns
//   show_bird(int index)    bird icon on the top 6 rows for 3 s
//   alarm(bool)             whole matrix blinks at 2 Hz + 2-tone siren
//   chirp(int kind)         0 = one chirp, 1 = two chirps (headline species)
//   mute(bool)              buzzer off; the matrix keeps working
//
// Bridge handlers run on a separate thread from loop() (RouterBridge README).
// They only store values in volatile variables; loop() does every matrix and
// I2C write, so no locking is needed. Nothing here calls delay().

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>

const int ROWS = 8, COLS = 13;
const unsigned long BIRD_MS = 3000;
const unsigned long BLINK_MS = 250;       // 250 on + 250 off = 2 Hz
const unsigned long SIREN_STEP_MS = 250;  // alternate 1000/1500 Hz
const int SIREN_LOW_HZ = 1000, SIREN_HIGH_HZ = 1500;
const int CHIRP_HZ = 2000, CHIRP_MS = 80;
const unsigned long SECOND_CHIRP_MS = 160;
const int BEEP_HZ = 1000, BEEP_MS = 120;

// Bird, top 6 rows (rows 6-7 belong to the score bar).
//   ..##.........
//   ####.........
//   ..#######....
//   ...#########.
//   ....#####....
//   .....#..#....
const uint8_t BIRD[ROWS][COLS] = {
  {0,0,1,1,0,0,0,0,0,0,0,0,0},
  {1,1,1,1,0,0,0,0,0,0,0,0,0},
  {0,0,1,1,1,1,1,1,1,0,0,0,0},
  {0,0,0,1,1,1,1,1,1,1,1,1,0},
  {0,0,0,0,1,1,1,1,1,0,0,0,0},
  {0,0,0,0,0,1,0,0,1,0,0,0,0},
  {0,0,0,0,0,0,0,0,0,0,0,0,0},
  {0,0,0,0,0,0,0,0,0,0,0,0,0},
};

Arduino_LED_Matrix matrix;
ModulinoBuzzer buzzer;

// Written by Bridge handlers, read by loop().
volatile int score = -1;           // -1 = nothing received yet
volatile bool birdPending = false;
volatile bool alarmOn = false;
volatile bool muted = false;
volatile int chirpRequest = -1;    // -1 none, 0 single, 1 double

// Owned by loop().
uint8_t frame[ROWS * COLS], shown[ROWS * COLS];
unsigned long birdSince = 0, sirenStepAt = 0, firstChirpAt = 0;
bool birdVisible = false, sirenPlaying = false, sirenHigh = false, secondChirpDue = false;

void show_score(int s) { score = constrain(s, 0, 100); }
void show_bird(int index) { birdPending = true; }  // one icon for every species
void alarm(bool on) { alarmOn = on; }
void chirp(int kind) { chirpRequest = kind; }
void mute(bool on) { muted = on; }

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);  // brightness 0..7
  matrix.clear();
  memset(shown, 0, sizeof(shown));

  Modulino.begin(Wire1);  // Qwiic connector; official UNO Q examples pass Wire1 explicitly
  bool haveBuzzer = buzzer.begin();  // TODO(hardware): check Monitor prints "buzzer found"

  bool bridgeUp = Bridge.begin();
  Monitor.begin(115200);
  Monitor.println(haveBuzzer ? "buzzer found" : "buzzer NOT found on Qwiic (Wire1)");
  // TODO(hardware): confirm RPClite maps Python int/bool args onto these int/bool handlers.
  Bridge.provide("show_score", show_score);
  Bridge.provide("show_bird", show_bird);
  Bridge.provide("alarm", alarm);
  Bridge.provide("chirp", chirp);
  Bridge.provide("mute", mute);
  // tone() is one I2C write; the module firmware times the note, so it does not block.
  if (bridgeUp) buzzer.tone(BEEP_HZ, BEEP_MS);  // TODO(hardware): beep audible at power-up?
}

void render(unsigned long now) {
  if (birdPending) {
    birdPending = false;
    birdVisible = true;
    birdSince = now;
  }
  if (birdVisible && now - birdSince >= BIRD_MS) birdVisible = false;

  if (alarmOn) {
    memset(frame, (now / BLINK_MS) % 2 ? 0 : 7, sizeof(frame));
  } else {
    memset(frame, 0, sizeof(frame));
    if (birdVisible)
      for (int r = 0; r < 6; r++)
        for (int c = 0; c < COLS; c++) frame[r * COLS + c] = BIRD[r][c] * 7;
    int s = score;
    int lit = s < 0 ? 0 : (s * COLS + 50) / 100;
    for (int r = 6; r < ROWS; r++)
      for (int c = 0; c < lit; c++) frame[r * COLS + c] = 7;
  }
  if (memcmp(frame, shown, sizeof(frame)) != 0) {
    matrix.draw(frame);
    memcpy(shown, frame, sizeof(frame));
  }
}

void sound(unsigned long now) {
  bool sirenWanted = alarmOn && !muted;
  if (sirenWanted && (!sirenPlaying || now - sirenStepAt >= SIREN_STEP_MS)) {
    sirenHigh = !sirenHigh;
    buzzer.tone(sirenHigh ? SIREN_HIGH_HZ : SIREN_LOW_HZ, SIREN_STEP_MS);
    sirenStepAt = now;
  } else if (!sirenWanted && sirenPlaying) {
    buzzer.noTone();
  }
  sirenPlaying = sirenWanted;

  int kind = chirpRequest;
  if (kind >= 0) {
    chirpRequest = -1;
    if (!muted && !sirenPlaying) {  // the siren wins over chirps
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
  unsigned long now = millis();
  render(now);
  sound(now);
}
