# SuoKuulo: hearing the bog recover

Junction 2026, Arduino challenge "The Green European Renaissance". Edge AI on
the Arduino UNO Q, no cloud.

## Story

Finland has drained about half of its original mires for forestry and peat.
Restoring them, by blocking ditches so the peat rewets, stops carbon loss and
brings back wildlife. But checking whether a restoration works means sending
people out to listen, a few mornings a year. Waders and other open-bog birds
return when a mire recovers.

SuoKuulo ("suo" = bog, "kuulo" = hearing) is a small listening station left
alone on the bog. It runs BirdNET on the board itself, turns the birds it hears
into a soundscape health score, and sends a short hourly summary over LoRa to
the restoration team's office. No audio leaves the device.

## How it works

1. A USB microphone records continuously. A 3 s window (48 kHz mono) starts
   every 2 s and goes, high-passed at 1 kHz, to BirdNET v2.4 on the UNO Q's
   Linux side.
2. BirdNET scores 6522 labels at once. We keep 12 bog indicator species (8
   breeding waders and open-bog birds, 2 migrants, 2 resident grouse), each
   judged on its own, so two birds calling together are both counted.
3. A species is confirmed on 2 consecutive windows or one strong window, then
   cools down for 30 s.
4. **Soundscape health (0-100).** It compares what was heard in the last hour
   with what a healthy bog sounds like at this season and time of day: 60 %
   *richness* (share of the expected species heard, golden plover weighted 3)
   and 40 % *activity* (minutes each species was heard vs expected). The
   expectation starts from `config/baseline.yaml` and is learned from the
   device's own log after 3 days.
5. Every hour the Linux side hands a summary to the MCU, which packs it into a
   16-byte LoRa payload: health, richness, activity, which species were heard
   today, detections, uptime and status.
6. The MCU also watches the Linux side. If the analysis stops sending
   heartbeats for 60 s it sends a "Linux down" payload, keeps an hourly
   heartbeat going, and reports when the analysis recovers. The office can
   tell "device dead" (silence) from "device alive, analysis down" from
   "healthy but quiet".
7. Every detection (species, time, confidence, never audio) goes to an
   append-only CSV on the device; daily counters are rebuilt from it after a
   restart. Anyone on the same network can open the dashboard on port 7000.

## Which brain does what

```
            Linux side (Qualcomm QRB2210, Debian, App Lab container)
 USB mic ─> 3 s windows ─> 1 kHz high-pass ─> BirdNET v2.4 (TFLite)
                                               │ detections
                          smoothing ─> health vs seasonal baseline ─> events.csv
                                               │                    └> dashboard :7000
                          Bridge (RPC over the internal UART)
                           │ summary (hourly)        │ heartbeat (every 10 s)
            ───────────────┼─────────────────────────┼──────────────────────────
            MCU side (STM32U585, Zephyr sketch)      v
                     16-byte payload encoder <── watchdog: linux_down / heartbeat / recovered
                           │
                     LoRa radio (SX1276/RFM95 hook; today: hex on the MCU serial)
                     LED matrix: health number + TX icon      Buzzer: startup beep
```

| Linux | MCU |
| --- | --- |
| audio capture, high-pass, BirdNET | LoRa payload encoding and transmit hook |
| smoothing, health score, learned baseline | watchdog of the Linux side, reported over LoRa |
| events.csv, daily counters, dashboard | LED matrix (health, TX), startup beep |

The core package `suokuulo/` has no Arduino imports and runs the same on a
laptop with file or mic input. Only `applab/python/main.py` and the sketch are
board specific.

## All year round

Most indicators are summer migrants, a point raised by a peatland expert who
reviewed the idea. The station keeps reporting when they leave:

- Spring and autumn: whooper swan and spotted redshank join the expected
  list. Taiga bean goose and ruff were tested and left out (2/5 and 0/5 clips
  confirmed).
- Winter: willow ptarmigan and black grouse are expected, but so rarely that
  health reads "Off season (low bird activity expected)"; the uplink keeps
  reporting what is heard and that the device is alive.
- An acoustic index (NDSI) compares bird/insect frequencies with engine/voice
  frequencies every minute. It needs no species and runs all year, shown
  apart from health.

## Why now: EU legal framework

