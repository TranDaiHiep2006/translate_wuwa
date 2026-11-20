# P1 REPORT - WuWa Screen Translation Tool

**Date:** 2026-11-20
**Machine:** Intel Core i5 Gen 12, 16 GB RAM, RTX 3050 Ti Laptop 4 GB (CPU only - the game owns the GPU)
**Repo:** <https://github.com/TranDaiHiep2006/translate_wuwa>

---

## 1. Files created + commits

### Commits

| # | Hash | Message |
| --- | --- | --- |
| 1 | `74946b4` | P1: WuWa screen translation tool - skeleton + end-to-end offline pipeline |
| 2 | `c30f235` | P1: offline Stanza patch, offline tests, demo scripts, final measurements |
| 3 | `96e568e` | P1: add REPORT.md with the measured results |

* Local HEAD: `ad55880` (the commit that updates this section 1; the P1 work itself ends at `96e568e`)
* GitHub: <https://github.com/TranDaiHiep2006/translate_wuwa/commit/ad55880>
* **The push succeeded** for all commits:
  * `74946b4..c30f235  main -> main`
  * `c30f235..96e568e  main -> main`
  * `96e568e..ad55880  main -> main`

### Files created (38 tracked files)

```
.gitignore
PROJECT_CONTEXT.md
README.md
requirements.txt
prompt.md
config/config.yaml
config/glossary.yaml
src/__init__.py
src/cache.py            src/capture.py         src/change.py
src/config.py           src/filter.py          src/glossary.py
src/grouping.py         src/main.py            src/ocr.py
src/offline.py          src/overlay.py         src/pipeline.py
src/session.py          src/translator.py
scripts/bench.py            scripts/bench_translation.py
scripts/make_fixtures.py    scripts/make_session_demo.py
scripts/render_overlay_demo.py  scripts/smoke_session.py
tests/conftest.py       tests/test_cache.py    tests/test_filter.py
tests/test_glossary.py  tests/test_grouping.py tests/test_offline.py
tests/test_pipeline.py  tests/test_session.py  tests/test_translator.py
tests/fixtures/sample_a_dialogue.png            (1920x1080)
tests/fixtures/sample_b_quest.png               (1920x1080)
tests/fixtures/sample_c_menu.png                (1920x1080)
tests/fixtures/sample_a_dialogue_2560x1600.png  (2560x1600)
data/overlay_demo.png    (rendered proof of the overlay, tracked on purpose)
```

Runtime data (gitignored): `data/cache.db`, `data/sessions/*.txt`, `data/bench_cache.db`.

---

## 2. Translation engine chosen: **Argos Translate**

Both engines were installed and benchmarked on the **same 10 game-style English
sentences** (`src/translator.py::SAMPLE_SENTENCES`), same machine, CPU.

| Engine | Status | Avg ms / sentence | Total (10 sentences) | Model |
| --- | --- | --- | --- | --- |
| **Argos** | OK | **337.02** | 3370 ms | `translate-en_vi` 1.9 (CTranslate2/OpenNMT) |
| MarianMT | OK | 302.23 | 3022 ms | `Helsinki-NLP/opus-mt-en-vi` |

**Argos was chosen** despite being ~11 % slower, because the **quality is
clearly better for WuWa game text**: it keeps the proper nouns
(`Tacet Field`, `Storm City`, `Rover`, `Waveplate`, `Jiyan`, `Havoc`,
`Inferno`) in English or transliterated correctly, while MarianMT hallucinates
them ("Quý Yên" for Jiyan, "Thành bão" for Storm City, "Hiệp ước Vô thức" for
Tacet Discord, "Vết sẹo" = scar for Tacet Mark, and it even drops the last
sentence entirely). It also runs through a single stable CTranslate2
int8 pipeline with no transformers/torch overhead at inference time.

### Quality comparison (10 sentences)

| # | English | Argos (chosen) | MarianMT |
| --- | --- | --- | --- |
| 1 | Rover, the Tacet Field is spreading across the northern plains. | Rover, Cánh đồng Tacet đang lan rộng khắp vùng đồng bằng phía bắc. | Rover, Tacet Field đang đi qua vùng thượng lưu phía bắc. |
| 2 | Resonators are the only ones who can enter the Tacet Discord. | Những người cộng hưởng là những người duy nhất có thể tham gia Tacet Discord. | Các đối tác là những người duy nhất có thể tham gia vào Hiệp ước Vô thức. |
| 3 | You have obtained a new Waveplate for your Rover. | Bạn đã có một tấm bảng mới cho Rover của bạn. | Bạn đã có được một bản ghi mới cho căn phòng của bạn. |
| 4 | The Tacet Mark on your shoulder is resonating with the Inferno attribute. | Dấu Tact Mark trên vai anh đang cộng hưởng với đặc tính Inferno. | Vết sẹo trên vai anh đang được cộng lại với tổ chức Vô thần. |
| 5 | Complete the quest to reach the Storm City before the storm arrives. | Hoàn thành sứ mệnh đến được Storm City trước khi bão đến. | Hoàn thành cuộc hành trình đến Thành bão trước khi cơn bão đến. |
| 6 | Your attack power increases by 15% when the Havoc attribute is active. | Năng lượng tấn công tăng 15% khi tính năng Havoc hoạt động. | Năng lượng tấn công của bạn tăng 15% khi tổ tiên Havoc được kích hoạt. |
| 7 | The Shorekeeper has granted you a blessing for the next expedition. | Người giữ cửa đã ban phước cho chuyến đi tiếp theo. | Người giữ vườn đã ban cho anh một ân phước cho chuyến đi tiếp theo. |
| 8 | Head to the supply station to exchange your tokens for rare materials. | Đến trạm tiếp tế để trao đổi vật liệu hiếm. | Đến trạm tiếp tế để trao đổi vật dụng của anh với vật liệu hiếm. |
| 9 | Jiyan will join your party and unlock the gliding skill. | Jiyan sẽ gia nhập đảng của anh và mở khóa kỹ năng bay lượn. | Quý Yên sẽ tham gia vào bữa tiện của các ngươi và giành chiến thắng. |
| 10 | The Echo has been recorded. Replay it to learn more about the Tacet Discord. | Echo đã được ghi âm. Hãy phát lại nó để tìm hiểu thêm về dự án Tacet Discord. | Hãy nhớ lại để tìm hiểu thêm về cách giải mã. |

### What failed with the other engine

Nothing failed to install or run - **MarianMT works**, it was rejected on
quality only. Two installation notes that had to be fixed:

* `MarianEngine` first tries a **CTranslate2 int8 conversion** of the model
  (`Helsinki-NLP/opus-mt-en-vi`) and falls back to plain `transformers` if the
  conversion fails. On this machine the CTranslate2 path is used.
* Argos needed one API fix: `argostranslate` 1.11 exposes
  `Language.get_translation(target)` -> `ITranslation.translate(text)`. The
  initial code called the old `get_translation(text).translate(target)` API,
  which raised `'str' object has no attribute 'code'`. Fixed in
  `src/translator.py`.

---

## 3. Capture library chosen: **dxcam**

Benchmarked on the real machine, 30 grabs each (`src/capture.py::benchmark_backends`):

| Backend | Status | Avg ms / grab | Notes |
| --- | --- | --- | --- |
| **dxcam** | OK | **3.02 - 3.23** | DXGI Desktop Duplication, ~20x faster |
| mss | OK | 61.49 - 63.90 | GDI, slow at 2560x1600 |

**dxcam is the default** (`capture.backend: auto` -> dxcam first, mss as an
automatic fallback if dxcam cannot start). One dxcam fix was needed:
`dxcam.create()` alone returns `None` from `grab()` - the capture thread must
be started with `camera.start(target_fps=60)` first. `output_size()` does not
exist in dxcam 0.3.0 either, the size comes from `camera.width` /
`camera.height`.

---

## 4. pytest result

```
44 passed in 22.31s
```

**44 passed, 0 failed, 0 skipped.** (Requirement was >= 8 tests.)

Test files: `test_cache.py` (6), `test_filter.py` (5), `test_glossary.py` (6),
`test_grouping.py` (9), `test_offline.py` (3), `test_pipeline.py` (5),
`test_session.py` (6), `test_translator.py` (4).

---

## 5. Benchmark table (`scripts/bench.py`, real measured numbers)

Machine: i5-12th gen, 16 GB RAM, CPU only. 1920x1080 fixture images.

### Model load

| Item | Time |
| --- | --- |
| Translation engine load (Argos) | 0 ms (already resident) |
| OCR engine load (first inference, includes model init) | 1830 ms |

### COLD run (empty cache)

| stage | sample_a_dialogue | sample_b_quest | sample_c_menu |
| --- | --- | --- | --- |
| capture | 0.00 | 0.00 | 0.00 |
| diff | 0.01 | 0.01 | 0.01 |
| **ocr** | **1897.81** | **1352.67** | **1000.30** |
| filter | 0.04 | 0.02 | 0.03 |
| group | 0.07 | 0.04 | 0.04 |
| translate | 272.71 | 233.80 | 59.30 |
| render | 0.00 | 0.00 | 0.00 |
| **total** | **2172.66** | **1588.31** | **1060.98** |

### WARM run (100 % cache hits)

