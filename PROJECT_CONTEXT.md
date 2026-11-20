# PROJECT_CONTEXT - WuWa Screen Translation Tool

This file is the **canonical context** for every later prompt of this project.
A later prompt only points at this file + the new work + the acceptance
criteria; it never pastes the whole codebase.

---

## 1. Goal

A Windows desktop tool that automatically:

1. captures the screen (borderless game),
2. OCRs the English text,
3. translates it to Vietnamese with a **fully offline** model (no API, no key,
   no cost),
4. draws the Vietnamese text in a transparent overlay **exactly over the
   original text**, at the original position.

Latency goal: **as low as possible, under 0.5 s** from the moment new text
appears until the translation is visible. If 0.5 s is not reached, the real
numbers are reported and the slowest stage is named. **Never claim 0.5 s
without measuring it.**

---

## 2. Hard constraints (never violate)

- **Python 3.11** (venv at `D:\translate_wuwa\.venv`). Not 3.13.
- **No online translation API** (Google / DeepL / OpenAI / Gemini...). After
  the first model download the tool must work with the network disconnected.
- **No game access**: never read the game memory / process, never inject, no
  DLL, never modify the game files, never press keys for the game.
  Only: screenshot capture + a separate overlay window.
- **No hardcoded resolution.** The screen size is auto-detected at runtime and
  every pixel value scales with the real resolution. Tests must cover
  1920x1080 **and** 2560x1600.
- Keep the code in **Python**. The bottleneck is the ONNX Runtime inference
  (C++), not the Python code. Optimize by processing only changed regions,
  caching, parallelism - not by rewriting in C++.

---

## 3. Stack

| Part | Choice |
| --- | --- |
| Capture | `mss` and `dxcam` (benchmarked, see `config/config.yaml` -> `capture.backend`) |
| OCR | `rapidocr-onnxruntime` (PP-OCR, ONNX Runtime, CPU) - never EasyOCR |
| Translation | `argos` (default) or `marian` - one common interface |
| Overlay | PyQt6 + pywin32, click-through, always on top |
| Cache | SQLite `data/cache.db` |
| History | text files in `data/sessions/` |
| Config | `config/config.yaml` (PyYAML) + `config/glossary.yaml` |
| Tests | pytest |

---

## 4. Pipeline

```
capture (200 ms poll)
  -> change detection (frame differencing, threshold)
  -> OCR (only when the frame changed)
  -> filter (drop numbers / symbols / conf < 0.5 / < 2 chars)
  -> grouping (vertical gap -> paragraph block; speaker name detection)
  -> debounce (block must be still ~120 ms)
  -> cache lookup (SQLite, normalized key)
  -> glossary protect (placeholder)
  -> translate (batch)
  -> glossary restore
  -> overlay render (translated text over the original bbox)
  -> session history append (exactly once per block)
```

Threads: a **worker thread** does capture / OCR / translation, the **UI
thread** only renders the overlay. The game must not stutter.

---

## 5. Hotkey

`F8` toggles the session **ON / OFF**.

- ON: new session, new history file, automatic translation from then on, no
  further key presses needed.
- OFF: stop capture / OCR / translation, clear all overlays, close the history
  file.

Implemented with `pynput`. `F8` does not conflict with the WuWa keys
(1-5 / Q / E / R / F / Tab / Esc).

---

## 6. Conventions

- One module per stage, in `src/`, small functions, docstrings on every
  public function.
- `TextBlock` is the unit that travels through the pipeline; it carries the
  merged `bbox` and the optional `speaker`.
- The speaker name is **never** translated and **never** invented.
- Any pixel value in the config is a **reference value at 1080p height** and
  is scaled at runtime via `Config.scale()`.
- Real measurements only - never hardcode a benchmark number.

---

## 7. How to run

```powershell
cd D:\translate_wuwa
.\.venv\Scripts\activate
python -m src.main          # press F8 to toggle the translation
```

## 8. How to test

```powershell
python -m pytest -q          # the full suite
python scripts\bench.py      # real benchmark tables
python scripts\make_fixtures.py   # regenerate the sample images
```

The translation models must be downloaded once (see `README.md` section 1):

```powershell
python -c "import argostranslate.package as p; p.update_package_index(); pkg=[x for x in p.get_available_packages() if x.from_code=='en' and x.to_code=='vi'][0]; p.install_from_path(pkg.download())"
python -c "from transformers import MarianMTModel, MarianTokenizer; M='Helsinki-NLP/opus-mt-en-vi'; MarianTokenizer.from_pretrained(M); MarianMTModel.from_pretrained(M)"
```

---

## 9. Module map

| File | Responsibility |
| --- | --- |
| `src/config.py` | YAML config, `Config.scale()` (1080p reference scaling) |
| `src/capture.py` | mss / dxcam backends, fallback, benchmark, resolution detection |
| `src/change.py` | frame differencing |
| `src/ocr.py` | RapidOCR wrapper, `OCRLine` (text + bbox + confidence) |
| `src/filter.py` | drops noise lines, `FilterReport` |
| `src/grouping.py` | `group_lines`, `detect_speaker`, `TextBlock` |
| `src/cache.py` | SQLite `cache` + `history` tables, `normalize()` |
| `src/glossary.py` | placeholder protect / restore |
| `src/translator.py` | `BaseEngine` / `ArgosEngine` / `MarianEngine`, benchmark |
| `src/overlay.py` | PyQt6 transparent click-through window, `OverlayItem` |
| `src/session.py` | session history file, `SessionLog` |
| `src/pipeline.py` | connects the stages, `StageTimings` per stage |
| `src/main.py` | entry point, worker thread, UI thread, F8 hotkey |

---

## 10. P1 status (2026-11-20)

- Skeleton + end-to-end pipeline: **done**.
- Tests: **41 passed**.
- Engine selected: **Argos** (see the P1 report).
- Capture selected: see the P1 report (mss vs dxcam on the real machine).
- The measured latency on this machine is **above 0.5 s**; the slowest stage
  is the **OCR inference** (ONNX Runtime). P2 must attack it first
  (region-of-interest OCR, smaller detection model, or a GPU pass when the
  game is not running).

### P2 ideas (not yet implemented)

1. **ROI OCR**: only run the OCR on the changed region of the frame
   (`src/change.py` already computes the diff mask). This is the single
   biggest win for the in-game case.
2. **Detection model**: use the PP-OCR mobile detection model
   (`det_limit_side_len` / `PP-OCRv4 mobile`) instead of the server one.
3. **ONNX Runtime tuning**: `intra_op_num_threads` is already 5 (measured
   optimum on this CPU); try `graph_optimization_level` and `quantization`.
4. **Translate asynchronously**: keep the last translation on screen while
   the new one is computed.
5. **Block reuse**: a block whose text did not change must never trigger a
   model call (already implemented in `src/pipeline.py` via `_shown`).
