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

After that you can disconnect the network: the tool still translates.

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
| `capture.backend` | `auto` (dxcam first, mss as fallback), `dxcam` or `mss` |
| `overlay.*` | font, colours, transparency of the overlay |

`config/glossary.yaml` holds the WuWa terms that must stay in English (Rover,
Resonator, Tacet Field, Waveplate, ...). The terms are replaced by a
placeholder before the translation and restored afterwards.

---

## 7. Push to GitHub

```powershell
git add .
git commit -m "P1: skeleton + end-to-end pipeline"
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
  ocr.py        RapidOCR wrapper
  filter.py     drops numbers / low confidence / short lines
  grouping.py   line grouping + speaker name detection
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
tests/          pytest suite + fixtures
config/         config.yaml, glossary.yaml
```

---

## 9. Safety

* The tool only takes screenshots and draws a **separate** overlay window.
* It never reads the game memory, never injects anything, never modifies the
  game files and never presses keys.
* It never calls an online translation API.
