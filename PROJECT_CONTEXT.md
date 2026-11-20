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
  -> change detection (frame differencing, threshold)            [P2]
  -> diff on a downscaled frame (1/4 of the size)                [P3]
  -> ROI computation (bbox of the diff, expanded, clamped)       [P2]
  -> per-region ROI (several disjoint rectangles)                [P3]
  -> tiled refresh (grid of tiles, only the changed ones)        [P3]
  -> OCR (full frame, the ROI crops or the tiles, in parallel)   [P2][P3]
  -> filter (drop numbers / symbols / conf < 0.5 / < 2 chars)
  -> grouping (vertical gap -> paragraph block; speaker name)   [P2]
  -> adaptive grouping (the gaps follow the measured font)       [P3]
  -> merge with the known blocks outside the ROI                 [P2]
  -> debounce (block must be still ~120 ms)
  -> cache lookup (SQLite, normalized key)
  -> UI label check (a menu header is kept in English)           [P2]
  -> split into sentences (regex, Stanza as fallback)           [P2][P3]
  -> number placeholder protect (XNUM0X / XPCT0X)               [P2]
  -> glossary protect (placeholder)
  -> translate (batch, in a background thread)                   [P3]
  -> glossary restore
  -> number placeholder restore + digit alignment check         [P2]
  -> overlay render (wrapped text over the original bbox)       [P2]
  -> session history append (exactly once per block)