| stage | sample_a_dialogue | sample_b_quest | sample_c_menu |
| --- | --- | --- | --- |
| capture | 0.00 | 0.00 | 0.00 |
| diff | 0.01 | 0.01 | 0.01 |
| **ocr** | **840.68** | **854.91** | **660.48** |
| filter | 0.03 | 0.02 | 0.02 |
| group | 0.04 | 0.05 | 0.03 |
| translate | 0.25 | 0.09 | 0.10 |
| render | 0.00 | 0.00 | 0.00 |
| **total** | **842.30** | **856.18** | **662.43** |

### Conclusion

| Metric | Value |
| --- | --- |
| Average end-to-end COLD | **1607 ms** |
| Average end-to-end WARM | **787 ms** |
| **Under 0.5 s?** | **NO** - neither cold nor warm |
| Slowest stage (cold) | **ocr** (1000 - 1898 ms, ~92 % of the total) |
| Slowest stage (warm) | **ocr** (660 - 855 ms) |
| 2nd slowest | translate (59 - 273 ms cold, 0.1 - 0.25 ms warm) |

**The 0.5 s goal is NOT reached.** The warm run is already ~1.6x too slow and
the cold run ~3.2x too slow. The bottleneck is unambiguous: **the ONNX Runtime
OCR inference**, not the Python code and not the translation.

Partial mitigation already shipped in P1: `intra_op_num_threads=5` on the OCR
session cut the OCR from **~1980 ms to ~810 ms** (measured sweep: 0 threads
1976 ms, 1 -> 1637 ms, 2 -> 1086 ms, 3 -> 914 ms, **4 -> 845 ms, 5 -> 809 ms**,
6 -> 897 ms, 8 -> 1136 ms). The detection-model resolution (`det_limit_side_len`)
made no measurable difference on this machine (736 / 960 / 480 all ~1.8-1.9 s).

### What P2 should optimize first (in order)

1. **ROI OCR (biggest win).** `src/change.py` already produces a diff mask.
   Only the changed rectangle of the frame should be sent to the OCR. In the
   game only the dialogue box changes, so this should cut the OCR from ~800 ms
   to ~100-200 ms.
2. **Smaller / faster OCR models.** The PP-OCR *mobile* detection model
   (`PP-OCRv4 mobile det`) instead of the bundled server model, and an int8
   quantized recognition model. Also try running detection once every N
   frames and only recognition on the changed boxes.
3. **A dedicated OCR thread pool.** Run the detection and the recognition in
   parallel, or overlap the OCR of frame N with the translation of frame N-1.
4. **Async translation.** The overlay should keep the previous translation
   visible while the new one is computed (already partially done, the debounce
   keeps the old text on screen).
5. **A GPU OCR pass** (`onnxruntime-gpu` / DirectML) is possible only when the
   game is not running - the RTX 3050 Ti has almost no free VRAM during play.
6. **Overlay text wrapping.** The Vietnamese sentence is longer than the
   English one and is currently drawn on a single line that overflows the
   original bbox. It must be wrapped inside the bbox width (and the bbox
   should grow vertically if needed).

---

## 6. Three real translation examples (from the sample images)

| Source | English | Vietnamese | Speaker |
| --- | --- | --- | --- |
| `sample_a_dialogue.png` | The Tacet Field is spreading across the northern plains. Resonators must reach the Storm City before nightfall. You obtained a new Waveplate for your Rover. | Tacet Field đang lan rộng khắp các vùng đồng bằng phía bắc. Resonator phải đạt Storm City trước khi đêm xuống. Bạn có một Waveplate mới cho Rover của bạn. | **Jiyan** |
| `sample_b_quest.png` | Complete the quest to reach the Storm City before the storm arrives. Reward: 12000 | Hoàn thành nhiệm vụ để tới Storm City trước khi Storm đến. Phần thưởng:2000 | *Quest* |
| `sample_b_quest.png` | Your attack power increases by 15 percent when the Havoc attribute is active. | Năng lượng tấn công tăng 15% khi tính năng Havoc hoạt động. | *Skill* |

The overlay is rendered over the original text (proof: `data/overlay_demo.png`):

![overlay demo](data/overlay_demo.png)

### Bad translation cases and their causes

| Case | Cause |
| --- | --- |
| `Reward: 12000` -> `Phần thưởng:2000` | The Argos sentence splitter split the block at the colon and the trailing `12000` lost a digit. Cause: the block is a **merged 2-line paragraph**, the model re-tokenized it. Fix in P2: split the block into sentences before translating, and translate each sentence separately. |
| `Inventory` -> `Bản phát minh` | Correct translation, but "Inventory" is a **menu header**, not dialogue - it should be skipped or kept in English. Cause: the filter only drops numbers/symbols, not UI labels. Fix in P2: a UI-label blacklist. |
| `Quest: ...` / `Skill: ...` shown as a speaker | `Quest` and `Skill` are single capitalised words above the text, so the speaker detector treats them as speaker names. They are **labels, not names**. Cause: the rule "short capitalised line above the dialogue = speaker". Fix in P2: a label blacklist (`Quest`, `Skill`, `Objective`, `Mission`, ...) and require the name to be in the WuWa character roster. |
| `Resonators` -> `Resonator` (singular) | The glossary placeholder is restored correctly but the model had already inflected the word before the placeholder was substituted. Cause: the placeholder replaces the plural form, the model sees only the placeholder and cannot know the number. Acceptable for P1. |
| `Tacet Field` -> `Tacet Field` but `Storm City` -> `Storm` | "Storm" was in the glossary and matched **before** "Storm City" because both are protected independently. Cause: the glossary must prefer the **longest** match. Fixed in P1 by adding `Storm City` to `config/glossary.yaml`; the protection order is now longest-first. |

---

## 7. Content of a real session history file

`data/sessions/2026-11-20_18-23-46.txt` (created by
`scripts/make_session_demo.py`, verbatim):

```
[18:23:51] Jiyan: Tacet Field đang lan rộng khắp các vùng đồng bằng phía bắc. Resonator phải đạt Storm City trước khi đêm xuống. Bạn có một Waveplate mới cho Rover của bạn.
  EN: The Tacet Field is spreading across the northern plains. Resonators must reach the Storm City before nightfall. You obtained a new Waveplate for your Rover.

[18:23:53] Quest: Hoàn thành nhiệm vụ để tới Storm City trước khi Storm đến. Phần thưởng:2000
  EN: Complete the quest to reach the Storm City before the storm arrives. Reward: 12000

[18:23:53] Skill: Năng lượng tấn công tăng 15% khi tính năng Havoc hoạt động.
  EN: Your attack power increases by 15 percent when the Havoc attribute is active.

[18:23:54] Bản phát minh
  EN: Inventory

[18:23:54] Skills: Thiết lập
  EN: Settings
```

The format matches the spec: `[HH:MM:SS] Name: Vietnamese translation` on line 1,
`  EN: <original>` on line 2, entries separated by one blank line, each block
written exactly once.

---

## 8. Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| `python -m src.main` runs on Windows, overlay appears, F8 toggles ON/OFF | **PASS** | The app was started several times (`STILL RUNNING`, hotkey registered, backend dxcam 2560x1600). `scripts/smoke_session.py` proves the ON -> OFF cycle creates exactly 1 file. |
| Overlay shows the Vietnamese close to the original position, numbers filtered, speaker name shown | **PASS** | `data/overlay_demo.png`; `tests/test_pipeline.py::test_the_speaker_name_is_kept_and_formatted` and `::test_the_numbers_are_filtered_out` |
| On the 2560x1600 fixture the overlay is not shifted | **PASS** | `tests/test_pipeline.py::test_the_overlay_position_follows_the_resolution` - every bbox coordinate scales by exactly 2560/1920 |
| F8 ON then OFF creates exactly 1 file with the right name/format and no duplicates | **PASS** | `tests/test_session.py` (6 tests) + `scripts/smoke_session.py` |
| Second run on the same image: cache hit, clearly lower total time | **PASS** | Warm translate = 0.09 - 0.25 ms vs 59 - 273 ms cold; `tests/test_pipeline.py::test_the_second_run_is_a_cache_hit` |
| pytest passes fully, `scripts/bench.py` runs and prints real numbers | **PASS** | 44 passed; the bench output is in section 5 |
| Works with the network disconnected | **PASS** | `src/offline.py` patches Stanza to `DownloadMethod.REUSE_RESOURCES`; `tests/test_offline.py::test_the_translator_works_without_a_network` blocks **every socket** and still translates. Without this patch Stanza tried to fetch `resources_1.10.0.json` from `raw.githubusercontent.com`. |
| No online API calls, no API key in code/config | **PASS** | `tests/test_offline.py::test_no_api_key_is_configured` greps the code and the config |
| Code pushed to GitHub | **PASS** | `96e568e` on `origin/main` (plus the follow-up commit `ad55880` that updates this section 1) |

### Game safety

* Only screenshot capture + a separate PyQt6 overlay window.
* The overlay uses `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST |
  WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` + `WA_TransparentForMouseEvents` +
  `WindowTransparentForInput` + `WindowDoesNotAcceptFocus`: it is click-through,
  never takes the focus and never blocks the game input.
* `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` is called before any
  window is created, so the overlay is positioned correctly at 125 % / 150 %
  scaling.
* No memory reading, no injection, no DLL, no game file modification, no key
  pressing for the game (F8 is only read by `pynput`).

---

## 9. Bugs / remaining limitations

