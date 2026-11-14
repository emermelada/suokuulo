# SuoKuulo: hearing the bog recover

Junction 2026, Arduino challenge "The Green European Renaissance". Edge AI on
the Arduino UNO Q, no cloud.

## Story

Finland has drained about half of its original mires for forestry and peat.
Restoring them, by blocking ditches so the peat rewets, stops carbon loss and
brings back wildlife. But checking whether a restoration works means sending
people out to listen, a few mornings a year. Waders and other open-bog birds
return when a mire recovers; machinery and gunfire mean disturbance.

SuoKuulo ("suo" = bog, "kuulo" = hearing) is a small listening station. It runs
BirdNET on the board itself, turns what it hears into a soundscape health
score and a separate disturbance report, shows health on the LED matrix,
sounds an alarm on machinery, and serves a local dashboard. No audio and no
data leave the device.

## How it works

1. A USB microphone records continuously. A 3 s window (48 kHz mono) starts
   every 2 s and goes, high-passed at 1 kHz, to BirdNET v2.4 on the UNO Q's
   Linux side.
2. BirdNET scores 6522 labels at once. We keep 8 bog indicator species and 4
   disturbance labels (Engine, Power tools, Gun, Human vocal), each judged on
   its own, so a bird is still counted while people talk.
3. A label is confirmed on 2 consecutive windows or one strong window, then
   cools down for 30 s. Engine, power tools and gun are pooled into one
   machinery signal.
4. Two separate outputs:
   - **Soundscape health (0-100), birds only.** It compares what we heard in
     the last hour with what a healthy bog sounds like at this season and time
     of day: 60 % *richness* (share of the expected species heard, golden
     plover weighted 3) and 40 % *activity* (minutes each species was heard vs
     expected). The expectation starts from `config/baseline.yaml` and is
     learned from the device's own log after 3 days.
   - **Disturbance pressure.** People, machinery and gunshots per day, and a
     Low/Moderate/High level from minutes disturbed in the last hour. It never
     lowers health. People show as "People nearby"; only machinery and
     gunshots raise the alert.
5. The LED matrix shows the health number, plus a small corner block during a
   machinery alert; the buzzer chirps for birds (twice for the golden plover)
   and sounds a siren for machinery.
6. Every event (label, time, confidence, never audio) goes to an append-only
   CSV on the device; daily counters are rebuilt from it after a restart.

## What is new compared with rainforest acoustic monitoring

Acoustic monitoring of birds and chainsaws is proven in rainforests
(Rainforest Connection streams audio from solar "guardians" to the cloud).
SuoKuulo's contribution is the combination for boreal peatland restoration:

- a health score built for restoration: species expected on a healthy bog,
  by season and time of day, learned per site, so before/after rewetting can
  be compared on the same device;
- everything on a low-cost board, offline: no audio leaves it, people are
  stored only as a label, and it works where there is no network;
- bird health and disturbance kept apart, so a noisy day does not read as a
  degraded bog.

## Architecture

```
 USB mic ──> [ Linux side (Python, App Lab container) ]                      [ MCU side (Zephyr sketch) ]
             AppLabMicSource ─ 3 s windows every 2 s                           LED matrix 8x13
                  │                                                              - health digits + bar
             BirdNetClassifier (1 kHz high-pass, BirdNET v2.4 TFLite)           - corner block on machinery alert
                  │  Detection(label, kind, confidence)                         Modulino Buzzer (Qwiic, Wire1)
             Smoother (2 consecutive / 1 strong, cooldown, machinery pooled)     - startup beep
                  │ events                                                       - chirp / double chirp
             Soundscape: health vs baseline.yaml, disturbance pressure,          - siren while machinery alert
                         daily counters ──┐
                                     BridgeDisplay ── RouterBridge ──────────────>
                                     EventLog ── events.csv (rebuilt on start)
                                     State ── WebUI brick :7000 /api/state + index.html  <── phone on the hotspot
```

The core package `suokuulo/` has no Arduino imports and runs the same on a
laptop with file or mic input. Only `applab/python/main.py` and the sketch are
board specific.

## Parts

| Part | Notes |
| --- | --- |
| Arduino UNO Q, 2 GB variant | Linux (Qualcomm) + MCU (STM32) on one board; 1.70 GB usable RAM |
| Arduino USB-C hub | stick-shaped, PD power input |
| Official Arduino power supply | powers the hub and board |
| USB microphone | model: TODO |
| Arduino Modulino Buzzer (ABX00108) | Qwiic cable to the board's Qwiic connector |

Measured power draw: TODO (W)

## Results

Laptop numbers (`scripts/evaluate.py` with the board's settings, one clip at a
time; full tables and the before/after comparison in `eval_results.md`):

| | before fixes | now |
| --- | --- | --- |
| bird clips confirmed (8 species, 81 clips) | 78 % | 88 % |
| seconds of audio to the first bird event (median) | - | 3 |
| golden plover confirmed on non-plover clips | 0 | 0 |
| birds under equal-level speech | - | 74 % |
| two species overlaid, both confirmed | - | 25 of 28 pairs |
| ESC-50 chainsaw / engine clips confirmed | 4 / 0 of 10 | 9 / 2 of 10 |
| machinery false alarms on 121 non-machinery clips | 0 | 0 |
| rfcx/frugalai field chainsaws (3 s clips) | 0 / 20 | 0 / 20 |

On the board (2026-11-14): 387 ms inference per window, phone playback 25 cm
from the mic confirmed curlew (69 %), crane (73 %) and wood sandpiper (82 %);
a golden plover recording was missed. Board RAM: the `[stats]` log line and the
dashboard footer show it; laptop measurement of the whole app: 238 MB RSS.

Weak spots: engines and short field chainsaw clips; the expected-activity
numbers are estimates until the device learns its own; most indicators are
summer migrants, so in winter health shows "Off season" and disturbance
monitoring carries on.

## Credits

- BirdNET (K. Lisa Yang Center for Conservation Bioacoustics, Cornell Lab of
  Ornithology, and Chemnitz University of Technology), model v2.4.
- birdnetlib (Joe Weiss), whose package ships the model files we load.
- Test recordings: Xeno-canto recordists, ESC-50 (Karol Piczak) and its
  Freesound contributors, Rainforest Connection (rfcx/frugalai). Every clip is
  listed with recordist, licence and URL in `credits.csv`.
- Arduino App Lab, app-bricks-py, Arduino_RouterBridge, Arduino_Modulino.

## Licence note

The BirdNET models are CC BY-NC-SA 4.0, and the test audio is non-commercial
too (Xeno-canto clips mostly CC BY-NC-SA, ESC-50 CC BY-NC 3.0, rfcx/frugalai
CC BY-NC 4.0). That is fine for a hackathon and for research. A commercial
version would train its own model on licensed recordings.
