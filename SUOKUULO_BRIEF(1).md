# SuoKuulo: software brief for Claude

Read this whole file before writing any code. Then work through the steps in
order. Each step has an acceptance check: do not start the next step until the
check passes, and paste the command output that proves it in your report.

## 1. Context

We are at Junction 2026, Arduino challenge "The Green European Renaissance":
Edge AI on the Arduino UNO Q solving a local, green problem with no dependence
on cloud services. We have under 24 hours.

SuoKuulo ("suo" = bog, "kuulo" = hearing) is a bioacoustic monitor for restored
Finnish peatlands. A USB microphone on the UNO Q listens in 3 second windows.
BirdNET runs on the board's Linux side. A script turns detections into a 0-100
"soundscape health" score and alerts. The MCU shows the state on the onboard
8x13 LED matrix. The board serves a local web dashboard. No audio or data
leaves the device.

The human is away collecting hardware. Right now you have NO board and NO
microphone. Everything must run on this laptop today, and move to the UNO Q
later by changing config and one thin entrypoint, nothing else.

## 2. Hard rules

1. Laptop first. Every hardware touchpoint sits behind an interface that has a
   working mock.
2. The core package `suokuulo/` must not import anything Arduino specific.
   Arduino imports live only in `applab/`.
3. No network calls at runtime. Downloads happen only in `scripts/`.
4. Do not guess hardware APIs. Section 9 lists what I believe is true and must
   be verified in the official docs. If you cannot verify something, write the
   code behind a clearly marked `TODO(hardware)` and list it in your report.
5. Never invent results. Accuracy numbers, timings and "it works" claims must
   come from commands you actually ran.
6. Reference only: the Hackster project "Eco-Sentinel: AI-Powered Urban Bird
   Conservation" ran BirdNET v2.4 on a UNO Q. Read it for approach. Its licence
   is CC BY-NC-ND, so do not copy code from it.
7. Python 3.10+. Minimal dependencies (the board is arm64 Debian, 2-4 GB RAM).
   Pin versions in `requirements.txt`.
8. Commit after every step with a message naming the step.
9. If blocked for more than 20 minutes on one thing, stop, write down what you
   tried, pick the fallback named in that step, and move on.

## 3. Repo layout

```
suokuulo/
  __init__.py
  config.py          # dataclass config + YAML loader
  audio.py           # AudioSource, FileSource, MicSource
  classifier.py      # Classifier, BirdNetClassifier, MockClassifier
  detection.py       # Smoother (2-of-3 rule, cooldown)
  scoring.py         # ScoreEngine, alerts
  display.py         # Display, ConsoleDisplay
  eventlog.py        # CSV logger
  state.py           # thread-safe shared state for the dashboard
  pipeline.py        # main loop wiring everything
  web/
    server.py        # tiny HTTP server, JSON endpoint
    static/index.html  # single page, no external assets
run_laptop.py        # entrypoint: laptop
applab/              # entrypoint: UNO Q App Lab app (see section 9)
  app.yaml
  python/main.py
  python/requirements.txt
  sketch/sketch.ino
  sketch/sketch.yaml
scripts/
  fetch_bird_clips.py
  fetch_noise_clips.py
  evaluate.py
  list_labels.py
config/
  laptop.yaml
  board.yaml
  species.yaml
tests/
test_clips/<label>/*.wav      # git-ignored
credits.csv
README.md
PROJECT_HUB.md
```

## 4. Interfaces (exact shapes)

```python
# audio.py
class AudioSource(Protocol):
    sample_rate: int                       # always 48000
    def windows(self) -> Iterator[np.ndarray]: ...
    # yields float32 mono arrays of exactly 144000 samples (3.0 s at 48 kHz)

# classifier.py
@dataclass
class Detection:
    label: str          # our internal id, e.g. "golden_plover", "engine"
    kind: str           # "indicator" | "disturbance"
    confidence: float   # 0..1

class Classifier(Protocol):
    def classify(self, window: np.ndarray, sample_rate: int) -> list[Detection]: ...

# display.py
class Display(Protocol):
    def show_score(self, score: int) -> None: ...        # 0..100
    def show_bird(self, species_index: int) -> None: ... # index into species.yaml
    def alarm(self, on: bool) -> None: ...
```

`FileSource(folder_or_file, loop=False, realtime=False)`: reads WAV/MP3/OGG,
resamples to 48 kHz mono, cuts into 3 s windows, zero-pads the last one. With
`realtime=True` it sleeps 3 s between windows so demos behave like live audio.

`MicSource(device=None)`: live capture at 48 kHz mono. Implement with
`sounddevice`. Add a second implementation that shells out to
`arecord -f S16_LE -r 48000 -c 1` as a fallback, selectable in config, because
PortAudio may not be available on the board.

