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
score, shows it on the LED matrix, sounds an alarm on machinery, and serves a
local dashboard. No audio and no data leave the device.

## How it works

1. A USB microphone records continuously. Every 3 s window (48 kHz mono) goes
   to BirdNET v2.4 on the UNO Q's Linux side.
2. BirdNET scores 6522 labels. We keep 8 bog indicator species and 4
   disturbance labels (Engine, Power tools, Gun, Human vocal), with no
   location or date filter (in November it would remove the migrants).
3. A label is confirmed when it hits in 2 of the last 3 windows, then cools
   down for 30 s.
4. Score = 50 + bonus - penalty, clamped to 0-100. Bonus: 10 x the weights of
   distinct indicator species heard in the last 10 min (golden plover counts
   3), capped at 50. Penalty: 15 per disturbance event in the last 10 min,
   capped at 50.
5. The MCU draws the score as a bar, flashes a bird icon on each indicator,
   chirps (twice for the golden plover), and blinks the matrix with a siren
   on disturbance.
6. Every event goes to an append-only CSV on the device.

## Architecture

```
 USB mic ──> [ Linux side (Python, App Lab container) ]                      [ MCU side (Zephyr sketch) ]
             AppLabMicSource ─ 3 s windows                                     LED matrix 8x13
                  │                                                              - score bar (bottom 2 rows)
             BirdNetClassifier (BirdNET v2.4 TFLite, ai-edge-litert)            - bird icon 3 s
                  │  Detection(label, kind, confidence)                          - 2 Hz blink on alarm
             Smoother (2 of 3, cooldown) ── events ──> ScoreEngine ──┐          Modulino Buzzer (Qwiic, Wire1)
                                                                     │            - chirp / double chirp
                                     BridgeDisplay ── RouterBridge ──┼──────────> - siren while alarm
                                     EventLog ── events.csv          │            - startup beep
                                     State ── WebUI brick :7000 ─────┘
                                                 /api/state + index.html  <── phone / laptop browser on the LAN
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

Laptop numbers (x86_64, `scripts/evaluate.py`, one clip at a time, details in
`eval_results.md`):

| label | source | clips | confirmed | hit rate |
| --- | --- | --- | --- | --- |
| common_crane | xeno-canto | 10 | 9 | 90% |
| common_snipe | xeno-canto | 10 | 10 | 100% |
| curlew | xeno-canto | 10 | 7 | 70% |
| golden_plover | xeno-canto | 10 | 6 | 60% |
| meadow_pipit | xeno-canto | 10 | 7 | 70% |
| whimbrel | xeno-canto | 10 | 6 | 60% |
| wood_sandpiper | xeno-canto | 10 | 7 | 70% |
| yellow_wagtail | xeno-canto | 10 | 10 | 100% |
| engine | ESC-50 | 10 | 0 | 0% |
| power_tools (chainsaw) | ESC-50 | 10 | 2 | 20% |
| power_tools (chainsaw) | rfcx/frugalai, 3 s clips | 20 | 0 | 0% (25% of windows hit some disturbance label) |
| background (negatives) | ESC-50 wind + frugalai environment | 30 | 0 false alarms | |

Inference: about 50-110 ms per 3 s window on the laptop. Board timing: TODO
(measure on the UNO Q). Memory: the whole board app (model, pipeline, web
server) peaks at 238 MB RSS, measured on the laptop; board RSS: TODO.

Bird detection works. BirdNET's machinery labels are the weak spot; plan B is
YAMNet beside BirdNET (README).

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