```

Threads: a **worker thread** does capture / OCR, a **translation thread**
does the model calls (item C of P3) and the **UI thread** only renders the
overlay. The game must not stutter.

### P2 refresh schedule

- Every frame: only the changed region is OCR'd (the ROI crop), and the
  blocks outside the ROI are kept from the last known state.
- Every `roi_full_refresh_ms` (2000 ms) or every `roi_full_refresh_frames`
  (10 frames), whichever comes first: a **tiled** OCR (P3), which prunes the
  blocks whose source text is gone and catches what the ROI missed.
- When the ROI covers more than `roi_full_frame_threshold` (80 %) of the
  screen: a full-frame OCR runs immediately.

### P3 refresh schedule (the current behaviour)

- Every frame: the diff runs on a **downscaled** copy of the frame (1/4 of
  the size), so the diff stage costs ~6 ms instead of ~40 ms.
- Every frame: the changed area is split into **disjoint regions** (the
  connected components of the diff mask, merged back into text lines). The
  regions are read **in parallel** and merged with the full-screen
  coordinates.
- Every frame: when more than `roi_tiles_threshold` (1 %) of the screen
  changed, the frame is read as a **grid of tiles** and only the changed
  tiles are read (in parallel). Reading the 11 changed tiles of a big menu
  opening in parallel is faster than one full-frame read.
- Every `roi_full_refresh_ms` (2000 ms) or every `roi_full_refresh_frames`
  (10 frames): the same tiled refresh runs, so the blocks whose source text
  is gone are pruned.

---

## 5. Hotkey

`F8` toggles the session **ON / OFF**.

- ON: new session, new history file, automatic translation from then on, no
  further key presses needed.
- OFF: stop capture / OCR / translation, clear all overlays, close the history
  file.

Implemented with `pynput`. `F8` does not conflict with the WuWa keys
(1-5 / Q / E / R / F / Tab / Esc).

`F9` toggles the **live latency HUD** (P3, item E): a small diagnostic panel
in the top-right corner that shows the stage timings and the running median
of the last cycles. It shows numbers only, never a translated text, and it is
OFF by default.

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
| `src/change.py` | frame differencing, downscaled diff (`P3`) |
| `src/roi.py` | ROI computation, per-region ROI, tiled refresh, bbox offsets (`P2`/`P3`) |
| `src/ocr.py` | RapidOCR wrapper, `OCRLine` (text + bbox + confidence), the ROI engine, the parallel pool (`P2`/`P3`) |
| `src/filter.py` | drops noise lines, `FilterReport` |
| `src/grouping.py` | `group_lines`, `detect_speaker`, `TextBlock`, adaptive gaps (`P2`/`P3`) |
| `src/speakers.py` | UI label blacklist + roster, `SpeakerVocabulary` (`P2`) |
| `src/sentences.py` | sentence splitting, number placeholder protect / restore (`P2`/`P3`) |
| `src/wrapping.py` | greedy word wrapping, `fit_text` (`P2`) |
| `src/cache.py` | SQLite `cache` + `history` tables, `normalize()` |
| `src/glossary.py` | placeholder protect / restore |
| `src/translator.py` | `BaseEngine` / `ArgosEngine` / `MarianEngine`, benchmark |
| `src/offline.py` | patches Stanza so Argos never downloads anything |
| `src/overlay.py` | PyQt6 transparent click-through window, `OverlayItem`, the HUD (`P2`/`P3`) |
| `src/session.py` | session history file, `SessionLog` |
| `src/pipeline.py` | connects the stages, `StageTimings` per stage (`P2`/`P3`) |
| `src/async_translate.py` | the background translation thread (`P3`) |
| `src/hud.py` | the live latency HUD state and the formatting (`P3`) |
| `src/display.py` | per-monitor DPI and hot-plug, `DisplayWatcher` (`P3`) |
| `src/main.py` | entry point, worker thread, UI thread, F8 hotkey, F9 HUD (`P2`/`P3`) |

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
   the new one is computed. -> **done in P3** (item C).
2. **More OCR tuning**: the full-frame path is still the slow one
   (~800 ms warm). A smaller `det_limit_side_len` for the full-frame engine
   would cut it, at the cost of a lower detection accuracy. -> **partly done
   in P3**: the tiled refresh replaced the periodic full-frame OCR.
3. **GPU acceleration**: ONNX Runtime is CPU-only on this machine.

### P3 status (2026-11-20) - DONE

All seven P3 items are implemented, tested and benchmarked. The acceptance
criteria are in `REPORT.md` (the P3 report).

| Item | Result |
| --- | --- |
| A. Tiled refresh + per-region ROI + parallel OCR | **Done.** `src/roi.py` (`compute_regions`, `compute_tiles`, `merge_small_regions`), `src/ocr.py` (`read_parallel` with a pool of engines), `src/pipeline.py` (`_read_text`, `_read_tiles`). Two distant corners give two disjoint regions; a big change is read as a grid of tiles in parallel. |
| B. Downscaled diff | **Done.** `src/change.py`. The diff runs on a 1/4 scale frame with a max-pooled mask: **~6 ms** instead of ~40 ms, and a change of a single pixel is never lost. |
| C. Async pipeline | **Done.** `src/async_translate.py`. The OCR of the frame N overlaps the translation of the frame N-1; the last translation stays on screen while the new one is computed. |
| D. Adaptive grouping | **Done.** `src/grouping.py` (`measure_font_height`, `adaptive_gaps`). The grouping gaps are a fraction of the measured font height, so the same dialogue gives the same blocks with a normal font and with a 0.7x font. |
| E. Live latency HUD | **Done.** `src/hud.py` + `src/overlay.py` (`paint_hud`). Toggled with `F9`, shows the same `StageTimings` as the benchmark. |
| F. Per-monitor DPI hot-plug | **Done, best effort.** `src/display.py`. `dxcam` binds its DXGI output to one device and two Desktop Duplication sessions cannot run at the same time, so the capture backend is **recreated** when the captured size changes. The overlay follows with the new resolution, font size and bbox scaling. |
| G. Sentence splitter hardening | **Done.** `src/sentences.py`. `Dr.`, `Mr.`, `Mrs.`, `e.g.`, `i.e.`, `U.S.`, `3,5` and `1,234` are never split; the regex splitter stays the default and Stanza is the fallback (`translation.sentence_splitter`). |

- Tests: **178 passed** (108 in P2, 70 new in P3).
- The new fixtures are **h** (two corners changed), **i** (the 0.7x font)
  and **j** (a big screen change). The P1/P2 fixtures were not regenerated.
- The in-game ROI path went from **143 ms** (P2) to **~91 ms** warm median.
- The big screen change of the fixture (j) went from **954 ms** to
  **478 ms** (under the 500 ms target).
- The diff stage went from **38 ms** to **7 ms**.
- The **two-step read** (detect on a half-size frame, recognize the native
  crops in parallel) is what made the difference: the full-frame read went
  from **946 ms** to **367 ms** with the same 10 text lines.

### P3 config keys

| Key | Default | Meaning |
| --- | --- | --- |
| `adaptive_grouping` | `true` | derive the grouping gaps from the measured font height |
| `group_gap_ratio` | `0.55` | `group_gap = font_height * group_gap_ratio` |
| `speaker_gap_ratio` | `3.0` | `speaker_gap = font_height * speaker_gap_ratio` |
| `adaptive_min_lines` | `2` | below this many lines the reference gaps are used |
| `roi_regions_enabled` | `true` | split the changed area into disjoint regions |
| `roi_region_min_area` | `1200` | a smaller region is merged into its neighbour |
| `roi_max_regions` | `4` | maximum number of regions read in one frame |
| `roi_workers` | `3` | worker threads used to read the regions |
| `roi_region_merge_gap` | `200` | two components closer than this are one region |
| `roi_region_min_width` | `480` | a region is widened to at least this width |
| `roi_tiles_threshold` | `0.01` | above this fraction of the screen, the tiles are used |
| `tiles_enabled` | `true` | the scheduled refresh reads the changed tiles |
| `tile_cols` / `tile_rows` | `4` / `3` | the size of the tile grid |
| `tile_changed_threshold` | `0.004` | a tile is read when this fraction changed |
| `tile_full_frame_ratio` | `0.5` | above this fraction of changed tiles, a full read |
| `tile_workers` | `3` | worker threads used to read the tiles |
| `tile_intra_threads` | `2` | ONNX threads of each tile worker |
| `diff_downscale` | `4` | the factor of the downscaled diff |
| `diff_refine_edges` | `true` | refine the region edges at full resolution |
| `async_pipeline` | `true` | the translation runs in a background thread |
| `async_queue_size` | `2` | how many translations may be in flight |
| `ocr_intra_threads` | `3` | ONNX threads of the full-frame and ROI engines |
| `ocr_two_step` | `true` | detect on a small frame, recognize the native crops |
| `ocr_detect_scale` | `0.5` | the scale of the frame the detection runs on |
| `ocr_rec_workers` | `8` | the workers that recognize the lines in parallel |
| `ocr_rec_intra_threads` | `1` | the ONNX threads of each recognition worker |
| `hud.enabled` | `false` | the live latency HUD is off by default |
| `hud.hotkey` | `F9` | the hotkey that toggles the HUD |
| `hud.history` | `10` | the number of cycles kept for the running median |
| `hud.font_size` | `14` | the font size of the HUD (scaled at runtime) |
| `hud.text_color` / `hud.background_color` / `hud.background_alpha` / `hud.margin` | | the look of the HUD |

### P3 ideas (not yet implemented)

1. **The detection is still the bottleneck** (~200 ms of the 367 ms of the
   two-step read, and 469 ms of the 478 ms of a big screen change). The next
   step is the PP-OCR **mobile** detection model, measured **on the small
   detection frame** (on the full frame it was slower, see the P2 item E).
2. **The detection scale is a compromise**: 0.5 keeps the 0.7x font exact,
   0.35 is faster but loses a period sometimes. A per-frame scale, chosen
   from the measured text height, would get both.
3. **The detection still runs on the whole frame** in the tiled refresh, even
   when a single pixel changed in a corner. The detector could run on the
   bounding box of the changed pixels instead.
4. **The hot-plug was not tested with a real second monitor** (the machine
   has one). It is exercised through the tests with a mocked size change.
