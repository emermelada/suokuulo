// SuoKuulo uplink payload, version 1: 16 bytes, little-endian.
// Plain C++ with no Arduino headers, so the encoder can be compiled and
// round-trip tested on a laptop (tests/test_payload.py). Decoder:
// scripts/decode_payload.py.
//
//  byte  field
//  0     version (high nibble) | type (low nibble)
//  1     flags
//  2     health 0-100, 255 = no score (off season, or no summary yet)
//  3     richness %, 4 activity %
//  5-6   species bitmask: bit i = i-th indicator in config/species.yaml heard today
//  7-8   detections today
//  9-12  MCU uptime, seconds
//  13-14 minutes since the last Linux heartbeat, 65535 = none since boot
//  15    sequence number (wraps), to spot lost packets
#pragma once
#include <stddef.h>
#include <stdint.h>

const uint8_t PAYLOAD_VERSION = 1;
const size_t PAYLOAD_LEN = 16;

enum PayloadType : uint8_t {
  TYPE_SUMMARY = 1,     // hourly bird summary from Linux
  TYPE_LINUX_DOWN = 2,  // no Linux heartbeat for 60 s
  TYPE_HEARTBEAT = 3,   // MCU alive, sent if nothing else went out for an hour
  TYPE_RECOVERED = 4,   // Linux heartbeats are back
};

enum PayloadFlag : uint8_t {
  FLAG_LINUX_OK = 1,    // Linux heartbeat within the last 60 s
  FLAG_OFF_SEASON = 2,  // health has no number (few birds expected)
};

struct Summary {
  uint8_t health = 255, richness = 0, activity = 0;
  uint16_t speciesMask = 0, detections = 0;
};

static inline void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xff; p[1] = v >> 8; }

// Writes PAYLOAD_LEN bytes to out and returns PAYLOAD_LEN.
static inline size_t encodePayload(uint8_t *out, uint8_t type, uint8_t flags, const Summary &s,
                                   uint32_t uptimeS, uint16_t sinceHeartbeatMin, uint8_t seq) {
  out[0] = (PAYLOAD_VERSION << 4) | (type & 0x0f);
  out[1] = flags | (s.health == 255 ? FLAG_OFF_SEASON : 0);
  out[2] = s.health;
  out[3] = s.richness;
  out[4] = s.activity;
  put16(out + 5, s.speciesMask);
  put16(out + 7, s.detections);
  put16(out + 9, uptimeS & 0xffff);
  put16(out + 11, uptimeS >> 16);
  put16(out + 13, sinceHeartbeatMin);
  out[15] = seq;
  return PAYLOAD_LEN;
}
