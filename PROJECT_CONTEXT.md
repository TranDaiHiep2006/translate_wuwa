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
  -> ROI computation (bbox of the diff, expanded, clamped)   [P2]
  -> OCR (full frame, or only the ROI crop at native res)    [P2]
  -> filter (drop numbers / symbols / conf < 0.5 / < 2 chars)
  -> grouping (vertical gap -> paragraph block; speaker name detection)
  -> merge with the known blocks outside the ROI               [P2]
  -> debounce (block must be still ~120 ms)
  -> cache lookup (SQLite, normalized key)
  -> UI label check (a menu header is kept in English)         [P2]
  -> split into sentences                                   [P2]
  -> number placeholder protect (XNUM0X / XPCT0X)             [P2]
  -> glossary protect (placeholder)
  -> translate (batch)
  -> glossary restore
  -> number placeholder restore + digit alignment check       [P2]
  -> overlay render (wrapped text over the original bbox)     [P2]
  -> session history append (exactly once per block)
```

Threads: a **worker thread** does capture / OCR / translation, the **UI
thread** only renders the overlay. The game must not stutter.

### P2 refresh schedule

- Every frame: only the changed region is OCR'd (the ROI crop), and the
  blocks outside the ROI are kept from the last known state.
- Every `roi_full_refresh_ms` (2000 ms) or every `roi_full_refresh_frames`
  (10 frames), whichever comes first: a full-frame OCR, which prunes the
  blocks whose source text is gone and catches what the ROI missed.
- When the ROI covers more than `roi_full_frame_threshold` (80 %) of the
  screen: a full-frame OCR runs immediately.

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
| `src/roi.py` | ROI computation, bbox offsets, block merging (`P2`) |
| `src/ocr.py` | RapidOCR wrapper, `OCRLine` (text + bbox + confidence), the ROI engine (`P2`) |
| `src/filter.py` | drops noise lines, `FilterReport` |
| `src/grouping.py` | `group_lines`, `detect_speaker`, `TextBlock` |
| `src/speakers.py` | UI label blacklist + roster, `SpeakerVocabulary` (`P2`) |
| `src/sentences.py` | sentence splitting, number placeholder protect / restore (`P2`) |
| `src/wrapping.py` | greedy word wrapping, `fit_text` (`P2`) |
| `src/cache.py` | SQLite `cache` + `history` tables, `normalize()` |
| `src/glossary.py` | placeholder protect / restore |
| `src/translator.py` | `BaseEngine` / `ArgosEngine` / `MarianEngine`, benchmark |
| `src/offline.py` | patches Stanza so Argos never downloads anything |
| `src/overlay.py` | PyQt6 transparent click-through window, `OverlayItem` |
| `src/session.py` | session history file, `SessionLog` |
| `src/pipeline.py` | connects the stages, `StageTimings` per stage |
| `src/main.py` | entry point, worker thread, UI thread, F8 hotkey |

---

## 10. P1 status (2026-11-20)

- Skeleton + end-to-end pipeline: **done**.
- Tests: **44 passed**.
- Engine selected: **Argos** (see the P1 report).
- Capture selected: **dxcam** (3.0 ms vs 61.5 ms for mss on this machine).
- The measured latency on this machine is **above 0.5 s**: the average
  end-to-end time is **1584 ms cold** / **778 ms warm** on a 1920x1080 image.
  The slowest stage is the **OCR inference** (ONNX Runtime, ~830-1830 ms);
  the translation is only ~50-280 ms.
- The tool works fully offline (`src/offline.py` patches Stanza so it never
  downloads `resources.json`; `tests/test_offline.py` blocks every socket and
  still translates).

### P2 status (2026-11-20) - DONE

All six P2 items are implemented, tested and benchmarked.

| Item | Result |
| --- | --- |
| A. ROI OCR | **Done.** `src/roi.py` + a second OCR engine at native resolution. In-game warm end-to-end: **143 ms** (was 802 ms full-frame warm). |
| B. Overlay wrapping | **Done.** `src/wrapping.py`. The bbox grows vertically, the font size stays. `data/overlay_demo.png` regenerated. |
| C. Sentence translation + number protection | **Done.** `src/sentences.py`. `Reward: 12000` now survives (was `2000`). |
| D. Speaker detector | **Done.** `src/speakers.py` + `config/ui_labels.yaml` + `config/roster.yaml`. `Quest` / `Skill` / `Inventory` / `Settings` are never speakers. |
| E. OCR model experiment | **Done, negative result.** The mobile detection model and the int8 recognition model are **not** faster on the ROI crop. The P1 server models stay the default (details in `REPORT.md`). |
| F. UI label translation | **Done** (extra). A menu header is kept in English instead of being translated. |

- Tests: **108 passed** (44 in P1, 64 new in P2).
- The measured in-game latency is now **under 0.5 s**: **143 ms** warm
  (OCR 99 ms, translation 0.04 ms thanks to the cache). The full-frame
  sweep is still ~800 ms warm / ~1740 ms cold, but it only runs every
  2 s (or every 10 frames), not on every frame.

### P2 ideas (not yet implemented)

1. **Translate asynchronously**: keep the last translation on screen while
   the new one is computed.
2. **More OCR tuning**: the full-frame path is still the slow one
   (~800 ms warm). A smaller `det_limit_side_len` for the full-frame engine
   would cut it, at the cost of a lower detection accuracy.
3. **GPU acceleration**: ONNX Runtime is CPU-only on this machine.