- **Nature Restoration Regulation**, [Regulation (EU) 2024/1991](https://eur-lex.europa.eu/eli/reg/2024/1991/oj/eng),
  in force since 18 August 2024. Each member state had to submit a draft
  national restoration plan by 1 September 2026 (Art. 16), and must then
  monitor the restored areas (Art. 20) and report progress to the Commission
  (Art. 21: from 30 June 2028, at least every 3 years). Peatlands are one of
  its core targets.
- **Drained peatlands in agricultural use** (Art. 11(4)), i.e. cropland and
  grassland on organic soils: restoration measures on 30 % of that area by
  2030 (at least a quarter of it rewetted), 40 % by 2040 and 50 % by 2050 (at
  least a third rewetted). This specific target is for *agricultural*
  peatlands. Most of Finland's drained peatlands are drained for forestry;
  rewetting those can count towards the target, up to 40 % of it.
- **Birds and Habitats Directives, Natura 2000.** Every 6 years member states
  report the status and trends of bird species
  ([Birds Directive 2009/147/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02009L0147-20190626),
  Art. 12) and the conservation status of habitat types
  ([Habitats Directive 92/43/EEC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:01992L0043-20130701),
  Art. 17).
  - Our indicators in Annex I of the Birds Directive: golden plover
    (*Pluvialis apricaria*), wood sandpiper (*Tringa glareola*), common crane
    (*Grus grus*), whooper swan (*Cygnus cygnus*), and black grouse only as the
    continental subspecies *Tetrao tetrix tetrix*. Not in Annex I: spotted
    redshank, curlew, whimbrel, common snipe, meadow pipit, yellow wagtail and
    willow ptarmigan.
  - Peatland habitats that are priority types (\*) in Annex I of the Habitats
    Directive: 7110 \* Active raised bogs, 7310 \* Aapa mires, 7320 \* Palsa
    mires, 91D0 \* Bog woodland. 7120 Degraded raised bogs still capable of
    natural regeneration and 7140 Transition mires and quaking bogs are listed
    but not priority.

Checked on 2026-11-14 against the Official Journal text of the regulation and
the consolidated directives (Birds Directive as of 26 June 2019, Habitats
Directive as of 1 July 2013), fetched from the EU Publications Office.

SuoKuulo does not replace field surveys; it covers the sites and the days where no surveyor is present.

## What is new compared with rainforest acoustic monitoring

Acoustic monitoring of birds is proven in rainforests (Rainforest Connection
streams audio from solar "guardians" to the cloud). SuoKuulo's contribution is
the combination for boreal peatland restoration:

- a health score built for restoration: species expected on a healthy bog, by
  season and time of day, learned per site, so before/after rewetting can be
  compared on the same device;
- everything on one low-cost board, offline, with a few bytes an hour over
  LoRa instead of streaming audio;
- both brains of the UNO Q used for what they are good at: Linux runs the
  model, the MCU owns the radio and watches that the model is alive.

## Power

The UNO Q's Linux side cannot be put to sleep, so the board draws power around
the clock. A field unit therefore runs on battery + solar panel. The draw has
not been measured yet (to do: at the board's USB-C input while listening). The
next version adds an external power timer that switches the board on for the
dawn and dusk chorus only, which is when most indicator birds call.

## Parts

| Part | Notes |
| --- | --- |
| Arduino UNO Q, 2 GB variant | Linux (Qualcomm) + MCU (STM32) on one board; 1.70 GB usable RAM |
| Arduino USB-C hub | stick-shaped, PD power input |
| Official Arduino power supply | powers the hub and board (field: battery + solar) |
| USB microphone | generic USB mic on the hub (enumerates as "Camera", 48 kHz) |
| Arduino Modulino Buzzer (ABX00108) | Qwiic cable to the board's Qwiic connector; startup beep |
| LoRa module, SX1276/RFM95 (planned) | not fitted yet; payloads are printed on the MCU serial |

## Results

Laptop numbers (`scripts/evaluate.py` with the board's settings, one clip at a
time; full tables and the before/after comparison in `eval_results.md`):

| | before fixes | now |
| --- | --- | --- |
| bird clips confirmed (8 breeding species, 81 clips) | 78 % | 88 % |
| seconds of audio to the first bird event (median) | - | 3 |
| golden plover confirmed on non-plover clips | 0 | 0 |
| birds under equal-level speech | - | 74 % |
| two species overlaid, both confirmed | - | 51 of 66 pairs |
| seasonal species (5 clips each): whooper swan, spotted redshank, willow ptarmigan, black grouse | - | 4, 5, 4, 5 of 5 |

On the board (2026-11-14): about 465 ms inference per window with the
high-pass filter (387 ms without), 631 MB of 1738 MB RAM in use, the app 256 MB.
Phone playback 25 cm from the mic confirmed curlew (69 %), crane (73 %) and
wood sandpiper (82 %); a golden plover recording was missed.

Weak spots: the expected-activity numbers are estimates until the device learns
its own; no LoRa module fitted yet; the power figure is still to be measured.

## Future work

- **Disturbance detection** (people, machinery, gunshots). The code path is
  kept behind `disturbance_enabled: false`. BirdNET's machinery labels gave
  too many misses and false alarms for a field product (engines 2/10, field
  chainsaws 0/20); a dedicated model such as YAMNet beside BirdNET would be
  the way back.
- A real SX1276/RFM95 driver in `radioSend()` and a LoRaWAN network server
  decoder (`scripts/decode_payload.py` shows the format).
- Dawn/dusk duty cycling with an external power timer.

## Credits

- BirdNET (K. Lisa Yang Center for Conservation Bioacoustics, Cornell Lab of
  Ornithology, and Chemnitz University of Technology), model v2.4.
- birdnetlib (Joe Weiss), whose package ships the model files we load.
- Test recordings: Xeno-canto recordists, ESC-50 (Karol Piczak) and its
  Freesound contributors, Rainforest Connection (rfcx/frugalai), LibriSpeech.
  Every clip is listed with recordist, licence and URL in `credits.csv`.
- Arduino App Lab, app-bricks-py, Arduino_RouterBridge, Arduino_Modulino.

## Licence note

The BirdNET models are CC BY-NC-SA 4.0, and the test audio is non-commercial
too (Xeno-canto clips mostly CC BY-NC-SA, ESC-50 CC BY-NC 3.0, rfcx/frugalai
CC BY-NC 4.0). That is fine for a hackathon and for research. A commercial
version would train its own model on licensed recordings.
