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
| `F9` | Toggle the **live latency HUD** (P3) |

* Press **F8 once** -> a new session starts, a new history file is created and
  every new text that appears on screen is translated automatically. No
  further key presses are needed.
* Press **F8 again** -> capture / OCR / translation stop, all overlays are
  cleared and the history file is closed.

`F8` does not conflict with the WuWa default keys (1-5 / Q / E / R / F / Tab /
Esc).

The state is printed to the log and shown on the overlay
(`TRANSLATING` / `OFF`).

### The F9 hotkey (the live latency HUD)

Press **F9** to show a small diagnostic panel in the top-right corner of the
screen. It shows the time of each pipeline stage of the last cycle and the
running median of the last few cycles:

```
diff   6.9 ms   ocr  95.1 ms   total 104.5 ms
median  91 ms   p95  307 ms
```

The numbers come from the same `StageTimings` object that `scripts/bench_p3.py`
prints, so the HUD and the benchmark always agree. The HUD shows **numbers
only**, never a translated text, and it is **off by default**.

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
| `sample_h_two_corner_base.png` | 1920x1080 | the base frame of the two-corner test (P3) |
| `sample_h_two_corner_changed.png` | 1920x1080 | a change in the top-left **and** in the bottom-right (P3) |
| `sample_i_small_font.png` | 1920x1080 | the same dialogue with a 0.7x font (P3) |
| `sample_j_big_change_base.png` | 1920x1080 | the base frame of the big-change test (P3) |
| `sample_j_big_change.png` | 1920x1080 | an inventory panel opens - a big screen change (P3) |

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
python scripts\bench.py      # the P1/P2 tables
python scripts\bench_p3.py   # the P3 tables (every number is a median of 7 runs)
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

### P3

| Key | Meaning |
| --- | --- |
| `adaptive_grouping` | derive the grouping gaps from the measured font height (`true`) |
| `group_gap_ratio` | `group_gap = font_height * group_gap_ratio` (0.55) |
| `speaker_gap_ratio` | `speaker_gap = font_height * speaker_gap_ratio` (3.0) |
| `adaptive_min_lines` | below this many lines the reference gaps are used (2) |
| `roi_regions_enabled` | split the changed area into disjoint regions (`true`) |
| `roi_region_min_area` | a smaller region is merged into its neighbour (1200) |
| `roi_max_regions` | the maximum number of regions read in one frame (4) |
| `roi_workers` | the worker threads used to read the regions in parallel (3) |
| `roi_region_merge_gap` | two components closer than this are one region (200) |
| `roi_tiles_threshold` | above this fraction of the screen, the tiles are used (0.01) |
| `tiles_enabled` | the scheduled refresh reads the changed tiles (`true`) |
| `tile_cols` / `tile_rows` | the size of the tile grid (4 / 3) |
| `tile_changed_threshold` | a tile is read when this fraction changed (0.004) |
| `tile_full_frame_ratio` | above this fraction of changed tiles, a full read (0.5) |
| `tile_workers` | the worker threads used to read the tiles (3) |
| `tile_intra_threads` | the ONNX threads of each tile worker (2) |
| `diff_downscale` | the factor of the downscaled diff (4) |
| `diff_refine_edges` | refine the region edges at the full resolution (`true`) |
| `async_pipeline` | the translation runs in a background thread (`true`) |
| `async_queue_size` | how many translations may be in flight (2) |
| `ocr_two_step` | detect on a small frame, recognize on the native crops (`true`) |
| `ocr_detect_scale` | the scale of the frame the detection runs on (0.5) |
| `ocr_rec_workers` | the workers that recognize the text lines in parallel (8) |
| `ocr_rec_intra_threads` | the ONNX threads of each recognition worker (1) |
| `hud.enabled` | the live latency HUD is on (`false` by default) |
| `hud.hotkey` | the hotkey that toggles the HUD (`F9`) |
| `hud.history` | the number of cycles kept for the running median (10) |
| `hud.font_size` | the font size of the HUD (scaled at runtime) |

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

## 6b. What P3 added

### The tiled refresh and the per-region ROI (item A)

Three changes, all measured on this machine (1920x1080):

**The per-region ROI.** The changed area is split into the connected
components of the diff mask. The components of the same text line are merged
back (a changed line is made of one component per glyph), but a change in the
top-left corner and a change in the bottom-right corner stay **two disjoint
regions** instead of one huge rectangle. The regions are read **in parallel**
and merged back with the full-screen coordinates.

**The two-step read.** The OCR of RapidOCR has two halves: the **detection**
(which finds the text boxes) and the **recognition** (which reads the text).
The detection is the slow half - 598 ms of the 972 ms of a full-frame read -
and it always runs at the size of the image it is given, so the only way to
make it faster is to give it a **smaller image**. The recognition is fast and
can be **parallelized**.

