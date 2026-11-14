# SuoKuulo

Bioacoustic monitor for restored Finnish peatlands. A USB microphone listens in
3 s windows (one every 2 s), BirdNET v2.4 runs on the device, indicator birds
become a 0-100 soundscape health score, disturbance (people, machinery,
gunshots) is reported separately, the MCU shows health on the LED matrix and
sounds the Modulino Buzzer, and a local dashboard serves it all. No audio or
data leaves the device.

## How the score works

- **Health (0-100) counts birds only.** Over the last hour (10 min in the
  demo) it compares the indicator species heard with what a healthy bog is
  expected to sound like at this season and time of day (`config/baseline.yaml`).
  - *Richness*: how much of the expected species list was heard, golden plover
    counting 3, the others 1.
  - *Activity*: for each expected species, minutes in which it was heard vs
    minutes expected, capped at 100 %. A minute counts once however often a
    bird calls, so one loud bird cannot inflate the score.
  - Health = 60 % richness + 40 % activity. 0-39 Poor, 40-69 Fair, 70-100 Good.
    No species expected (winter) shows "Off season".
- **Baseline.** Starting estimates per season (breeding May-Jul, migration
  Mar-Apr and Aug-Oct, winter) and part of day. After 3 days of `events.csv`
  the device learns its own: the median minutes per hour for each species at
  that hour of day.
- **Disturbance never lowers health.** People ("People nearby"), machinery
  (engine, power tools) and gunshots are counted per day, and the minutes
  disturbed in the last hour give a Low/Moderate/High pressure level. Only
  machinery and gunshots raise the alert (matrix corner + siren).

## Laptop setup

Python 3.10+ (tested with 3.12 and 3.13).

