# WuWa Screen Translation Tool

An offline Windows tool that captures the screen, reads the English text of
*Wuthering Waves* with OCR, translates it to Vietnamese with a local model and
draws the translation in a transparent overlay placed exactly over the
original text.

No online API, no API key, no cost. After the first model download the tool
runs completely offline.

---

## 1. Install

Requirements: Windows 10/11, Python **3.11** (do not use 3.13, some OCR wheels
are unstable there).

```powershell
cd D:\translate_wuwa
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### First-time model download (needs internet, once)

The OCR models ship with `rapidocr-onnxruntime`. The translation models have to
be downloaded once:

```powershell
# Argos Translate package (en -> vi)
python -c "import argostranslate.package as p; p.update_package_index(); pkg=[x for x in p.get_available_packages() if x.from_code=='en' and x.to_code=='vi'][0]; p.install_from_path(pkg.download())"

# Helsinki-NLP opus-mt-en-vi (MarianMT)
python -c "from transformers import MarianMTModel, MarianTokenizer; M='Helsinki-NLP/opus-mt-en-vi'; MarianTokenizer.from_pretrained(M); MarianMTModel.from_pretrained(M)"
```

After that you can disconnect the network: the tool still translates. The
Argos engine uses Stanza as its sentence splitter; `src/offline.py` patches it
so it never tries to reach GitHub for `resources.json` - the model files are
already bundled inside the Argos package. `tests/test_offline.py` proves it by
blocking every socket connection.

To check the offline behaviour yourself:

```powershell
python -m pytest tests\test_offline.py -q
```

---

## 2. Run

```powershell
.\.venv\Scripts\activate
python -m src.main
```

The overlay appears immediately and shows `OFF` in the top-left corner.

### The F8 hotkey

| Key | Action |
| --- | --- |
| `F8` | Toggle the translation **ON / OFF** |

* Press **F8 once** -> a new session starts, a new history file is created and
  every new text that appears on screen is translated automatically. No
  further key presses are needed.
* Press **F8 again** -> capture / OCR / translation stop, all overlays are
  cleared and the history file is closed.

`F8` does not conflict with the WuWa default keys (1-5 / Q / E / R / F / Tab /
Esc).

The state is printed to the log and shown on the overlay
(`TRANSLATING` / `OFF`).

---

## 3. Session history

Every session writes one text file into `data/sessions/`:

```
data/sessions/2026-11-20_16-30-05.txt
```

The file name is the session start time (`YYYY-MM-DD_HH-MM-SS.txt`). Each
translated block is appended exactly once, in this format:

```
[16:30:07] Jiyan: Vung dat Tacet dang lan rong khap mien bac.
  EN: The Tacet Field is spreading across the northern plains.

[16:30:12] Ban da nhan duoc mot Waveplate moi cho Rover.
  EN: You obtained a new Waveplate for your Rover.
