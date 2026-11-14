# SuoKuulo

Bird-biodiversity monitor for restored Finnish peatlands, on the Arduino UNO Q.
A USB microphone listens in 3 s windows (one every 2 s), BirdNET v2.4 runs on
the board, indicator birds become a 0-100 soundscape health score, and an
hourly summary goes out as a 16-byte LoRa payload from the MCU, which also
watches that the analysis on the Linux side is alive. A local dashboard shows
the detail to anyone on the same network. No audio leaves the device.

## Why now: EU legal framework

- [Regulation (EU) 2024/1991](https://eur-lex.europa.eu/eli/reg/2024/1991/oj/eng)
  on nature restoration, in force since 18 August 2024: draft national
  restoration plans were due by 1 September 2026 (Art. 16), followed by
  monitoring (Art. 20) and reporting of progress (Art. 21). Peatlands are a
  core target.
- Drained peatlands in **agricultural** use (Art. 11(4)): 30 % restored by 2030
  (at least a quarter of it rewetted), 40 % by 2040, 50 % by 2050. Most Finnish
  drained peatlands are forestry-drained; rewetting them can count for up to
  40 % of that target.
- Natura 2000: every 6 years member states report bird species status
  ([Birds Directive](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02009L0147-20190626)
  Art. 12) and habitat status
  ([Habitats Directive](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:01992L0043-20130701)
  Art. 17). Birds Directive Annex I includes our golden plover, wood
  sandpiper, common crane, whooper swan and black grouse (subspecies *Tetrao
  tetrix tetrix* only). Priority peatland habitats in Habitats Directive
  Annex I: 7110 active raised bogs, 7310 aapa mires, 7320 palsa mires, 91D0
  bog woodland. Details in PROJECT_HUB.md.

SuoKuulo does not replace field surveys; it covers the sites and the days where no surveyor is present.

## How the score works

- **Health (0-100) counts indicator birds.** Over the last hour (10 min in the
  demo) it compares the species heard with what a healthy bog is expected to
  sound like at this season and time of day (`config/baseline.yaml`).
  - *Richness*: how much of the expected species list was heard, golden plover
    counting 3, the others 1.
  - *Activity*: for each expected species, minutes in which it was heard vs
    minutes expected, capped at 100 %. A minute counts once however often a
    bird calls, so one loud bird cannot inflate the score.
  - Health = 60 % richness + 40 % activity. 0-39 Poor, 40-69 Fair, 70-100 Good.
- **Baseline.** Starting estimates per season and part of day. After 3 days of
  `events.csv` the device learns its own: the median minutes per hour for each
  species at that hour of day.
  - Breeding (May-Jul): the 8 waders and open-bog birds.
  - Migration (Mar-Apr, Aug-Oct): the same plus whooper swan and spotted
    redshank.
  - Winter (Nov-Feb): only willow ptarmigan and black grouse, which call
    little. When fewer than 3 detection-minutes per hour are expected in all,
    health reads "Off season (low bird activity expected)" instead of a number.
- **Acoustic index (NDSI).** Per minute, sound energy at 2-8 kHz (birds,
  insects) against 1-2 kHz (engines, voices): -1 noise-dominated, +1
  nature-dominated. It needs no species, so it works all year. Shown on its
  own; it never changes health.

## Which brain does what

| Linux (QRB2210, Python in App Lab) | MCU (STM32U585, Zephyr sketch) |
| --- | --- |
| USB mic, 3 s windows, 1 kHz high-pass | LoRa payload: packs the hourly summary (16 bytes) |
| BirdNET v2.4, smoothing, health score | Watchdog: linux_down / heartbeat / recovered payloads |
| events.csv, daily counters, learned baseline | LED matrix: health number + TX icon |
| Dashboard (WebUI brick, port 7000) | Buzzer: one beep at startup |
| Bridge: `summary` hourly, `heartbeat` every 10 s | |

## Uplink payload

16 bytes, little-endian (`applab/sketch/payload.h`, decoder
`scripts/decode_payload.py`):

| bytes | field |
| --- | --- |
| 0 | version (high nibble), type (low): 1 summary, 2 linux_down, 3 heartbeat, 4 recovered |
| 1 | flags: 1 linux_ok, 2 off_season (no health number) |
| 2 | health 0-100, 255 = none |
| 3, 4 | richness %, activity % |
| 5-6 | species heard today, bit i = i-th indicator in `config/species.yaml` |
| 7-8 | detections today |
| 9-12 | MCU uptime, s |
| 13-14 | minutes since the last Linux heartbeat, 65535 = none since boot |
| 15 | sequence number |

The office reads three states: no payloads = device dead; `linux_down` or a
heartbeat without `linux_ok` = device alive, analysis down; summaries =
healthy (a low health is a quiet bog, not a fault). The MCU cannot reset the
Linux side (no line for it on the UNO Q), so it only reports.

No LoRa module is fitted yet: `radioSend()` in the sketch is the hook for an
SX1276/RFM95 driver; until then each payload is printed as hex on the MCU
serial and a TX block lights on the matrix for 3 s.

## Laptop setup

Python 3.10+ (tested with 3.12 and 3.13).

```sh
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
# or: python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Test audio (only needed for replay, demo and evaluation; git-ignored):

```sh
XC_API_KEY=...  .venv/bin/python scripts/fetch_bird_clips.py    # key: xeno-canto.org/account
.venv/bin/python scripts/fetch_noise_clips.py --speech 10       # ESC-50 background, LibriSpeech; no key
```

Run scripts from the repo root. Keys come from the environment; never commit them.

## Commands

| What | Command |
| --- | --- |
| Scripted run, no model, no audio | `.venv/bin/python run_laptop.py --mock` |
| Replay one file or folder | `.venv/bin/python run_laptop.py --input test_clips/golden_plover -v` |
| Replay at live speed with dashboard | `.venv/bin/python run_laptop.py --input test_clips --realtime` then open http://localhost:8000 |
| Demo (quiet, plover, snipe, crane, quiet) | `.venv/bin/python run_laptop.py --demo` |
| Same demo at full speed, health timeline | `.venv/bin/python scripts/simulate.py [--start 2026-06-10T05:00] [--web]` |
| Live laptop mic | `.venv/bin/python run_laptop.py --mic` (or `--mic arecord --device plughw:1,0`) |
| Unit tests | `.venv/bin/pytest -q` |
| Evaluation | `.venv/bin/python scripts/evaluate.py` writes `eval_results.md` and `.csv` (docstring: `--speech`, `--mixed`, `--set`, `--compare`, `--notes`) |
| Decode an uplink payload | `.venv/bin/python scripts/decode_payload.py <hex>` |
| Deploy to the board | `./deploy.sh [--restart]` (copies `applab/`, checks every file by sha256) |

## Config switches

`config/board.yaml` (field deployment) holds the detection settings;
`config/demo.yaml` includes it and sets the demo values (the board loads
`demo.yaml`, see `CONFIG` in `applab/python/main.py`); `config/laptop.yaml`
includes `demo.yaml` and replays files. Defaults are in `suokuulo/config.py`;
unknown keys fail at startup.

| Key | board / demo | Meaning |
| --- | --- | --- |
| `hop_s` | 2.0 | a 3 s window every 2 s (1 s overlap) |
| `hits_needed`, `hit_window`, `confirm_single` | 2, 2, 0.70 | confirm on 2 consecutive windows, or one window >= 0.70 |
| `indicator_hit`, `species_hit`, `species_single` | 0.50, plover 0.35, plover 0.85 | per-window bird thresholds |
| `cooldown_s` | 30 | per species; the first event is never delayed |
| `highpass_hz` | 1000 | high-pass before inference; 0 = off |
| `baseline_profile` | by month / `breeding` | season profile in `baseline.yaml` |
| `score_window_min` | 60 / 10 | health window |
| `richness_weight`, `activity_weight` | 0.6, 0.4 | health split |
| `learn_min_days`, `off_season_below` | 3, 3 | days before the baseline is learned; expected detection-minutes per hour under which health is "Off season" |
| `ndsi_anthro_hz`, `ndsi_bio_hz` | [1000, 2000], [2000, 8000] | acoustic index bands |
| `uplink_interval_s` | 3600 / 300 | summary to the MCU for the LoRa payload |
| `buzzer_startup` | true | the one startup beep |
| `silence_s` | 1800 | `silence` row in events.csv after 30 min without birds |
| `timezone`, `site_name` | Europe/Helsinki, demo name | days, hours, midnight reset; dashboard header |
| `verbose` | true on the board | raw detections per window in the log |
| `disturbance_enabled` | false | future work, see below; when off nothing about disturbance appears |
| `log_file`, `web_port` | `events.csv`, 7000 | outputs |

Species and exact BirdNET labels: `config/species.yaml`. Expected activity per
season and part of day: `config/baseline.yaml`.

## Board setup (Arduino UNO Q)

Hardware: UNO Q, official Arduino USB-C hub with PD power input on the official
Arduino power supply, USB microphone on the hub, Modulino Buzzer (ABX00108) on
the Qwiic connector.

1. Configure the board in Arduino App Lab once (board name, Wi-Fi, Linux
   password). Put your SSH key on it once from your own terminal:
   `ssh-copy-id arduino@<board-ip>`.
2. Flash `applab/buzzer_test` first (below) to prove the Qwiic wiring.
3. `./deploy.sh --restart` (symlinks become files, every file is checked by
   sha256 on the board; `BOARD=arduino@<ip> ./deploy.sh` for another address).
4. Success looks like:
   - one beep, then the health number on the matrix (0 until a bird is heard);
   - a TX block on the matrix for 3 s at start and with every uplink;
   - in the app log (App Lab, or `ssh arduino@<ip> arduino-app-cli app logs user:suokuulo`):
     `[config] demo.yaml ...`, `[log] events.csv at ...`, `[mic] <device> at
     48000 Hz`, a `[stats]` line each minute (inference ms, RAM);
   - on the MCU serial (App Lab, the app's Serial Monitor):
     `[uplink] no radio, payload 11...` lines, which `scripts/decode_payload.py` decodes;
   - the dashboard on `http://<board-ip>:7000/`.

To test the board without the mic, set `source: file` and `input: <folder of
clips copied to the board>`.

### Buzzer test

```sh
tar -chf - -C applab/buzzer_test . | \
  ssh arduino@<board>.local 'mkdir -p ~/ArduinoApps/suokuulo-buzzer-test && tar -xf - -C ~/ArduinoApps/suokuulo-buzzer-test'
```

Then App Lab, My Apps, SuoKuulo Buzzer Test, Run. You should hear, on repeat:
beep, chirp, two chirps, a 2 s two-tone siren, 1.5 s of silence. The console
prints `buzzer found` and each sound name. An X on the matrix means the buzzer
was not found on `Wire1`: reseat the Qwiic cable.

## Known limits

- Evaluation (`eval_results.md`, laptop): 88 % of bird clips confirmed, median
  3 s of audio to the first event; the four seasonal species 4-5 of 5 clips.
- A golden plover played from a phone 25 cm from the board's mic was missed,
  while the same file scores 0.81-0.98 on the laptop: check the mic path with
  `verbose: true`.
- `baseline.yaml` numbers are estimates until the device has learned its own.
- No LoRa module is fitted: payloads are printed, not sent.
- Power: the Linux side cannot sleep, so the board draws power all the time
  (see PROJECT_HUB.md).

## Future work: disturbance detection

The code path for people, machinery and gunshots is kept behind
`disturbance_enabled: false`. BirdNET's machinery labels were too weak in
evaluation (ESC-50 chainsaw 9/10 but engines 2/10, field chainsaw clips 0/20,
human voice 2/10) and false alarms would dilute a biodiversity product. A
dedicated model (YAMNet beside BirdNET, same TFLite runtime) is the likely way
back.

## Licences

Code: this repo. BirdNET models: CC BY-NC-SA 4.0. Test audio: see `credits.csv`
(Xeno-canto per-recording licences, ESC-50 CC BY-NC 3.0, rfcx/frugalai
CC BY-NC 4.0, LibriSpeech CC BY 4.0).