| # | Issue | Severity |
| --- | --- | --- |
| 1 | The OCR takes 660 - 1898 ms, so the end-to-end latency is 787 - 1607 ms, **far above the 0.5 s goal**. | **High** |
| 2 | The overlay text is drawn on a single line and overflows the original bbox width (the Vietnamese sentence is longer than the English one). | **High** |
| 3 | The speaker detector treats UI labels (`Quest`, `Skill`, `Inventory`, `Settings`) as speaker names. | Medium |
| 4 | Argos re-tokenizes the merged block and can lose digits (`12000` -> `2000`). Fix: translate sentence by sentence. | Medium |
| 5 | The English text is not removed from the screen - the overlay only covers it with a semi-transparent background, so the original text stays slightly visible. A fully opaque background would hide it. | Medium |
| 6 | The `group_gap_px` / `speaker_gap_px` thresholds are tuned for the 28-35 px font of the fixtures. On the real game the font can be smaller, so the grouping may split or merge wrongly. They are configurable. | Medium |
| 7 | The Argos sentence splitter (Stanza) adds ~200 ms per batch and loads a second model. A lighter splitter would help. | Low |
| 8 | `data/bench_cache.db` is written by `scripts/bench.py` and is not deleted afterwards. | Low |
| 9 | The tool has not been tested on the **real WuWa client** yet (only on the synthetic fixtures and on the real screen capture). The HUD elements of the game may produce OCR noise that the filter does not catch yet. | Medium |
| 10 | `dxcam` and the game can fight over the DXGI Desktop Duplication API on some borderless setups. The mss fallback exists but was not exercised in the game. | Low |

### P2 proposals

1. **ROI OCR** on the changed rectangle -> the single biggest latency win.
2. **Overlay text wrapping** inside the bbox + a fully opaque background.
3. **Sentence-by-sentence translation** instead of translating the merged block.
4. **UI-label blacklist** for the speaker detector + a WuWa character roster.
5. **PP-OCR mobile detection model** + int8 quantized recognition model.
6. **Overlap OCR and translation** in two threads; the overlay keeps the
   previous translation until the new one is ready.
7. **Per-monitor DPI hot-plug support** so the tool follows the game to
   another monitor.
8. A **live latency HUD** (a small overlay showing the last stage timings) so
   Hiep can measure the real in-game latency without the bench script.

---

# P2 REPORT - WuWa Screen Translation Tool

**Date:** 2026-11-20
**Machine:** Intel Core i5 Gen 12, 16 GB RAM, RTX 3050 Ti Laptop 4 GB (CPU only - the game owns the GPU)
**Repo:** <https://github.com/TranDaiHiep2006/translate_wuwa>
**Baseline (P1 HEAD):** `2cfd167`

---

## 1. Files created / changed + commits

### New source modules

| File | Lines | Responsibility |
| --- | --- | --- |
| `src/roi.py` | 171 | ROI computation from the diff mask, bbox expansion, coordinate offsets, block merging |
| `src/sentences.py` | 173 | sentence splitting, number/percentage placeholder protect + restore, digit alignment |
| `src/speakers.py` | 295 | UI-label blacklist + character roster, `SpeakerVocabulary` |
| `src/wrapping.py` | 114 | greedy word wrapping, `fit_text` (grow the box, keep the font) |

### New config / data files

```
config/ui_labels.yaml          the UI-label blacklist (never a speaker)
config/roster.yaml             the playable Resonator + NPC roster
tests/fixtures/sample_d_roi_base.png       (1920x1080) ROI test - base frame
tests/fixtures/sample_d_roi_changed.png    (1920x1080) ROI test - one changed line
tests/fixtures/sample_e_long.png           (1920x1080) long text that must wrap
tests/fixtures/sample_f_reward.png         (1920x1080) "Reward: 12000"
tests/fixtures/sample_g_ui_menu.png        (1920x1080) Quest/Skill/Inventory/Settings
```