```

Entries are separated by one blank line. A block without a speaker name has
only the translation on the first line.

---

## 4. Test on the sample images

The fixtures in `tests/fixtures/` are drawn from scratch with Pillow (no
copyrighted game screenshots):

| File | Size | Content |
| --- | --- | --- |
| `sample_a_dialogue.png` | 1920x1080 | 3-line dialogue with a speaker name above it |
| `sample_b_quest.png` | 1920x1080 | quest text + skill description |
| `sample_c_menu.png` | 1920x1080 | menu entries + damage numbers (number filtering) |
| `sample_a_dialogue_2560x1600.png` | 2560x1600 | the dialogue image scaled up (resolution test) |
| `sample_d_roi_base.png` | 1920x1080 | the base frame of the ROI test (before the dialogue changes) |
| `sample_d_roi_changed.png` | 1920x1080 | the same frame with one changed dialogue line (ROI test) |
| `sample_e_long.png` | 1920x1080 | a long text that has to be wrapped inside the bbox |
| `sample_f_reward.png` | 1920x1080 | `Reward: 12000` (number protection test) |
| `sample_g_ui_menu.png` | 1920x1080 | the UI labels `Quest` / `Skill` / `Inventory` / `Settings` |

Regenerate them with:

```powershell
python scripts\make_fixtures.py
```

Run the test suite:

```powershell
python -m pytest -q
```

Run the benchmark (real measured numbers, never hardcoded):

```powershell
python scripts\bench.py
```

It prints the capture backend comparison, the translation engine comparison
and the pipeline stage table for a cold run (empty cache) and a warm run
(100% cache hits).

---

## 5. Test on the real game

1. Start the game in borderless windowed mode.
2. Start the tool: `python -m src.main`.
3. Press **F8** once. The overlay shows `TRANSLATING`.
4. Advance the dialogue. The Vietnamese text appears over the English text.
5. Press **F8** again to stop and clear the overlay.
6. Read the history file in `data/sessions/`.

The game must not stutter: capture, OCR and translation run in a worker
thread, the UI thread only paints the overlay.

---

## 6. Configuration

`config/config.yaml`:

| Key | Meaning |
| --- | --- |
| `poll_ms` | capture interval in ms (default 200) |
| `diff_threshold` | frame-difference threshold, the fraction of changed pixels |
| `debounce_ms` | how long a text block must stay still before it is translated |
| `ocr_conf_min` | minimum OCR confidence (0.5) |
| `group_gap_px` | vertical gap under which two lines belong to the same block |
| `speaker_gap_px` | vertical gap under which a line above is a speaker name |
| `translation.engine` | `argos` or `marian` |
| `translation.device` | `cpu` (default, the game owns the GPU) or `cuda` |
| `translation.split_sentences` | translate every sentence of a block separately (`true`) |
| `translation.sentence_splitter` | `regex` (fast, default) or `stanza` |
| `translation.skip_ui_labels` | keep a menu header in English instead of translating it |
| `capture.backend` | `auto` (dxcam first, mss as fallback), `dxcam` or `mss` |
| `overlay.*` | font, colours, transparency of the overlay |
| `overlay.background_alpha` | 255 = fully opaque, the English text is completely hidden |
| `overlay.max_height_growth` | how much the box may grow vertically before the font is reduced |

### ROI (P2)

| Key | Meaning |
| --- | --- |
| `roi.enabled` | OCR only the changed region of the frame (`true`) |
| `roi.padding_px` | extra margin around the changed region (reference value at 1080p) |
| `roi.min_area` | below this area (px) the whole frame is OCR'd instead |
| `roi.full_frame_threshold` | if the ROI covers more than this fraction of the screen, OCR the whole frame |
| `roi.full_refresh_ms` | full-frame refresh interval in ms (2000) |
| `roi.full_refresh_frames` | full-frame refresh interval in frames (10) |
| `roi.det_limit_side_len` | max side of the ROI crop for the detector (2000 = native resolution) |
| `roi.det_limit_type` | `max` (never upscale a crop) |

### Speakers (P2)

| Key | Meaning |
| --- | --- |
| `speaker.enabled` | use the blacklist and the roster (`true`) |
| `speaker.ui_labels_path` | `config/ui_labels.yaml` - the labels that are never a speaker |
| `speaker.roster_path` | `config/roster.yaml` - the playable characters and the NPCs |

`config/glossary.yaml` holds the WuWa terms that must stay in English (Rover,
Resonator, Tacet Field, Waveplate, ...). The terms are replaced by a
placeholder before the translation and restored afterwards.

---

## 6. What P2 added

### ROI OCR (item A)

The frame differencing already computes a diff mask. P2 turns it into a
bounding box: the changed region is cropped out, OCR'd **at the native
resolution** (a second OCR engine with `det_limit_type=max`, so a small crop
is never upscaled to 736 px) and the coordinates are shifted back to the
screen.

The blocks outside the ROI are kept from the last known state, so the
unchanged dialogue stays on screen. Every 2 s (or every 10 frames) a
full-frame OCR runs and prunes the blocks whose source text is gone. A block
is never removed just because it was outside the current ROI.

Measured on this machine (1920x1080, one changed dialogue line):

| Path | OCR | End to end |
| --- | --- | --- |
| Full frame | 819 ms | 822 ms |
| **ROI crop** | **99 ms** | **143 ms** |

### Overlay wrapping (item B)

The Vietnamese text is wrapped inside the original bbox width. When it does
not fit, the bbox grows downward and the font size stays the same (the font is
only shrunk if the growth hits `overlay.max_height_growth`). The background is
fully opaque by default (`overlay.background_alpha: 255`), so the English text
is really hidden.

### Sentence translation and number protection (item C)

A block is split into sentences and each sentence is translated on its own,
which makes the Argos model much more accurate. Before the translation every
number, percentage and decimal is replaced by a placeholder (`XNUM0X`,
`XPCT0X`) and restored exactly afterwards. A digit-alignment check compares
the digits of the source and of the output and repairs a mismatch.

Without this, `Reward: 12000` was translated to `Phần thưởng: 2000` - the
Argos tokenizer drops the leading digits. With it, the value survives.

### Speaker detector (item D)

`config/ui_labels.yaml` is a blacklist of the UI labels (`Quest`, `Skill`,
`Inventory`, `Settings`, ...) and `config/roster.yaml` lists the playable
characters and the NPCs. A line is a speaker only when it is on the roster or
when it is a `Name:` prefix that is not blacklisted. `Jiyan` and `Rover` stay
speakers, `Quest` and `Skill` never are.

### UI labels stay in English (extra)

A block whose whole text is a UI label is not translated at all, so the
player finds "Quest" and "Inventory" in the menu.

### OCR model experiment (item E)

The PP-OCRv4 mobile detection model and an int8-quantized recognition model
were benchmarked against the P1 defaults. **Both are slower on the ROI crop
and neither is more accurate**, so the P1 models stay the default. The
numbers are in `REPORT.md`.

---

## 7. Push to GitHub

```powershell
git add .
git commit -m "P2: ROI OCR, overlay wrapping, sentence translation, speaker detector"
git push -u origin main
```

Remote: <https://github.com/TranDaiHiep2006/translate_wuwa>

### If the repository does not exist yet

Create it first (the GitHub web UI: *New repository*, name
`translate_wuwa`, **do not** add a README) and then push:

```powershell
git remote add origin https://github.com/TranDaiHiep2006/translate_wuwa
git push -u origin main
```

If the push fails because of the credentials, use a personal access token
(HTTPS) or `gh auth login`.

---

## 8. Project layout

```
src/
  main.py       entry point (worker thread + UI thread + F8 hotkey)
  config.py     YAML configuration
  capture.py    mss / dxcam screen capture, resolution auto-detection
  change.py     frame differencing
  roi.py        ROI computation + block merging (P2)
  ocr.py        RapidOCR wrapper, the full-frame and the ROI engine
  filter.py     drops numbers / low confidence / short lines
  grouping.py   line grouping + speaker name detection
  speakers.py   UI label blacklist + roster (P2)
  sentences.py  sentence splitting + number placeholder protection (P2)
  wrapping.py   greedy word wrapping for the overlay (P2)
  cache.py      SQLite translation cache + history table
  glossary.py   placeholder protection of the WuWa terms
  translator.py Argos / MarianMT engines behind one interface
  overlay.py    transparent, click-through, always-on-top PyQt6 window
  session.py    session history file
  pipeline.py   connects the stages and measures the time of each stage
scripts/
  make_fixtures.py  generates the sample images
  bench.py          prints the real benchmark tables
  bench_translation.py  compares Argos and MarianMT
  render_overlay_demo.py  renders data/overlay_demo.png
  make_session_demo.py   writes a real session history file
tests/          pytest suite + fixtures
config/         config.yaml, glossary.yaml, ui_labels.yaml, roster.yaml
```

---

## 9. Safety

* The tool only takes screenshots and draws a **separate** overlay window.
* It never reads the game memory, never injects anything, never modifies the
  game files and never presses keys.
* It never calls an online translation API.