```sh
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt
# or: python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Test audio (only needed for replay, demo and evaluation; git-ignored):

```sh
XC_API_KEY=...  .venv/bin/python scripts/fetch_bird_clips.py    # key: xeno-canto.org/account
.venv/bin/python scripts/fetch_noise_clips.py                   # ESC-50, no key
HF_TOKEN=hf_... .venv/bin/python scripts/fetch_noise_clips.py --frugalai 20   # optional, gated dataset
```

Run scripts from the repo root. Keys come from the environment; never commit them.

## Commands

| What | Command |
| --- | --- |
| Scripted run, no model, no audio | `.venv/bin/python run_laptop.py --mock` |
| Replay one file or folder | `.venv/bin/python run_laptop.py --input test_clips/golden_plover -v` |
| Replay at live speed with dashboard | `.venv/bin/python run_laptop.py --input test_clips --realtime` then open http://localhost:8000 |
| Demo (quiet, plover, people, snipe, crane, chainsaw, quiet) | `.venv/bin/python run_laptop.py --demo` |
| Same demo at full speed, health timeline | `.venv/bin/python scripts/simulate.py [--start 2026-06-10T05:00] [--web]` |
| Live laptop mic | `.venv/bin/python run_laptop.py --mic` (or `--mic arecord --device plughw:1,0`) |
| Unit tests | `.venv/bin/pytest -q` |
| Evaluation | `.venv/bin/python scripts/evaluate.py` writes `eval_results.md` and `.csv` (see its docstring for `--speech`, `--mixed`, `--set`, `--compare`) |
| Deploy to the board | `./deploy.sh [--restart]` (copies `applab/`, checks every file by sha256) |
| BirdNET label check | `.venv/bin/python scripts/list_labels.py` |

Flags: `-v` prints raw detections per window, `--mute` turns off chirps and siren,
`--no-web` skips the dashboard, `--loop` loops replay. Events append to `events.csv`.

## Config switches

`config/board.yaml` (field deployment) holds the detection settings;
`config/demo.yaml` includes it and sets the demo scoring (the board loads
`demo.yaml`, see `CONFIG` in `applab/python/main.py`); `config/laptop.yaml`
includes `demo.yaml` and replays files. Defaults are in `suokuulo/config.py`;
unknown keys fail at startup.

| Key | board / demo | Meaning |
| --- | --- | --- |
| `hop_s` | 2.0 | a 3 s window every 2 s (1 s overlap) |
| `hits_needed`, `hit_window`, `confirm_single` | 2, 2, 0.70 | confirm on 2 consecutive windows, or one window >= 0.70 |
| `indicator_hit`, `species_hit`, `species_single` | 0.50, plover 0.35, plover 0.85 | per-window bird thresholds |
| `any_disturbance_hit`, `disturbance_hit` | 0.20, 0.35 | engine/power tools/gun pooled into one signal; human voice alone |
| `cooldown_s` | 30 | per label (and for the pooled signal); the first event is never delayed |
| `highpass_hz` | 1000 | high-pass before inference; 0 = off |
| `baseline_profile` | by month / `breeding` | season profile in `baseline.yaml` |
| `score_window_min` | 60 / 10 | health window |
| `richness_weight`, `activity_weight` | 0.6, 0.4 | health split |
| `learn_min_days` | 3 | days of history before the baseline is learned |
| `pressure_minutes` | [5, 15] | disturbed minutes in the last hour for Moderate, High |
| `alarm_clear_s`, `silence_s` | 20, 1800 | alert clears 20 s after the last machinery hit; silence alert after 30 min without birds |
| `buzzer_startup`, `buzzer_alerts` | true, false / true | startup beep; bird chirps + machinery siren |
| `timezone`, `site_name` | Europe/Helsinki, demo name | days, hours, midnight reset; dashboard header |
| `verbose` | true on the board | raw detections per window in the log |
| `log_file`, `web_port` | `events.csv`, 7000 | outputs |

Species, BirdNET labels and disturbance groups: `config/species.yaml`.
Expected activity per season and part of day: `config/baseline.yaml`.

## Board setup (Arduino UNO Q)

Hardware: UNO Q, official Arduino USB-C hub with PD power input on the official
Arduino power supply, USB microphone on the hub, Modulino Buzzer (ABX00108) on
the Qwiic connector.

1. Configure the board in Arduino App Lab once (board name, Wi-Fi, Linux
   password; the password is needed for SSH).
2. Flash `applab/buzzer_test` first (below) to prove the Qwiic wiring.
3. Copy the app with `./deploy.sh` (symlinks become files, every file is
   checked by sha256 on the board, `--restart` restarts the app;
   `BOARD=arduino@<ip> ./deploy.sh` for another address).
4. In App Lab open My Apps, SuoKuulo, Run. The first run compiles the sketch,
   installs `python/requirements.txt` and needs internet once. After that
   nothing goes online.
5. Success looks like: one beep when the app is up, the health number on the
   matrix (0 until a bird is heard in the demo), the log printing
   `[config] demo.yaml ...`, `[log] events.csv at ...`, `[mic] <device> at
   48000 Hz`, a `[stats]` line each minute (inference ms, RAM), and the
   dashboard on `http://<board-ip>:7000/`.

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
  3 s of audio to the first event; ESC-50 chainsaws 9/10, engines 2/10, 0 false
  alarms on 121 non-machinery clips. rfcx/frugalai chainsaws (3 s, one
  window) 0/20.
- Human vocal is confirmed on only 2 of 10 LibriSpeech clips: "People nearby"
  undercounts quiet read speech.
- A golden plover played from a phone 25 cm from the board's mic was missed,
  while the same file scores 0.81-0.98 on the laptop: check the mic path with
  `verbose: true`.
- `baseline.yaml` numbers are estimates until the device has learned its own.
- The sketch is compiled by App Lab on the board, not here.

## Plan B for machinery: YAMNet

If BirdNET keeps missing chainsaws and engines, add a second classifier:
`YamnetClassifier.classify(window, 48000)` resamples the same 3 s window to
16 kHz, runs the YAMNet TFLite model (AudioSet classes Chainsaw, Engine,
Vehicle, ...) with the same ai-edge-litert runtime, and returns `Detection`s
with `kind="disturbance"`. A `CombinedClassifier` concatenates BirdNET and
YAMNet results, so the Smoother, score and display need no change.

## Licences

Code: this repo. BirdNET models: CC BY-NC-SA 4.0. Test audio: see `credits.csv`
(Xeno-canto per-recording licences, ESC-50 CC BY-NC 3.0, rfcx/frugalai CC BY-NC 4.0).