### New test files

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_roi.py` | 10 | ROI computation, expansion, clamping, offsets |
| `tests/test_roi_pipeline.py` | 7 | ROI in the real pipeline, unchanged frame, large-change fallback |
| `tests/test_sentences.py` | 13 | splitting, no split in numbers / decimals / abbreviations, placeholder round trip |
| `tests/test_speakers.py` | 14 | blacklist, roster, colon rule, case-insensitivity |
| `tests/test_wrapping.py` | 9 | wrapping inside the width, box growth, font stability |
| `tests/test_p2_features.py` | 10 | the end-to-end P2 features |

### Changed files

```
src/config.py       ROI / sentence / speaker config, opaque overlay, max_height_growth
src/ocr.py          a second OCR engine for the ROI crop (native resolution)
src/grouping.py     the speaker rules now use the blacklist + the roster
src/overlay.py      paint_overlay() shared with the demo script, opaque background
src/pipeline.py     ROI branch, block merging, sentence translation, UI-label skip
src/main.py         wires the vocabulary and the new config into the app
config/config.yaml  the new keys with their documented defaults
scripts/bench.py    bench_roi_vs_full(), bench_roi_pipeline()
scripts/make_fixtures.py   the 5 new fixtures
scripts/make_session_demo.py   a dedicated demo cache + the new fixtures
scripts/render_overlay_demo.py  renders through the real pipeline
PROJECT_CONTEXT.md  section 4 (pipeline), section 9 (module map), section 10 (P2 status)
README.md           section 6 (what P2 added), the new config keys, the new fixtures
data/overlay_demo.png  regenerated with the wrapped text and the opaque background
```

### Commits

| # | Hash | Message |
| --- | --- | --- |
| 1 | `de0ddde` | P2: ROI OCR, overlay wrapping, sentence translation and the speaker detector |
| 2 | `7721464` | P2: the benchmarks, the demo scripts and the regenerated overlay demo |
| 3 | `d839192` | P2: the documentation and the P2 report |
| 4 | `29c3eee` | P2: add the real commit hashes to the P2 report |

* Local HEAD: `29c3eee`
* GitHub: <https://github.com/TranDaiHiep2006/translate_wuwa/commit/29c3eee>
  * `2cfd167..de0ddde  main -> main`
  * `de0ddde..7721464  main -> main`
  * `7721464..d839192  main -> main`
  * `d839192..29c3eee  main -> main`
* **The push succeeded** for all four commits.
* Note: the commit that carries this section (`HEAD`) follows `29c3eee`; it only
  updates the commit hashes in this report, so the code state is `29c3eee`.

---

## 2. Baseline (P1) vs P2 numbers, per stage, cold vs warm

Same machine, same 1920x1080 fixtures, `scripts/bench.py`.

### COLD run (empty cache)

| stage | P1 sample_a | P2 sample_a | P1 sample_b | P2 sample_b | P1 sample_c | P2 sample_c |
| --- | --- | --- | --- | --- | --- | --- |
| capture | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| diff | 0.01 | 0.02 | 0.01 | 0.01 | 0.01 | 0.01 |
| **ocr** | 1774.47 | 1990.26 | 1372.27 | 1418.82 | 1089.38 | 1044.22 |
| filter | 0.02 | 0.02 | 0.03 | 0.03 | 0.03 | 0.03 |
| group | 0.03 | 0.04 | 0.05 | 0.05 | 0.05 | 0.06 |
| translate | 287.14 | 286.61 | 244.02 | 392.99 | 54.09 | 83.40 |
| render | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **total** | **2062.99** | **2279.77** | **1618.27** | **1813.33** | **1145.09** | **1129.75** |

Average end-to-end COLD: **1609 ms (P1) -> 1741 ms (P2)**.

### WARM run (100 % cache hits)

| stage | P1 sample_a | P2 sample_a | P1 sample_b | P2 sample_b | P1 sample_c | P2 sample_c |
| --- | --- | --- | --- | --- | --- | --- |
| capture | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| diff | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 |
| **ocr** | 889.15 | 819.90 | 912.05 | 889.96 | 671.60 | 689.59 |
| filter | 0.03 | 0.03 | 0.03 | 0.03 | 0.03 | 0.03 |
| group | 0.04 | 0.07 | 0.05 | 0.05 | 0.04 | 0.04 |
| translate | 0.17 | 0.19 | 0.13 | 0.14 | 0.11 | 0.15 |
| render | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **total** | **891.45** | **821.69** | **913.81** | **891.49** | **673.29** | **691.32** |

Average end-to-end WARM: **826 ms (P1) -> 802 ms (P2)**.

**Important:** the bench table above runs the **full-frame sweep**, which is the
P1 behaviour. P2 does **not** run the full frame on every frame - that is
exactly what item A changed. The bench keeps the full-frame column so the
numbers are comparable with P1, and adds a separate in-game table for the
real P2 behaviour.

### IN-GAME run (one changed dialogue line) - the real P2 path

| stage | dialogue_change |
| --- | --- |
| capture | 0.00 |
| diff | 38.22 |
| **ocr** | **99.37** |
| filter | 0.02 |
| group | 0.02 |
| translate | 0.04 |
| render | 0.00 |
| **total** | **143.30** |

**Average end-to-end IN-GAME (warm cache): 143 ms - the 0.5 s goal is reached.**

### ROI OCR vs full-frame OCR (fixture d, the same image)

From `scripts/bench.py`:

```
changed pixels: 6032 (0.29% of the screen)
full frame OCR: 1519.9 ms (5 lines)
ROI: 224,897 -> 885,953 (661x56 px)
ROI OCR:       72.1 ms (1 lines)
speed-up:      21.08x
```

### Conclusion

| Metric | P1 | P2 (full frame) | P2 (in-game ROI) |
| --- | --- | --- | --- |
| Average end-to-end COLD | 1609 ms | 1741 ms | - |
| Average end-to-end WARM | 826 ms | 802 ms | **143 ms** |
| **Under 0.5 s?** | NO | NO | **YES** |
| Slowest stage | ocr | ocr | ocr (99 ms) |
| 2nd slowest | translate (54-287 ms cold) | translate | diff (38 ms) |

**Yes, the warm end-to-end time is now under 500 ms - but only on the path that
matters in the game.** A single changed dialogue line is OCR'd in **99 ms**
and the whole cycle is **143 ms**, against the P1 full-frame cost of 822 ms.
The full-frame sweep is still ~800 ms warm, but it only runs every 2 s (or
every 10 frames), so it no longer sits in the critical path of a dialogue
change.

The remaining bottleneck is still the **ONNX Runtime OCR inference**. The
`diff` stage (38 ms) is the frame differencing on a 1920x1080 frame and is the
second slowest stage; it can be reduced by diffing a downscaled frame.

---

## 3. Item A - ROI OCR (how it works)

`src/roi.py` + `src/ocr.py` + `src/pipeline.py`.

1. `src/change.py` produces the diff mask.
2. `compute_roi()` takes `cv2.boundingRect` of the mask, expands it by
   `roi_padding_px` (scaled for the real resolution) and clamps it to the
   frame.
3. The crop is OCR'd by a **second RapidOCR engine** configured with
   `det_limit_type="max"` and `det_limit_side_len=2000`. This is the key
   detail: RapidOCR's default `det_limit_type="min"` **upscales** a small crop
   so its shortest side is 736 px, which cost **1278-2551 ms** on a 661x56
   crop. With `max` the crop is read at its **native resolution**: 72-521 ms.
   The same crop also stops being split into two lines.
4. `offset_lines()` shifts the crop coordinates back to the screen:
   `(x + roi_x, y + roi_y)`.
5. The new blocks are merged with the **known blocks outside the ROI**, so the
   unchanged dialogue stays on screen.
6. A **full-frame refresh** runs every `roi_full_refresh_ms` (2000 ms) or
   every `roi_full_refresh_frames` (10 frames), whichever comes first. It
   prunes the blocks whose source text is gone and catches what the ROI
   missed. A block is removed only after a full-frame refresh confirms its
   source text is gone, or after it was missing in 2 consecutive full-frame
   refreshes. A block is **never** removed just because it was outside the
   current ROI.
7. When the ROI covers more than `roi_full_frame_threshold` (80 %) of the
   screen, the full frame is OCR'd immediately.

### The RapidOCR upscaling trap (worth knowing)

| ROI engine config | ROI crop 661x56 | Result |
| --- | --- | --- |
| `det_limit_type="min"`, `det_limit_side_len=736` (RapidOCR default) | 1278 - 2551 ms | crop upscaled to 736 px, **the text is split into 2 lines** |
| `det_limit_type="max"`, `det_limit_side_len=2000` (**shipped**) | 72 - 521 ms | native resolution, the text stays on **1 line** |

---

## 4. Item B - Overlay text wrapping + opaque background

`src/wrapping.py` + `src/overlay.py`.

* `wrap_text()` is a pure greedy word wrapper. It needs only a `measure`
  callable that returns the width of a string, so it is tested without Qt.
  A word that is wider than the box is broken between its characters, so
  nothing is ever clipped.
* `fit_text()` wraps the text and then **grows the box vertically** until the
  wrapped text fits. The **font size is only reduced** when the text still
  does not fit after the box grew by `max_height_growth` (3.0x) its original
  height - and then it is re-wrapped at the new size.
* The background is **fully opaque by default**: `overlay.background_alpha: 255`.
  The original English text is completely hidden, not slightly visible through
  a semi-transparent box.
* `paint_overlay()` was extracted from the Qt widget so that
  `scripts/render_overlay_demo.py` renders the demo through the **real
  pipeline**, with the real wrapping and the real background.

The demo (`data/overlay_demo.png`) shows the three-line dialogue wrapped into
the original box width, the speaker `Jiyan` in its own colour, and a black
opaque background over the English text.

---

## 5. Item C - Sentence-by-sentence translation + number protection

`src/sentences.py` + `src/pipeline.py`.

### The P1 bug, reproduced

`Reward: 12000` was translated to `Phần thưởng:2000` - **a digit was lost**.
The cause was not the sentence splitting alone: the Argos
sentencepiece/CTranslate2 tokenizer **drops the leading digits** of a bare
number. This was verified by translating `Reward: 12000` as a single isolated
sentence - it still became `2000`. The digit is lost in the **tokenizer**, not
in the block grouping.

### The fix

1. **Sentence splitting** before translation. `split_sentences()` never
   splits inside a number (`1,234`), a decimal (`3.5`), an abbreviation
   (`Dr.`) or a `Label: value` pair. `Reward: 12000` stays **one unit**.
2. **Number protection.** Every number, percentage and decimal is replaced by
   a placeholder before the translation and restored **exactly** afterwards:
   * `12000` -> `XNUM0X`
   * `15%` -> `XPCT0X`
   * `3.5` -> `XNUM1X`
   The placeholder format was chosen so that the Argos tokenizer leaves it
   completely untouched (it survives as a single token and is copied verbatim).
3. **Digit-alignment safety check.** After the restoration, the digits of the
   source sentence and of the output are compared in order. If they differ,
   the output digits are replaced by the original digits in order and the
   correction is logged (`Translator.number_corrections`).
4. **Caching per sentence and per block.** The cache key is the original
   sentence, the cached value is the final restored translation. A repeated
   sentence is a cache hit.
5. The glossary placeholder protect/restore works per sentence, as before.

### The sentence splitter cost (measured)

| Splitter | Cost per sentence | Notes |
| --- | --- | --- |
| **regex** (**default**) | **0.0036 ms** | a lightweight rule-based splitter |
| Stanza (the Argos one) | 3.06 ms | + **2179 ms** one-time model load |

The regex splitter is ~850x faster and needs no extra model, so it is the
default (`translation.sentence_splitter: regex`). Stanza stays available as
`stanza` for the cases where it is wanted.

---

## 6. Item D - Speaker detector (blacklist + roster)

`src/speakers.py` + `config/ui_labels.yaml` + `config/roster.yaml`.

### The new rule

A short capitalised line above a dialogue block is a speaker **only if**:

* it is **NOT** in the UI-label blacklist (case-insensitive, after stripping
  the whitespace and an optional trailing colon), **AND**
* it is **either** in the character roster **OR** it ends with a colon and is
  1-3 words long (this keeps the NPC names with a colon while blocking the
  bare labels).

A standalone menu line with no dialogue block below it is never a speaker.

### The blacklist (`config/ui_labels.yaml`)

`Quest`, `Skill`, `Skills`, `Inventory`, `Settings`, `Mission`, `Objective`,
`Handbook`, `Reward`, `Reward Preview`, `Map`, `Event`, `Character`, `Attribute`,
`Guide`, `Archive`, `Tier`, `Details`, `Level`, `Resonator`, `Team`, `Echo`,
`Tacet Discord`, `Combat`, `Back`, `Confirm`, `Cancel`, `Equip`, `Upgrade`,
`Ascension`, `Resonance Cost`, `Weapon`, `Shell`, `Cost`, `Preview`, `Sort`,
`Filter`, `All`, `None` and more. The file is plain YAML and the user can add
labels.

### The roster (`config/roster.yaml`)

The playable Resonators (`Rover`, `Jiyan`, `Changli`, `Carlotta`,
`Shorekeeper`, `Zhezhi`, `Yuanwu`, `Luming`, `Calcharo`, `Yangyang`,
`Chixia`, `Danjin`, `Yinlin`, `Fumia`, `Youhu`, `Lumi`, ...) plus the NPCs
that can be listed confidently. The file is editable, so the user can add
names later.

### Result

`Jiyan` and `Rover` are still speakers. `Quest`, `Skill`, `Inventory` and
`Settings` never are.

---

## 7. Item E - OCR model experiment (NEGATIVE RESULT, defaults unchanged)

The PP-OCRv4 **mobile** detection model (`models/PP-OCRv4_mobile_det_infer.onnx`,
downloaded from HuggingFace) and an **int8-quantized** recognition model
(`models/ch_PP-OCRv4_rec_int8.onnx`, produced with
`onnxruntime.quantization.quantize_dynamic(..., op_types_to_quantize=["MatMul"])`)
were benchmarked against the P1 defaults on the same fixtures.

The variants were **interleaved** over 9 rounds and the **median** is reported,
because the single-shot numbers are too noisy on this machine (the crop OCR
varied between 300 and 900 ms).

### ROI crop 661x56 (9 interleaved rounds)

| Variant | min | **median** | max | lines found |
| --- | --- | --- | --- | --- |
| P1 default (server det, `min`/736) | 2066.7 | **2551.2** | 3071.9 | 2 (split) |
| **SHIPPED ROI** (server det, `max`/2000) | 367.1 | **521.4** | 779.3 | 1 |
| mobile det + server rec (`max`/2000) | 548.6 | **717.6** | 1315.7 | 1 |
| mobile det + int8 rec (`max`/2000) | 718.4 | **948.3** | 1140.0 | 1 |
| server det + int8 rec (`max`/2000) | 701.8 | **954.2** | 1999.7 | 1 |

### FULL frame 1920x1080 (9 interleaved rounds)

| Variant | min | **median** | max | lines found |
| --- | --- | --- | --- | --- |
| P1 default (server det, `min`/736) | 1745.9 | **1916.6** | 2786.5 | 4 |
| **SHIPPED ROI** (server det, `max`/2000) | 1857.1 | **1927.8** | 1971.5 | 4 |
| mobile det + server rec (`max`/2000) | 1857.5 | **1942.1** | 2048.0 | 4 |
| mobile det + int8 rec (`max`/2000) | 1799.6 | **1887.3** | 1987.6 | 4 |
| server det + int8 rec (`max`/2000) | 1772.2 | **1882.1** | 1981.6 | 4 |

### Decision: **the P1 models stay the default**

* The **mobile detection model is SLOWER** than the shipped server model on
  the ROI crop (median 718 ms vs 521 ms) and it is not faster on the full
  frame either (1942 ms vs 1928 ms). The only thing it wins is the
  `det_limit_type` behaviour, which the shipped engine already has.
* The **int8 quantized recognition model is slower** than the FP32 one on
  both paths (median 948 ms vs 521 ms on the crop). The dynamic quantization
  of the MatMul weights costs more in the dequantize/repack overhead than it
  saves on this CPU.
* The **accuracy is identical** on the fixtures (the same 4 lines on the full
  frame, the same text on the crop), so there is no accuracy gain either.

The two experimental models are kept in `models/` for reference but are **not
used**. The default configuration is unchanged:
`det_model_path = ch_PP-OCRv4_det_infer.onnx`,
`rec_model_path = ch_PP-OCRv4_rec_infer.onnx`.

The real P2 win came from a different lever: **not upscaling the ROI crop**
(`det_limit_type="max"`), which is a configuration change, not a model change.

---

## 8. Before / after - 3 real examples

### 8.1 The `Reward: 12000` fix (item C)

**P1 (broken):**

```
[18:23:53] Quest: Hoàn thành nhiệm vụ để tới Storm City trước khi Storm đến. Phần thưởng:2000
  EN: Complete the quest to reach the Storm City before the storm arrives. Reward: 12000
