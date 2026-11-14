// SuoKuulo MCU sketch: LED matrix + Modulino Buzzer, driven over the Bridge.
//
// Matrix (13 x 8): soundscape health only, as digits (3x5 font, rows 0-4,
// columns 0-10) and a bar (row 7, columns 0-10); a small TX block (columns
// 11-12, rows 0-2) for 3 s after each uplink.
//
// Uplink: Linux sends a summary every hour; this side packs it into the
// 16-byte payload of payload.h and transmits it. radioSend() is where an
// SX1276/RFM95 driver goes; with no module the payload is printed as hex on
// the MCU serial (Monitor) instead.
//
// Bridge functions (called from python/main.py):
//   show_score(int 0..100)  health; -1 = no score (off season), shown as "--"
//   beep(int)               startup beep, the buzzer's only sound
//   summary(health, richness %, activity %, species mask, detections today)
//                           all int; health -1 = no score
//   heartbeat(int)          every 10 s from the analysis loop
//
// Watchdog: if Linux heartbeats stop for 60 s (10 min after boot, while the
// app starts), the MCU sends a linux_down payload; if nothing else went out
// for an hour it sends a heartbeat payload (uptime, minutes since the last
// Linux heartbeat); when heartbeats return it sends one recovered payload.
// So the office can tell device dead (silence) from analysis crashed
// (linux_down / heartbeat without linux_ok) from healthy but quiet (summaries).
// The MCU cannot reset the Linux side: the UNO Q board files expose no line
// from the STM32 to the QRB2210's reset or power (it is the other way round:
// Linux flashes and resets the MCU over SWD). So there is no reset attempt.
//
// Bridge handlers run on a separate thread from loop() (RouterBridge README).
// They only store values in volatile variables; loop() does every matrix and
// I2C write, so no locking is needed. Nothing here calls delay().

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>

#include "payload.h"

const int ROWS = 8, COLS = 13;
const uint8_t DIGIT_LEVEL = 4, BAR_LEVEL = 2;  // grayscale 0..7
const int BEEP_HZ = 1000, BEEP_MS = 120;
const uint8_t TX_LEVEL = 3;
const unsigned long TX_ICON_MS = 3000;
const unsigned long LINUX_DOWN_MS = 60000UL;        // no heartbeat for this long: linux_down
const unsigned long BOOT_GRACE_MS = 600000UL;       // first heartbeat may take this long after boot
const unsigned long HEARTBEAT_TX_MS = 3600000UL;    // MCU heartbeat if nothing else was sent

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
volatile bool summaryPending = false;
Summary incoming;                  // filled by summary(), copied by loop()
volatile unsigned long lastHeartbeatMs = 0;
volatile bool heartbeatArrived = false;

// Owned by loop().
uint8_t frame[ROWS * COLS], shown[ROWS * COLS];
Summary last;                      // latest summary, reused by later payloads
uint8_t seq = 0;
unsigned long txAt = 0;
bool txShown = false;
bool everHeard = false, linuxDown = false;

void show_score(int s) { score = s < 0 ? -1 : constrain(s, 0, 100); }
void beep(int) { beepRequest = true; }
void summary(int health, int richness, int activity, int mask, int detections) {
  incoming.health = health < 0 ? 255 : constrain(health, 0, 100);
  incoming.richness = constrain(richness, 0, 100);
  incoming.activity = constrain(activity, 0, 100);
  incoming.speciesMask = mask & 0xffff;
  incoming.detections = constrain(detections, 0, 65535);
  lastHeartbeatMs = millis();  // a summary is also a sign of life
  heartbeatArrived = true;
  summaryPending = true;  // set last: loop() copies incoming after seeing it
}
void heartbeat(int) {
  lastHeartbeatMs = millis();
  heartbeatArrived = true;
}

// Transmit hook. Returns true if a radio took the packet.
// TODO(hardware): with an SX1276/RFM95 on SPI, e.g. RadioLib:
//   SX1276 radio = new Module(NSS, DIO0, RESET, DIO1);  radio.begin(868.0);
//   return radio.transmit(buf, len) == RADIOLIB_ERR_NONE;
bool radioSend(const uint8_t *buf, size_t len) {
  (void)buf;
  (void)len;
  return false;  // no LoRa module attached
}

uint32_t minutesSinceHeartbeat(unsigned long now) {
  return everHeard ? (now - lastHeartbeatMs) / 60000UL : 65535;
}

void transmit(uint8_t type, uint8_t flags, uint32_t sinceHeartbeatMin) {
  uint8_t buf[PAYLOAD_LEN];
  size_t n = encodePayload(buf, type, flags, last, millis() / 1000,
                           sinceHeartbeatMin > 65535 ? 65535 : sinceHeartbeatMin, seq++);
  bool sent = radioSend(buf, n);
  char hex[2 * PAYLOAD_LEN + 1];
  for (size_t i = 0; i < n; i++) snprintf(hex + 2 * i, 3, "%02x", buf[i]);
  Monitor.print(sent ? "[uplink] sent " : "[uplink] no radio, payload ");
  Monitor.println(hex);
  txAt = millis();
  txShown = true;
}

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
  Bridge.provide("summary", summary);
  Bridge.provide("heartbeat", heartbeat);
  transmit(TYPE_HEARTBEAT, 0, minutesSinceHeartbeat(millis()));  // MCU booted
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
  if (txShown)
    for (int r = 0; r < 3; r++)
      for (int c = 11; c < COLS; c++) frame[r * COLS + c] = TX_LEVEL;
  if (memcmp(frame, shown, sizeof(frame)) != 0) {
    matrix.draw(frame);
    memcpy(shown, frame, sizeof(frame));
  }
}

void loop() {
  unsigned long now = millis();
  if (beepRequest) {
    beepRequest = false;
    buzzer.tone(BEEP_HZ, BEEP_MS);  // one I2C write; the module times the note
  }
  if (heartbeatArrived) {
    heartbeatArrived = false;
    everHeard = true;
    if (linuxDown) {
      linuxDown = false;
      transmit(TYPE_RECOVERED, FLAG_LINUX_OK, 0);
    }
  }
  if (summaryPending) {
    summaryPending = false;
    last = incoming;
    transmit(TYPE_SUMMARY, FLAG_LINUX_OK, 0);
  }
  unsigned long silentFor = now - (everHeard ? lastHeartbeatMs : 0);
  if (!linuxDown && silentFor > (everHeard ? LINUX_DOWN_MS : BOOT_GRACE_MS)) {
    linuxDown = true;
    transmit(TYPE_LINUX_DOWN, 0, minutesSinceHeartbeat(now));
  }
  if (now - txAt >= HEARTBEAT_TX_MS)
    transmit(TYPE_HEARTBEAT, linuxDown ? 0 : FLAG_LINUX_OK, minutesSinceHeartbeat(now));
  if (txShown && now - txAt >= TX_ICON_MS) txShown = false;
  render();
}