## 5. BirdNET specifics (these matter, get them right)

- Use `birdnetlib` (`Analyzer`, and `RecordingBuffer` for in-memory arrays so
  we never write temp files per window). Runtime: `tflite-runtime` if it
  installs, otherwise `tensorflow`. If neither installs on the laptop within
  20 minutes, use the ONNX route and say so.
- BirdNET v2.4 expects 48 kHz audio in 3 s chunks.
- DO NOT pass `lat`, `lon` or `date` to BirdNET. It is November and the
  location filter would remove every migratory species we care about. Filter
  by species list instead.
- Labels look like `Scientific name_Common Name`. Run `scripts/list_labels.py`
  first: it must print the exact label strings for every species in section 6
  and every non-bird label in the model. Build `config/species.yaml` from that
  real output, not from memory.
- Any custom species list must include the disturbance labels too, or they
  will be filtered out.
- Set BirdNET's own `min_conf` low (0.1) and apply our thresholds ourselves in
  `detection.py`, so thresholds are tunable without touching the model code.
- Load the model once at startup. Print model load time and mean inference
  time per window over 20 windows.

## 6. Species and labels

Indicators (id, scientific name, weight):

| id | scientific name | weight |
| --- | --- | --- |
| golden_plover | Pluvialis apricaria | 3 |
| wood_sandpiper | Tringa glareola | 1 |
| common_snipe | Gallinago gallinago | 1 |
| curlew | Numenius arquata | 1 |
| whimbrel | Numenius phaeopus | 1 |
| meadow_pipit | Anthus pratensis | 1 |
| yellow_wagtail | Motacilla flava | 1 |
| common_crane | Grus grus | 1 |

Disturbance: I expect BirdNET v2.4 to contain non-bird labels such as
`Engine`, `Power tools`, `Gun`, `Human vocal`. Confirm with `list_labels.py`.
Map whichever exist to ids `engine`, `power_tools`, `gun`, `human_voice`.
If none exist, stop and report: the fallback is a second tiny classifier, and
the human decides.

## 7. Detection, score and alerts (exact rules, all numbers in config)

Detection smoothing, per label:
- A window is a "hit" if confidence >= 0.50 for indicators, >= 0.35 for
  disturbance.
- A label is confirmed when it has 2 hits in the last 3 windows.
- After confirmation, that label has a 30 s cooldown before it can confirm
  again. Each confirmation is one event.

Score, recomputed after every window:

```
bonus   = min(50, 10 * sum(weight of each DISTINCT indicator species
                           confirmed in the last 600 s))
penalty = min(50, 15 * number of disturbance events in the last 600 s)
score   = clamp(50 + bonus - penalty, 0, 100)
```

Alerts:
- `disturbance`: raised on any disturbance event. Calls `alarm(True)`. Clears
  (`alarm(False)`) after 20 s with no further disturbance hit.
- `silence` (lowest priority, skip if short on time): raised when no label of
  any kind has been confirmed for 30 minutes.

Display calls: `show_bird(i)` on each indicator event, `show_score(score)`
whenever the score changes, `alarm` as above.

Use an injectable clock (`now: Callable[[], float]`) in `detection.py` and
`scoring.py` so tests run instantly without sleeping.

## 8. Build steps with acceptance checks

1. **Skeleton on mocks.** Config loader, interfaces, `MockClassifier` (scripted
   list of detections per window), `ConsoleDisplay`, pipeline loop.
   Check: `python run_laptop.py --config config/laptop.yaml --mock` prints a
   scripted run where score moves and an alarm fires.
2. **Labels.** `scripts/list_labels.py`. Check: prints the 8 indicator labels
   and the non-bird labels found. Write `config/species.yaml`.
3. **BirdNET on files.** `BirdNetClassifier` + `FileSource`.
   Check: one real golden plover clip gives `golden_plover` as top indicator.
   Print inference time per window.
4. **Test audio.** `scripts/fetch_bird_clips.py`: about 10 clips per species
   from Xeno-canto into `test_clips/<id>/`, quality A or B, under 60 s each
   where possible, writing recordist, licence and URL to `credits.csv`. Check
   the current Xeno-canto API docs first. If it needs an API key, STOP and ask
   the human for one. `scripts/fetch_noise_clips.py`: chainsaw and engine clips
   from the ESC-50 dataset on GitHub (karolpiczak/ESC-50, CC BY-NC), into
   `test_clips/engine/` and `test_clips/power_tools/`, credited in the CSV.
5. **Detection + scoring** per section 7, with unit tests covering: 2-of-3
   rule, cooldown, distinct species counting, bonus cap, penalty cap, clamp,
   alarm raise and clear, 600 s expiry. Check: `pytest -q` all green.