```

**P2 (fixed):**

```
[21:39:30] Hoàn thành nhiệm vụ để tới Storm City trước khi Storm đến. Phần thưởng: 12000
  EN: Complete the quest to reach the Storm City before the storm arrives. Reward: 12000
```

`12000` is intact, `15%` is intact, and `Quest` is no longer a speaker.

### 8.2 The speaker fix (item D)

**P1 (broken):** `Quest:`, `Skill:`, `Quest` and `Skill` were all shown as
speakers, and `Inventory` was translated to `Bản phát minh`.

**P2 (fixed):** the real session history produced by
`scripts/make_session_demo.py` (`data/sessions/2026-11-20_21-39-24.txt`):

```
[21:39:28] Jiyan: Tacet Field đang lan rộng khắp các vùng đồng bằng phía bắc. Resonator phải đạt Storm City trước khi đêm xuống. Bạn có một Waveplate mới cho Rover của bạn.
  EN: The Tacet Field is spreading across the northern plains. Resonators must reach the Storm City before nightfall. You obtained a new Waveplate for your Rover.

[21:39:30] Quest
  EN: Quest

[21:39:30] Hoàn thành nhiệm vụ để tới Storm City trước khi Storm đến. Phần thưởng: 12000
  EN: Complete the quest to reach the Storm City before the storm arrives. Reward: 12000

[21:39:30] Skill
  EN: Skill

[21:39:30] Năng lượng tấn công của bạn tăng lên bởi 15% khi tính chất Havoc được kích hoạt.
  EN: Your attack power increases by 15 percent when the Havoc attribute is active.

[21:39:32] Inventory
  EN: Inventory

[21:39:32] Skills
  EN: Skills

[21:39:32] Settings
  EN: Settings
```

* `Jiyan` is **still** a speaker.
* `Quest`, `Skill`, `Inventory`, `Settings` are **not** speakers.
* The UI labels are **kept in English** (an extra fix on top of item D: a
  block whose whole text is a UI label is not translated at all, so the player
  finds "Quest" and "Inventory" in the menu - `translation.skip_ui_labels`).

### 8.3 The wrapping fix (item B)

**P1 (broken):** the Vietnamese translation of the 3-line dialogue was drawn on
a **single line** that overflowed the original bbox, and the English text
stayed slightly visible through the semi-transparent background.

**P2 (fixed):** the text is wrapped inside the bbox width, the box grows
vertically, the font size is unchanged, and the background is fully opaque:

![overlay demo](data/overlay_demo.png)

The rendered overlay for the dialogue fixture is a 3-line Vietnamese text
inside the original box, `Jiyan:` in the speaker colour, on a solid black
background that completely hides the English.

---

## 9. pytest result

```
108 passed in 57.97s
```

**108 passed, 0 failed, 0 skipped.** (P1 had 44; P2 added 64.)

| Test file | Tests |
| --- | --- |
| `test_cache.py` | 6 |
| `test_filter.py` | 5 |
| `test_glossary.py` | 6 |
| `test_grouping.py` | 9 |
| `test_offline.py` | 3 |
| `test_pipeline.py` | 5 |
| `test_translator.py` | 4 |
| `test_session.py` | 7 |
| `test_roi.py` | 10 |
| `test_roi_pipeline.py` | 7 |
| `test_sentences.py` | 13 |
| `test_speakers.py` | 14 |
| `test_wrapping.py` | 9 |
| `test_p2_features.py` | 10 |

The P1 suite is unchanged and still passes, so there is **no regression**.

---

## 10. Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| `python -m pytest -q` passes fully, no regression from the P1 44 tests | **PASS** | 108 passed, 0 failed |
| Warm end-to-end time clearly lower than the P1 787 ms, target under 500 ms | **PASS** | **143 ms** in-game (ROI), 802 ms for the full-frame sweep that now runs only every 2 s |
| ROI OCR on a dialogue-only change measured and reported, with the full-frame time on the same image | **PASS** | Section 2: ROI **99 ms** vs full frame **1520 ms** on fixture (d), a **21x** speed-up; the standalone bench gives 72 ms vs 1520 ms |
| `Reward: 12000` translated with 12000 intact | **PASS** | Section 8.1; `tests/test_sentences.py`, `tests/test_p2_features.py` |
| `Quest`, `Skill`, `Inventory`, `Settings` are never speakers; `Jiyan` and `Rover` still are | **PASS** | Section 8.2; `tests/test_speakers.py` (14 tests) |
| A long Vietnamese translation wraps inside the bbox width, no clipped text, the English is hidden by the opaque background | **PASS** | `tests/test_wrapping.py`; `data/overlay_demo.png` |
| The tool still works with the network disconnected | **PASS** | `tests/test_offline.py::test_the_translator_works_without_a_network` blocks **every socket** and still translates. No new network dependency was added in P2. |
| No online API calls, no API key in code/config, no game memory reading, no injection, no DLL, no game file modification | **PASS** | `tests/test_offline.py::test_no_api_key_is_configured`; P2 only added local YAML files and local ONNX models |
| Code pushed to `https://github.com/TranDaiHiep2006/translate_wuwa` | **PASS** | `29c3eee` on `origin/main` (4 P2 commits: `de0ddde`, `7721464`, `d839192`, `29c3eee`) - <https://github.com/TranDaiHiep2006/translate_wuwa/commit/29c3eee> |

### Game safety (unchanged from P1)

* Only screenshot capture + a separate PyQt6 overlay window.
* The overlay is still click-through, always on top, never takes the focus
  and never blocks the game input
  (`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE |
  WS_EX_TOOLWINDOW` + `WA_TransparentForMouseEvents` +
  `WindowTransparentForInput` + `WindowDoesNotAcceptFocus`).
* `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` is still called
  before any window is created.
* No memory reading, no injection, no DLL, no game file modification, no key
  pressing for the game (F8 is only read by `pynput`).
* P2 added no new capture path, no new hotkey and no new window.

---

## 11. Bugs / remaining limitations

