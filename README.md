# SuoKuulo

Bioacoustic monitor for restored Finnish peatlands. A USB microphone listens in
3 s windows, BirdNET v2.4 runs on the device, detections become a 0-100
soundscape health score and alerts, the MCU shows it on the LED matrix and
sounds the Modulino Buzzer, and a local dashboard serves it. No audio or data
leaves the device.

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
| Demo (background, plover, snipe, crane, chainsaw, background) | `.venv/bin/python run_laptop.py --demo` |
| Live laptop mic | `.venv/bin/python run_laptop.py --mic` (or `--mic arecord --device plughw:1,0`) |
| Unit tests | `.venv/bin/pytest -q` |
| Evaluation | `.venv/bin/python scripts/evaluate.py` writes `eval_results.md` and `.csv` |
| BirdNET label check | `.venv/bin/python scripts/list_labels.py` |

Flags: `-v` prints raw detections per window, `--mute` silences the buzzer,
`--no-web` skips the dashboard, `--loop` loops replay. Events append to `events.csv`.

## Config switches

`config/laptop.yaml` and `config/board.yaml` override the defaults in
`suokuulo/config.py`. Unknown keys fail at startup.

| Key | Default | Meaning |
| --- | --- | --- |
| `source` | `file` | `file`, `mic` (sounddevice), `arecord`, `applab` (board only) |
| `input`, `loop`, `realtime` | `test_clips`, false, false | file replay |
| `device` | null | mic device (index, ALSA name, or App Lab `usb:1`) |
| `min_conf` | 0.1 | BirdNET's own floor; our thresholds sit above it |
| `indicator_hit`, `disturbance_hit` | 0.50, 0.35 | per-window hit thresholds |
| `hits_needed`, `hit_window`, `cooldown_s` | 2, 3, 30 | confirm 2 hits in 3 windows, then 30 s cooldown |
| `base_score`, `score_window_s` | 50, 600 | score baseline and memory |
| `bonus_per_weight`, `bonus_cap`, `penalty_per_event`, `penalty_cap` | 10, 50, 15, 50 | score rule |
| `alarm_clear_s`, `silence_s` | 20, 1800 | alarm clears 20 s after the last disturbance hit; silence alert after 30 min |
| `headline_species`, `mute` | `golden_plover`, false | double chirp species; buzzer off |
| `log_file`, `web_host`, `web_port` | `events.csv`, `0.0.0.0`, 8000 | outputs (board: WebUI on 7000) |
| `demo` | in `laptop.yaml` | `[path, max_windows]` playlist for `--demo` |

Species, weights and exact BirdNET labels: `config/species.yaml`. Its order is
the index `show_bird(i)` sends to the MCU.

## Board setup (Arduino UNO Q)

Hardware: UNO Q, official Arduino USB-C hub with PD power input on the official
Arduino power supply, USB microphone on the hub, Modulino Buzzer (ABX00108) on
the Qwiic connector.

1. Configure the board in Arduino App Lab once (board name, Wi-Fi, Linux
   password; the password is needed for SSH).
2. Flash `applab/buzzer_test` first (below) to prove the Qwiic wiring.
3. Copy the app. The repo uses symlinks, `tar -h` turns them into files:
   ```sh
   tar -chf - -C applab --exclude=buzzer_test . | \
     ssh arduino@<board>.local 'mkdir -p ~/ArduinoApps/suokuulo && tar -xf - -C ~/ArduinoApps/suokuulo'
   ```
4. In App Lab open My Apps, SuoKuulo, Run. The first run compiles the sketch,
   installs `python/requirements.txt` and needs internet once. After that
   nothing goes online.
5. Success looks like: a short beep when the Bridge is up, 7 of 13 columns lit on
   the bottom two matrix rows (score 50), the App Lab console printing
   `[birdnet] imports + model load ...` and `[mic] <device> at 48000 Hz`, and the
   dashboard on `http://<board>.local:7000/`.

Board config is `config/board.yaml`. To test the board without the mic, set
`source: file` and `input: <folder of clips copied to the board>`.

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

- Evaluation (`eval_results.md`): indicator birds 60-100 % of clips confirmed.
  BirdNET's machinery labels are weak: ESC-50 engine 0/10 clips, real-field
  rfcx/frugalai chainsaws 0 % on `Power tools` (25 % of windows on any
  disturbance label, mostly `Engine`). See plan B.
- rfcx/frugalai clips are 3 s, one window, so they cannot pass the 2-of-3 rule.
- Laptop-speaker to laptop-mic loopback did not confirm a golden plover (max
  0.18). Room/fan noise scored `Engine` 0.20-0.33, just under the 0.35
  threshold: watch for false alarms on the board.
- The sketches have not been compiled here (no `arduino-cli`); App Lab compiles
  them on first run.
- Everything marked `TODO(hardware)` in `applab/` is unverified on a real board.

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