6. **Event log.** CSV with columns
   `iso_time,label,kind,confidence,score,alert`. Append only, flushed per row.
7. **Dashboard.** HTTP server on port 8000 using the standard library or
   Flask. `GET /api/state` returns:
   ```json
   {"score": 72, "alarm": false,
    "recent": [{"time": "...", "label": "golden_plover", "kind": "indicator",
                "confidence": 0.81}],
    "alerts": [{"time": "...", "type": "disturbance", "label": "engine"}],
    "species_heard_10min": ["golden_plover", "common_snipe"],
    "uptime_s": 1234, "inference_ms": 850}
   ```
   `static/index.html` polls every second. Big score number with a colour
   band (0-39 red, 40-69 amber, 70-100 green), list of recent detections,
   alert log, a small "offline, on-device" badge. Inline CSS and JS only, no
   CDNs, no web fonts. Must be readable from 3 metres on a laptop screen.
   Check: page updates live during a replay run.
8. **Live mic on laptop.** `MicSource`. Check: playing a clip from a phone
   next to the laptop mic produces a confirmed detection. If there is no mic
   available to you, implement it, mark it untested, and say so.
9. **Demo replay mode.** `python run_laptop.py --demo`: scripted sequence with
   `realtime=True`: 30 s background, golden plover, snipe, crane, then
   chainsaw. Score should rise then drop, alarm should fire.
10. **Evaluation.** `scripts/evaluate.py` runs every clip in `test_clips/`,
    counts a clip as a hit if its label is confirmed at least once, and writes
    `eval_results.md` (table: label, clips, hits, misses, hit rate) plus a
    CSV. Report the real numbers, whatever they are.
11. **Board entrypoint.** `applab/` per section 9: `BridgeDisplay`, sketch,
    app.yaml. This cannot be run without the board, so keep it small, readable
    and fully marked with `TODO(hardware)` where unverified.
12. **Docs.** `README.md` (laptop setup, board setup, config switches, demo
    commands, known limits) and `PROJECT_HUB.md` (story, how it works, parts
    list, architecture diagram in text, credits, licence note: BirdNET models
    are CC BY-NC-SA 4.0, a commercial version would train its own model).

Priority if time runs out: steps 1-5, 7, 9, 11 are essential. 6, 8, 10, 12
come next. The silence alert is last.

## 9. UNO Q facts to VERIFY before writing `applab/`

I believe the following, from memory and from other people's projects. Check
each against docs.arduino.cc (UNO Q and App Lab sections) and the official
`arduino/app-bricks-examples` repo. Correct anything that is wrong.

- An App Lab app has `app.yaml`, `python/main.py`, optional
  `python/requirements.txt`, and `sketch/sketch.ino` with `sketch/sketch.yaml`.
- Linux side: `from arduino.app_utils import App, Bridge`, then
  `Bridge.call("function_name", arg)` and `App.run()`.
- MCU side: `#include "Arduino_RouterBridge.h"`, `Bridge.begin()` in `setup()`,
  and `Bridge.provide("function_name", handler)`.
- The onboard LED matrix is 8 rows by 13 columns, driven with
  `Arduino_LED_Matrix.h`.
- App Lab apps run in a container. System binaries such as `arecord` may not
  be visible inside it. Find out how the official audio bricks read the USB
  microphone (there may be a `Microphone` class in `arduino.app_peripherals`)
  and make `MicSource` able to use that on the board.
- Find out how an App Lab app exposes a web page (there is a Web UI brick) and
  whether a plain server on port 8000 is reachable from another machine. Pick
  whichever is documented and note the choice.
- Check whether `pip` packages in `python/requirements.txt` are installed
  automatically, and whether `tflite-runtime` has an arm64 wheel for the
  board's Python version.

Sketch requirements:
- `show_score(int)`: horizontal bar, 0-100 mapped to 0-13 lit columns on the
  bottom 2 rows.
- `show_bird(int)`: a bird icon on the top 6 rows for 3 seconds, then back to
  the score view.
- `alarm(bool)`: whole matrix blinks at 2 Hz while on; optional buzzer on a
  pin defined at the top of the file. Use `millis()`, never `delay()`.
- Define icons as 8x13 bitmaps at the top of the file with ASCII art comments.

## 10. Final report (write this when done or when you stop)

1. What works on the laptop, with the commands to see it.
2. Measured numbers: model load time, inference time per window, evaluation
   table.
3. Every `TODO(hardware)` with file and line, and what must be tested.
4. Exact step-by-step for the human when the board arrives: what to copy
   where, what to install, which config to use, which command to run first,
   and what output means success.
5. Anything in sections 5, 6 or 9 that turned out to be wrong.