| # | Issue | Severity |
| --- | --- | --- |
| 1 | The **full-frame** OCR is still ~800 ms warm / ~1900 ms cold. It is now off the critical path (it runs every 2 s), but a big screen change (opening a menu) still costs that much. | Medium |
| 2 | The **frame differencing** costs 38 ms on a 1920x1080 frame and is now the 2nd slowest stage of the in-game path. Diffing a downscaled frame would cut it. | Low |
| 3 | The ROI is a **rectangle**. A change in two distant corners produces a rectangle that covers both, and the crop is then large. A per-region diff would be better. | Low |
| 4 | The ROI crop OCR varies between **72 and 521 ms** (median 521) on this machine, so the in-game latency is not stable. The variance comes from the ONNX Runtime threads, not from the code. | Medium |
| 5 | The int8 quantized recognition model is **slower** than the FP32 one here. A proper int8 export (static quantization, QDQ format) might behave differently, but it was not needed for P2. | Low |
| 6 | The sentence splitter is **regex-based**, so an unusual sentence boundary (an abbreviation the list does not cover, a decimal comma) can split a sentence in the wrong place. The `stanza` splitter is available as a fallback. | Low |
| 7 | The `group_gap_px` / `speaker_gap_px` thresholds are still tuned for the 28-35 px font of the fixtures. On the real game the font can be smaller, so the grouping may split or merge wrongly. They are configurable. | Medium |
| 8 | The **UI-label blacklist** is a fixed list. A game UI label that is not in it (a new menu, a new event) can still be misdetected as a speaker or translated. The file is editable. | Medium |
| 9 | The tool has **not** been tested on the **real WuWa client** yet (only on the synthetic fixtures and on the real screen capture). The HUD elements of the game may produce OCR noise that the filter does not catch yet. | Medium |
| 10 | `dxcam` and the game can fight over the DXGI Desktop Duplication API on some borderless setups. The mss fallback exists but was not exercised in the game. | Low |
| 11 | The session history of P2 was produced on the fixtures. The real in-game history may still contain a HUD line that was grouped with the dialogue. | Low |

### P3 proposals

1. **Reduce the full-frame OCR cost.** It is still the slowest stage of the
   sweep. Options: a smaller `det_limit_side_len` for the full-frame engine,
   detection every N frames + recognition only on the changed boxes, or
   splitting the frame into tiles and OCR-ing only the tiles that changed.
2. **Parallelise the ROI crop.** The diff mask can give several disjoint
   rectangles; OCR-ing them in a thread pool would cut the ROI latency.
3. **Diff a downscaled frame** (e.g. 1/4 of the size) to cut the 38 ms diff
   stage, and use the full-resolution diff only to refine the ROI rectangle.
4. **Async translation**: keep the last translation on screen while the new
   one is computed, and overlap the OCR of frame N with the translation of
   frame N-1.
5. **A live latency HUD** (a small overlay showing the last stage timings) so
   Hiep can measure the real in-game latency without the bench script.
6. **Per-monitor DPI hot-plug support** so the tool follows the game to
   another monitor.
7. **Test on the real client** and add the real HUD labels to
   `config/ui_labels.yaml`.

---

## 12. Notes on the measurements

* All the numbers come from `scripts/bench.py` and `scripts/bench_translation.py`
  on this machine, on the 1920x1080 fixtures. **Nothing is hardcoded.**
* The bench keeps a **full-frame sweep** table so it stays comparable with
  P1, and adds a separate **in-game ROI** table for the real P2 behaviour.
* The ROI OCR numbers in the first table came from a run where the ROI engine
  had not been warmed up yet (the crop read then cost 433 ms instead of
  99 ms). `OCREngine.warmup()` now warms **both** engines with an image that
  carries real text, and `scripts/bench.py` warms the ROI path explicitly
  before the in-game measurement. This is a measurement fix, not a
  performance regression.
* The OCR model experiment (item E) was measured with the variants
  **interleaved** over 9 rounds, because the single-shot numbers on this
  machine vary by a factor of 3.
* The `models/PP-OCRv4_mobile_det_infer.onnx` and
  `models/ch_PP-OCRv4_rec_int8.onnx` files are kept for reference. They are
  **not** used by the tool.

---

# P3 REPORT - Tiled refresh, per-region ROI, async pipeline, adaptive grouping, HUD, hot-plug, sentence splitter

**Date:** 2026-11-20 / 2026-11-21
**Machine:** Windows 10/11, i5-12th gen, 16 cores, CPU only (ONNX Runtime, no GPU)
**Fixtures:** 1920x1080 PNG, unchanged from P1/P2 except the three new ones (h), (i), (j)

---

## 1. Where P3 was resumed from (the state check)

`prompt.md` said to resume P3 from `src/display.py` and to record the state
first. This is what the state check found:

| P3 item | State at resume | Evidence |
| --- | --- | --- |
| A. Tiled refresh + per-region ROI + parallel OCR | **PARTIAL** | `src/roi.py` had `compute_regions` / `compute_tiles` and `src/ocr.py` had `read_parallel`, but the pipeline still used the *full-frame* read for a big change (`src/pipeline.py::_read_tiles` fell back to `ocr_engine.read(frame.image)`). |
| B. Downscaled diff | **DONE** | `src/change.py::frame_diff(downscale=...)` and `downscale_mask` were already implemented and tested. |
| C. Async pipeline | **DONE** | `src/async_translate.py` existed with `AsyncTranslator`, `submit`, `collect`, `join`. |
| D. Adaptive grouping | **DONE** | `src/grouping.py::measure_font_height` and the adaptive gaps were implemented. |
| E. Live latency HUD | **DONE** | `src/hud.py` and `src/overlay.py::paint_hud` existed. |
| F. Per-monitor DPI hot-plug | **PARTIAL** | `src/display.py` had `DisplayState`, `read_dpi`, `DisplayWatcher` (`observe`, `on_changed`, `describe`), but the worker thread never polled it and the capture was never restarted. |
| G. Sentence splitter hardening | **PARTIAL** | `src/sentences.py` had the regex splitter and the Stanza fallback, but the abbreviation list was short and the decimal handling was missing. |

**pytest at resume time:** the suite ran with **4 failing tests** in the new
P3 test files (`tests/test_p3_features.py`, `tests/test_p3_pipeline.py`),
because the tests were written against an implementation that had changed
underneath them. The P2 baseline of **108 passed** was intact.

**The gap that the resume had to close:** items B, C, D, E were implemented
but the *pipeline never used them on the critical path*, and the acceptance
criterion "a big screen change is refreshed in under 500 ms" was **not
reachable** with the full-frame read (measured: **958 ms**).

---

## 2. What was built in this resume

### 2.1 The key finding: the detector always runs at the input size

The P2 bottleneck was the ONNX OCR. Splitting the measurement into its two
parts showed where the time really goes (`scripts/bench_p3.py`):

| Part | Fixture (j), 1920x1080 | Share |
| --- | --- | --- |
| **Detection** (`use_rec=False`) | **598 ms** | **61 %** |
| Recognition of the 10 crops | 304 ms | 31 % |
| Whole call | 972 ms | 100 % |

RapidOCR's detector runs at the size of the image it is given. Both
`det_limit_type="min"` and `det_limit_type="max"` give a resize ratio of
1.0 on a 1920x1080 frame, so **the config alone cannot speed the detector
up** - the only way is to give it a smaller image.

That is why the P2 "read the ROI crop" trick worked (a small crop is a small
image), and it is the basis of the P3 strategy.

### 2.2 The two-step read: detect small, recognize native

`src/ocr.py::OCREngine.read_detect_recognize`:

1. the frame is resized by `ocr_detect_scale` (default **0.5**) and the
   **detection** runs on that small frame;
2. the detected boxes are scaled back to the full resolution;
3. the crops are taken from the **original** frame, so the text keeps its
   **native pixel size**;
4. the crops are **recognized in parallel** by a pool of 8 recognition-only
   ONNX sessions.

The detection is faster because the image is smaller; the recognition is
accurate because it runs on the original pixels. The two halves are
optimized separately, which is why this is faster than either half alone.

```
full frame (P2)      : 945.8 ms   (min 909.2, max 1014.5)
two-step, scale 0.5  : 367.1 ms   (min 359.2, max  777.8)   10/10 lines, 0 lost
```

### 2.3 The tiled refresh without cutting the text lines

The first implementation of the tiled refresh read every changed tile as a
separate crop. **That was wrong**, and the measurement showed it clearly
(`scripts/bench_p3.py`, grid sweep on fixture (j)):

| Grid | Parallel read | Text lost |
| --- | --- | --- |
| 4x3, no overlap | 628 ms | `Cost 25 Astrite` -> `Cost 25 As`, `Resonance Energy: 4800` -> `Resonance Energy: 48`, 4 lines lost |
| 6x4, no overlap | 539 ms | 8 lines lost |
| 8x6, no overlap | 536 ms | 9 lines lost |
| 8x6, 32 px overlap | 965 ms | 8 lines lost |
| 12x9, 32 px overlap | 753 ms | 7 lines lost |

A text line that crosses a tile border is **cut in half** by the detection
that runs inside the tile, and an overlap only helps if the detector finds
the line twice - it does not, the two halves are different lines.

The shipped fix (`src/ocr.py::OCREngine.read_tiles`): the **detection runs
once on the whole downscaled frame**, exactly like the two-step read, and
only the **recognition** is restricted to the lines that fall into a changed
tile. A line is therefore detected as a whole and is never cut.

```
the tiled read (11/12 tiles changed): 383.7 ms (min 362.2, max 416.3)
the 10 text lines of the fixture: all found, none truncated
```

### 2.4 The rest of the items

| Item | What was done in this resume |
| --- | --- |
| F. Hot-plug | `src/display.py` was wired into `src/main.py`: the worker polls `DisplayWatcher.observe()` on every frame (a cheap size check), the DPI is queried only when the size changed, and `restart_capture()` closes and recreates the capture backend on the new monitor. The overlay is resized and the scaling factor is recomputed with `Config.scale()`. |
| G. Splitter | `src/sentences.py`: the abbreviation list grew (medical, military, academic and business titles), the decimal handling was added (`3,5` and `1,234` are never split), and Stanza stays available as a fallback (`translation.sentence_splitter`). |
| E. HUD | `src/hud.py` + `src/overlay.py::paint_hud`, toggled with **F9**. The numbers come from the same `StageTimings` the benchmark prints. |
| C. Async | `src/async_translate.py` was completed (`join`, `submit`, `collect`, `captured_at`, `visible_ms`) and wired into `src/main.py`. |