So the detection runs on a copy of the frame scaled to `ocr_detect_scale`
(0.5) and the recognition runs on the crops of the **original** frame, in a
pool of 8 workers. The text keeps its native pixel size, so nothing is lost:

| Full-frame read of a 1920x1080 frame | Median | Lines found |
| --- | --- | --- |
| P2 (the plain call) | 946 ms | 10 |
| **P3 (the two-step read)** | **367 ms** | 10 (none lost) |

**The tiled refresh.** When a big part of the screen changes (a menu opens),
the frame is split into a grid of tiles and only the changed tiles are read.
The detection still runs once on the whole (downscaled) frame, and only the
lines that fall into a changed tile are recognized. That detail matters:
reading the detection **inside** each tile cuts the text lines that cross a
tile border - measured on the fixture (j), "Cost 25 Astrite" became
"Cost 25 As" and 4 of the 10 lines were lost.

| Path | P2 | P3 |
| --- | --- | --- |
| A dialogue line changed | 143 ms (best run) | **91 ms** median |
| A big screen change | 954 ms | **478 ms** median |
| The diff stage | 38 ms | **7 ms** median |

### The downscaled diff (item B)

The frame differencing runs on a copy of the frame scaled to 1/4 of the
size, and the mask is **max-pooled**: a block is marked as changed when at
least one of its pixels changed, so a change of a single pixel is never lost.
The full-resolution diff is only used to refine the edges of a region.

### The async pipeline (item C)

The OCR of a frame N overlaps the translation of the frame N-1: the
translation runs in a background thread and the last translation stays on
screen while the new one is computed. The overlay is never cleared just
because a new frame is being processed.

### The adaptive grouping (item D)

The grouping thresholds are no longer fixed pixel values: they are a
fraction of the **measured font height** of the frame (the median height of
the OCR boxes). The same dialogue therefore gives the same blocks and the
same speaker with the normal font **and** with a 0.7x font.

### The live latency HUD (item E)

Press **F9**. A small panel in the corner shows the time of each stage of the
last cycle and the running median. It reads the same `StageTimings` object
that the benchmark prints, and it shows numbers only.

### The per-monitor hot-plug (item F)

The worker polls the display watcher on every frame (a cheap size check).
When the captured size changes - a monitor was plugged in, unplugged or the
resolution changed - the DPI is read, the capture backend is **closed and
recreated** for the new monitor, and the overlay is resized with the new
resolution, the rescaled font size and the rescaled bboxes. The tool is not
restarted: the session, the cache and the history file all survive.

This is a **best effort**: dxcam binds its DXGI output to one device at
creation and two Desktop Duplication sessions cannot run at the same time,
so the running session cannot be rebound to another monitor - it has to be
recreated. The details are in the P3 report.

### The sentence splitter hardening (item G)

The abbreviation list grew (medical, military, academic and business
titles) and the decimal handling was added: `Dr.`, `Mr.`, `Mrs.`, `e.g.`,
`i.e.`, `U.S.`, `3,5` and `1,234` are never split. The regex splitter stays
the default and Stanza remains available as a fallback
(`translation.sentence_splitter`).

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
  main.py       entry point (worker thread + UI thread + F8 / F9 hotkeys)
  config.py     YAML configuration
  capture.py    mss / dxcam screen capture, resolution auto-detection
  change.py     frame differencing + the downscaled diff (P3)
  roi.py        ROI computation, per-region ROI, tiled refresh (P2 / P3)
  ocr.py        RapidOCR wrapper, the two-step read, the parallel pool (P2 / P3)
  filter.py     drops numbers / low confidence / short lines
  grouping.py   line grouping + speaker name detection + adaptive gaps (P2 / P3)
  speakers.py   UI label blacklist + roster (P2)
  sentences.py  sentence splitting + number placeholder protection (P2 / P3)
  wrapping.py   greedy word wrapping for the overlay (P2)
  cache.py      SQLite translation cache + history table
  glossary.py   placeholder protection of the WuWa terms
  translator.py Argos / MarianMT engines behind one interface
  async_translate.py  the background translation thread (P3)
  display.py    per-monitor DPI + the hot-plug watcher (P3)
  hud.py        the live latency HUD (P3)
  overlay.py    transparent, click-through, always-on-top PyQt6 window + the HUD
  session.py    session history file
  pipeline.py   connects the stages and measures the time of each stage
scripts/
  make_fixtures.py  generates the sample images
  bench.py          prints the real P1/P2 benchmark tables
  bench_p3.py       prints the P3 tables (median / min / max of 7 runs)
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