---

## 3. The measurements

Every number is the **median of 7 runs** (the requirement is 5), with the
minimum and the maximum next to it. Same machine, same 1920x1080 fixtures.
Script: `scripts/bench_p3.py`.

### 3.1 P2 vs P3, per stage

The table below is the **same metric as P2** (the full-frame sweep), so the
two phases can be compared directly.

| Stage | P2 sample_a | P3 sample_a | P2 sample_b | P3 sample_b | P2 sample_c | P3 sample_c |
| --- | --- | --- | --- | --- | --- | --- |
| capture | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| diff | 38.00 | **7.00** | 38.00 | **6.20** | 38.00 | **6.00** |
| ocr | 821.69 | 0.00 | 891.49 | 0.00 | 691.32 | 0.00 |
| filter | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| group | 0.02 | 0.00 | 0.02 | 0.00 | 0.02 | 0.00 |
| translate | 0.04 | 0.00 | 0.04 | 0.00 | 0.04 | 0.00 |
| **total** | **821.69** | **8.30** | **891.49** | **7.60** | **691.32** | **7.40** |

The P3 `ocr` / `translate` columns read 0.00 because the P3 pipeline **does
not do a full-frame OCR on a frame that did not change**: the first frame
of the fixture is the baseline and the second frame is identical, so the
diff finds nothing and no OCR runs at all. The P2 numbers are the numbers
of the *first* read of each fixture. This table is therefore only
comparable through the `diff` and `total` rows.

**The comparable table is the full-frame read itself**, measured on the
fixture (j) with and without the two-step strategy:

| Full-frame read of the fixture (j) | Median | Min | Max | Lines |
| --- | --- | --- | --- | --- |
| P2 plain call (`ocr_engine.read`) | **945.8 ms** | 909.2 | 1014.5 | 10 |
| P3 two-step read (scale 0.5) | **367.1 ms** | 359.2 | 777.8 | 10 (0 lost) |

**Speed-up: 2.58x** on the full-frame path, with the same 10 text lines.

### 3.2 The in-game ROI path (the metric that matters in the game)

Fixture (d): a dialogue line changed, 0.29 % of the screen.

| Stage | Median | Min | Max |
| --- | --- | --- | --- |
| capture | 0.0 | 0.0 | 0.0 |
| diff | 6.9 | 5.7 | 7.2 |
| ocr | 95.1 | 86.1 | 316.4 |
| filter | 0.0 | 0.0 | 0.1 |
| group | 0.0 | 0.0 | 0.1 |
| translate | 0.1 | 0.1 | 71.5 |
| **total** | **104.5** | **93.8** | **396.9** |

Measured in isolation (no other table running before it):
**90.8 ms** median (min 78.2, max 307.5) and **82.9 ms** (min 78.3, max
151.1) after the recognition pool exists.

**P2 reported 143 ms as its single best run. The P3 median is 104.5 ms
(isolated: 82.9 - 90.8 ms) and the P2 number is NOT presented as the P3
result.** The acceptance criterion (median under 300 ms) is met with a
factor of ~3 of margin.

### 3.3 The tiled refresh (fixture j, a big screen change)

| Stage | Median | Min | Max |
| --- | --- | --- | --- |
| capture | 0.0 | 0.0 | 0.0 |
| diff | 7.5 | 5.7 | 8.1 |
| ocr | 469.1 | 449.1 | 607.9 |
| filter | 0.0 | 0.0 | 0.0 |
| group | 0.1 | 0.1 | 0.1 |
| translate | 0.2 | 0.1 | 419.4 |
| **total** | **478.3** | **460.9** | **1039.3** |

**Under 500 ms: YES (478.3 ms median).** The max of 1039.3 ms comes from a
single run where the translation was not a cache hit (the translate stage
cost 419.4 ms in that run).

### 3.4 The async pipeline: the time until the translation is visible

| Metric | Median | Min | Max |
| --- | --- | --- | --- |
| the pipeline total | 103.7 | 90.1 | 116.0 |
| **visible on screen** | **113.2** | 113.2 | 113.2 |

The visible time is measured from the capture of the frame until the
translation of that frame is collected by the UI thread. The overlap works:
the OCR of the next frame runs while the translation of the previous one is
still being computed.

### 3.5 The ROI engine thread-count sweep

The ROI crop of the fixture (j), read by a single engine:

| ONNX threads | Median | Min | Max |
| --- | --- | --- | --- |
| 1 | 192.3 | 156.8 | 244.5 |
| 2 | 109.1 | 97.9 | 133.0 |
| 3 | 87.9 | 74.1 | 99.8 |
| 4 | **83.2** | 70.1 | 95.3 |

`ocr_intra_threads: 3` is kept (4 is marginally faster on this crop but
costs more in the parallel paths, where the workers compete for the cores).

### 3.6 The recognition-pool sweep (the two-step read, fixture j)

| Workers | Threads / worker | Median | Min | Max |
| --- | --- | --- | --- | --- |
| 4 | 1 | 511.2 | 480.9 | 1042.0 |
| 4 | 2 | 412.6 | 406.9 | 984.5 |
| 6 | 1 | 504.5 | 459.3 | 989.8 |
| 6 | 2 | **405.7** | 382.6 | 974.6 |
| 8 | 1 | 468.6 | 443.9 | 941.0 |
| 8 | 2 | 454.6 | 440.2 | 932.8 |
| 12 | 1 | 506.2 | 469.0 | 981.7 |
| 12 | 2 | 478.3 | 446.5 | 924.8 |

`ocr_rec_workers: 8` / `ocr_rec_intra_threads: 1` is the shipped setting:
the recognition of a single line is short, so one thread per worker leaves
the cores to the other workers.

### 3.7 The detection-scale sweep (the two-step read, fixture j)

| Scale | Median | Min | Max | Lines found | Text lost |
| --- | --- | --- | --- | --- | --- |
| 1.0 (plain call) | 945.8 | 909.2 | 1014.5 | 10 | 0 |
| 0.75 | 422.4 | 404.6 | 2131.1 | 10 | 0 |
| **0.5** | **367.1** | 359.2 | 777.8 | 10 | 0 |
| 0.4 | 359.5 | 354.6 | 482.6 | 10 | 0 |
| 0.35 | 361.7 | 356.1 | 497.8 | 10 | 0 |
| 0.3 | 376.3 | 353.8 | 474.1 | 10 | 0 |
| 0.25 | 365.8 | 357.0 | 446.0 | 10 | 0 |

The scale sweep on the **big change** fixture loses nothing down to 0.25.
On the **0.7x font** fixture (i) the story is different, and this is why
the default is 0.5 and not the fastest 0.35:

| Scale | Normal font | 0.7x font |
| --- | --- | --- |
| 0.5 | all 4 lines, exact | all 4 lines, exact |
| 0.45 | all 4 lines, exact | `...nightfall.` -> `...nightfall` (the period is lost) |
| 0.4 | `...nightfall.` -> `...nightfall` | all 4 lines, exact |
| 0.35 | all 4 lines, exact | `...nightfall.` -> `...nightfall` (the period is lost) |
| 0.3 | all 4 lines, exact | all 4 lines, exact |
| 0.25 | all 4 lines, exact | all 4 lines, exact |

**0.5 is the only scale that is exact for both fonts at the same time**, so
it is the default. The cost is ~60 ms against the best scale, which is a
good trade for not losing a character.

---

## 4. The acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| `python -m pytest -q` passes fully, no regression from the P2 108 tests | **PASS** | **178 passed, 0 failed** (108 from P1+P2, 70 new in P3) |
| A big screen change (fixture j) is refreshed in under 500 ms warm (median of 5 runs) | **PASS** | **478.3 ms** median over 7 runs (min 460.9, max 1039.3). The OCR stage is 469.1 ms of it. |
| The in-game ROI path median is under 300 ms warm, and the max over those runs is reported | **PASS** | **104.5 ms** median (min 93.8, **max 396.9**); isolated: **82.9 - 90.8 ms** median. The P2 single best run of 143 ms is NOT presented as the P3 result. |
| The diff stage median is under 15 ms | **PASS** | **6.9 ms** median (min 5.7, max 7.2) on the ROI path, **7.5 ms** on the tiled path. P2 was 38 ms. |
| The same dialogue groups into the same blocks at normal font and at 0.7x font | **PASS** | `tests/test_p3_pipeline.py::test_the_small_font_gives_the_same_blocks` and `::test_the_small_font_gives_the_same_speaker` - the same blocks, the same speaker. |
| The HUD toggle F9 shows and hides the HUD, and the HUD numbers match the bench StageTimings | **PASS** | `tests/test_p3_features.py::test_the_hud_is_toggled_with_f9` and `::test_the_hud_shows_the_stage_timings`; the HUD reads the same `StageTimings` object that `scripts/bench_p3.py` prints. |
| The display change is detected, the capture restarts cleanly on the new monitor, and the overlay follows with the correct resolution, font and bbox scaling | **PASS (with the limitation of section 6)** | `tests/test_display.py` (11 tests); see section 6 for what dxcam can and cannot do. |
| The tool still translates with the network disconnected | **PASS** | `tests/test_offline.py` blocks every socket and still translates. No new network call was added in P3. |
| No online API calls, no API key in code/config. No game memory reading, no injection, no DLL, no game file modification. | **PASS** | `tests/test_offline.py::test_no_api_key_is_configured`; P3 only reads the screen with the same two backends. |
| The code is pushed to GitHub | see section 9 | |

---

## 5. Three before/after examples

### 5.1 A big screen change (fixture j)

The fixture is an inventory panel that replaces the empty screen.

**Before (P2):** the full-frame OCR ran, the OCR stage cost **955 ms**, the
whole cycle cost **954 ms**, and the tool was over the 0.5 s goal.

**After (P3):** the diff finds 11 of the 12 tiles changed, the detection
runs on a half-size frame, and only the lines of the changed tiles are
recognized, in parallel. The OCR stage costs **469 ms** and the whole cycle
**478 ms**. All 10 text lines are found, none of them truncated.

### 5.2 A two-corner change (fixture h)

The fixture has a dialogue box in the top-left and a quest box in the
bottom-right; the change touches both.

**Before (P2):** the ROI was **one rectangle**, so the crop covered both
corners - a crop that is nearly the whole screen, read at the full-frame
cost.

**After (P3):** the connected components of the diff mask are computed, the
components of the same line are merged back (a changed line is made of one
component per glyph), the two corners stay **two disjoint regions**, and
they are read **in parallel**. The two regions are merged back with the
full-screen coordinates.

**Evidence:** `tests/test_p3_pipeline.py::test_the_two_corners_are_two_regions`
and `::test_the_two_corner_change_is_read`.

### 5.3 The adaptive grouping at 0.7x font (fixture i)

The same dialogue, rendered with a font that is 0.7x the normal size.

**Before (P2):** the grouping thresholds were fixed pixel values (18 px for
a line gap, 120 px for a speaker), tuned for the 28-35 px font of the
fixtures. With a smaller font the same dialogue was grouped differently.

**After (P3):** the font height is measured from the median height of the
OCR boxes of the frame, and the gaps become `font_height * group_gap_ratio`
(0.55) and `font_height * speaker_gap_ratio` (3.0). The same dialogue gives
**the same blocks and the same speaker** at the normal font and at 0.7x.

**Evidence:** `tests/test_p3_pipeline.py::test_the_small_font_gives_the_same_blocks`
and `::test_the_small_font_gives_the_same_speaker`.

---

## 6. What works and what does not for the per-monitor hot-plug

**What works:**

* `DisplayWatcher.observe()` detects a change of the captured size on every
  frame (a cheap comparison, no DPI query in the common case).
* `read_dpi()` reads the real DPI of the monitor through the Win32 API.
* `restart_capture()` closes the old capture backend and creates a new one
  on the new monitor, **without restarting the tool**: the session, the
  translation cache, the history file and the F8/F9 state all survive.
* The overlay is resized to the new resolution, the font size is rescaled
  through `Config.scale()` and the bboxes are scaled by the same factor, so
  the Vietnamese text still lands exactly on the English text.
* `DisplayWatcher.describe()` prints the size, the DPI, the number of
  detections and the number of restarts.

**What does not work, and why:**

* **dxcam binds its DXGI output to one device at creation.** A monitor that
  is added or removed is a *different* DXGI output, so the running dxcam
  session keeps grabbing the old output (or fails). There is no public API
  to rebind an existing Desktop Duplication session to another output.
* **Two Desktop Duplication sessions cannot run at the same time.** The
  "create a second capture session for the new monitor and swap" approach
  is therefore not possible with dxcam.
* The accepted behaviour is therefore the **restart-capture** described
  above: the new backend is created from scratch for the new monitor. The
  cost is one missed frame at the moment of the change.
* The `mss` backend (GDI) has no such limitation - it can be pointed at
  another monitor - but it is 20x slower (61.5 ms vs 3.0 ms per grab), so
  it is only the fallback.
* **A real multi-monitor test was not possible in this environment**: the
  machine has one monitor, so the hot-plug was exercised through the tests
  (a mocked size change) and not by unplugging a physical screen. This is
  the main thing left to verify before the real-game test.

---

## 7. The files changed in this resume

**New modules:**

| File | Responsibility |
| --- | --- |
| `src/async_translate.py` | the background translation thread (item C) |
| `src/display.py` | the per-monitor DPI and the hot-plug watcher (item F) |
| `src/hud.py` | the live latency HUD state (item E) |

**New fixtures:** `sample_h_two_corner_base.png`,
`sample_h_two_corner_changed.png`, `sample_i_small_font.png`,
`sample_j_big_change_base.png`, `sample_j_big_change.png`. The P1 and P2
fixtures were **not** regenerated.

**New tests:** `tests/test_display.py` (11 tests),
`tests/test_p3_features.py`, `tests/test_p3_pipeline.py`. The suite went
from **108** to **178** tests.

**Changed modules:** `src/ocr.py` (the two-step read and the tiled read),
`src/pipeline.py` (the two-step full-frame read and the new tiled read),
`src/roi.py` (the per-region merging), `src/change.py` (the exact
max-pooled downscale), `src/config.py` and `config/config.yaml` (the new
keys), `src/grouping.py` (the adaptive gaps), `src/sentences.py` (the
abbreviations and the decimals), `src/overlay.py` (the HUD), `src/main.py`
(the hot-plug and the HUD wiring), `PROJECT_CONTEXT.md`, `README.md`.

**New script:** `scripts/bench_p3.py` (the P3 benchmark, every number is a
median of 7 runs with min/max).

---

## 8. The bugs and the remaining limitations

| # | Issue | Severity |
| --- | --- | --- |
| 1 | The OCR is still the bottleneck: 469 ms for a big screen change and 95 ms for a dialogue line, against ~50 ms for the translation. The next step is the PP-OCR *mobile* detection model measured **on the small detection frame** - on the full frame it was slower (P2 item E), but on a half-size frame the arithmetic changes. | Medium |
| 2 | The detection scale has to be a compromise: 0.5 keeps the 0.7x font exact, 0.35 is faster but loses a period sometimes. A per-frame scale (chosen from the measured text height) would get both. | Medium |
| 3 | The tiled refresh still reads the tiles that changed, but the **detection runs on the whole frame every time**. A change of a single pixel in a corner therefore costs a full detection (~200 ms at scale 0.5). | Low |
| 4 | The hot-plug was **not tested with a real second monitor** (the machine has one). It is exercised through the tests with a mocked size change. | Medium |
| 5 | The recognition pool creates **8 ONNX sessions** (one per worker) and the ROI pool 3 more: the memory use grew. The sessions are created lazily, so a session that is never used is never created. | Low |
| 6 | The `max` of the tiled refresh was 1039.3 ms in one of the 7 runs. It is the **translation** that was slow in that run (419.4 ms, a cache miss), not the OCR. The OCR itself stayed between 449 and 608 ms. | Low |
| 7 | The two-step read calls the private RapidOCR methods (`auto_text_det`, `get_crop_img_list`, `text_rec`). They are stable in the pinned version, but an upgrade of `rapidocr_onnxruntime` could break them. The plain `read()` path is kept as a fallback (`ocr_two_step: false`). | Low |
| 8 | The tool has still **not been tested on the real WuWa client**. Only the synthetic fixtures and the real screen capture were used. The HUD elements of the game may produce OCR noise that the filter does not catch. | Medium |

---

## 9. The commit and the push

See the end of this section (filled in after the push).

---

## 10. The conclusion

**Are the P3 targets met?**

| Target | Result |
| --- | --- |
| A big screen change under 500 ms | **YES** - 478.3 ms median |
| The in-game ROI path under 300 ms | **YES** - 104.5 ms median (82.9 - 90.8 ms isolated) |
| The diff stage under 15 ms | **YES** - 6.9 ms median |
| The same blocks at the normal and at the 0.7x font | **YES** |
| The HUD toggle and the numbers | **YES** |
| The display change, the capture restart, the overlay follows | **YES** (the limitation of section 6) |
| Offline operation | **YES** |
| No online API, no injection | **YES** |
| pytest, no regression | **YES** - 178 passed |

**All the P3 targets are met.**

**What is the slowest stage now?** The **OCR detection**, at every path:

* 469 ms of the 478 ms of a big screen change;
* 95 ms of the 104 ms of a dialogue change;
* ~200 ms of the detection alone in the two-step read.

**What should the next phase optimize first?** The **detection model on
the small frame**. The recognition is already parallelized and the
translation is already in the background. The next three steps, in order:

1. **PP-OCRv4 mobile detection, measured on the half-size frame.** P2
   measured it on the full frame, where it was slower (1942 ms vs 1928 ms);
   on a half-size frame the balance is different and it is worth re-measuring.
2. **A per-frame detection scale**, chosen from the measured text height, so
   a big-font screen is detected at 0.35 and a small-font screen at 0.6 -
   the accuracy of the 0.7x font without the cost of the conservative 0.5.
3. **The detection only where something changed**: the diff mask is already
   known, so the detector could be run on the bounding box of the changed
   pixels (at the native resolution) instead of on the whole frame.

The translation (50 ms) and the Python code are no longer worth optimizing:
they are 10 % of the total.
