# P1 NEW - WuWa Screen Translation Tool: rebuild from scratch, skeleton + end-to-end pipeline

## ROLE
You are a senior Python developer. You build desktop tools on Windows, with clean code, tests, and real benchmarks. You never fabricate numbers.

## CONTEXT
- User: Hiep, plays Wuthering Waves (WuWa) on Windows, game runs borderless.
  Machine: Intel Core i5 Gen 12, 16GB RAM, RTX 3050 Ti Laptop 4GB (VRAM is already
  almost full while playing the game).
- This is a COMPLETELY NEW project, rebuilt from scratch. Discard the old spec
  from 15/10 and the old P1 code. Do not copy old code, do not reuse the old repo.
- Local path: D:\translate_wuwa
- GitHub repo: https://github.com/TranDaiHiep2006/translate_wuwa
- Workflow: Hiep is the middleman. I write the prompt, Hiep pastes it to Cursor,
  you code + commit + push to the repo above, and return a REPORT. Hiep will
  test on the real machine.
- Lesson from a previous project by the same user (wuwa-dps-meter): the bottleneck
  is OCR inference + decode (running on ONNX Runtime, which is C++ code), not
  Python code. So KEEP PYTHON, do not rewrite in C++. Optimize by: only
  processing changed regions (frame differencing), caching results, running
  in parallel, measuring real benchmarks.
- The PROJECT_CONTEXT.md you create in this P1 will be the canonical context
  for all later prompts. Every later prompt will only point at that file plus
  the new work plus acceptance criteria, never paste the whole codebase.

## GOAL OF P1
A Windows tool that automatically captures the screen, OCRs English text,
translates it to Vietnamese with an OFFLINE model (no API, no key, no cost),
and shows the translation in a transparent overlay placed directly over the
original text in the game, at the original text position.
Latency goal: as low as possible, under 0.5 seconds from the moment new text
appears until the translation is visible, ideally almost instant.
P1 = a working pipeline + real measured latency. If 0.5s is not reached, REPORT
the real numbers and name the slowest stage. NEVER claim 0.5s without measuring it.

## ABSOLUTE PROHIBITIONS (anti-cheat safety)
- DO NOT read the game memory / process, DO NOT inject, NO DLL, DO NOT modify
  game files, DO NOT automatically press keys / control the game.
- Only allowed: screenshot capture + drawing a separate overlay window outside
  the game.
- DO NOT call any online translation API (Google / DeepL / OpenAI / Gemini...).
  No API key required. After the first model download, the tool must run
  fully OFFLINE.

## SCREEN SIZE / RESOLUTION - MANDATORY
- DO NOT hardcode 1920x1080 or any resolution.
- The tool must auto-detect the primary monitor resolution at runtime (via the
  capture library) and handle Windows DPI scaling correctly (100%, 125%, 150%...).
- OCR bbox coordinates, overlay position, and font size must all scale with the
  real resolution. Switching to another monitor (for example 2560x1600) must
  still show the overlay at the correct position.
- Tests must cover at least 2 different resolutions (a 1920x1080 fixture and
  the same image scaled to 2560x1600) to prove nothing is hardcoded.

## STACK (follow this direction unless you can prove another option is better)
- Python 3.11 (DO NOT use 3.13 - some OCR wheels are unstable on 3.13). venv.
- Capture: benchmark BOTH on the same real machine and pick the faster one,
  record the numbers in the REPORT:
  (a) mss (simple), (b) dxcam (DXGI Desktop Duplication, usually faster).
  Keep a fallback: if the chosen one fails, automatically use the other.
- OCR: rapidocr-onnxruntime (RapidOCR, PP-OCR, ONNX Runtime, CPU). DO NOT use
  EasyOCR in P1 (heavy, slow, pulls in torch).
- Offline translation: benchmark the 2 candidates below on the SAME 10 English
  game-style sentences (dialogue, quest, skill description - you create the
  10 sample sentences), then pick 1 as the default:
  (a) Argos Translate, package translate-en_vi (CTranslate2 / OpenNMT).
  (b) Helsinki-NLP opus-mt-en-vi (MarianMT) via transformers (prefer a
  CTranslate2/ONNX build if it runs, to stay light and fast).
  Selection criteria: average latency per sentence + translation quality judged
  by eye. If one of them fails to install/run on Windows, fall back to the
  other one and state the error clearly in the REPORT. Code must hide the
  translation engine behind one common interface
  (translate(texts: list[str]) -> list[str]) so switching engines does not
  change the pipeline.
- Overlay: PyQt6 + pywin32. Transparent, click-through window
  (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST), always on top,
  NEVER steals focus, NEVER blocks game input.
- Cache/history: SQLite (file data/cache.db, gitignored) for the translation cache.
  Session history: text files, see PIPELINE item 11.
- Config: config/config.yaml (read with PyYAML). Tests: pytest.

## PIPELINE (P1 must contain all of these stages)
1. Capture: capture the primary screen every ~200ms (configurable, default 200ms
   to aim for the 0.5s goal), handle Windows DPI/scale, auto-detect resolution.
2. Change detection: compare the new frame with the previous frame (frame
   differencing, configurable threshold). A nearly unchanged frame is SKIPPED,
   no OCR is run on it.
3. OCR: only run OCR when the frame changed enough. Return per line:
   text + bbox + confidence.
4. Filter: drop lines that are only numbers/symbols (damage numbers, HP,
   timers...), drop confidence below 0.5, drop text shorter than 2 characters.
   Log how many lines were filtered.
5. Group lines into blocks + detect speaker name: OCR lines close together
   vertically (gap below a configurable threshold) are grouped into one
   paragraph before translation - translating isolated lines breaks sentences.
   Each block keeps its merged bbox so the overlay draws at the right place.
   In WuWa, the speaker name is usually on its own line above the dialogue box,
   or in the form Name: dialogue. Rule: a short line (1-3 words, capitalized,
   no sentence-ending period, sitting directly above the dialogue block) or
   the part before a colon in the same line is treated as the speaker name.
   KEEP the name untranslated and display it as Name: translated dialogue.
   If no name is found, show only the translated dialogue. NEVER invent a name.
6. Stabilize (debounce): only translate a text block after it has stayed still
   for ~100-150ms (configurable), to avoid translating text that is still
   fading in or typing out.
7. Cache: normalize the source (strip, collapse whitespace, keep case) and
   look it up in SQLite. Cache hit: use it immediately, DO NOT call the
   translation model. Cache miss: translate and store it.
8. Glossary: config/glossary.yaml - a dict of WuWa terms kept untranslated
   (pre-fill: Rover, Resonator, Tacet Field, Waveplate... plus a placeholder
   mechanism that replaces them before translation and restores them after,
   with tests).
9. Translate: translate in batches (collect the uncached blocks from one loop
   iteration and translate them in one call).
10. Overlay render: draw the Vietnamese translation at the original block bbox,
    covering the original text, on a semi-transparent black background, white
    or yellow text, font size auto-scaled to the bbox height and the screen
    resolution. Format: Name: translated dialogue when a name exists, otherwise
    only the translated dialogue. When the original text disappears, remove
    the matching overlay (do not leave stale translations on screen).
11. Session history: folder data/sessions/ (gitignored). Each session starts
    when the hotkey is pressed to turn translation ON, and ends when the hotkey
    is pressed again to turn it OFF. File name: YYYY-MM-DD_HH-MM-SS.txt using
    the session start time. Each translated block is appended exactly once
    (never repeat the same block every poll loop). Format per entry, easy to read:
    Line 1: [HH:MM:SS] Speaker Name: Vietnamese translation
    Line 2:   EN: original English sentence
    If there is no name, line 1 is: [HH:MM:SS] Vietnamese translation
    Entries are separated by one blank line.
12. Threads: a worker thread does capture, OCR, and translation; the UI thread
    only renders the overlay. The game must not stutter because of the tool.

## HOTKEY - MANDATORY, FOLLOW THIS DEFINITION EXACTLY
- F8 = toggle the translation session ON/OFF. Press once to turn ON: start a new
  session, create a new history file, and start automatically translating any
  new text that appears on screen. Press again to turn OFF: stop capture/OCR/
  translation, clear all overlays, and close the history file of that session.
- Do NOT require a key press for every translation. While ON, the tool translates
  automatically with no further key presses.
- Use pynput for the global hotkey. DO NOT use keys that conflict with WuWa
  defaults 1-5/Q/E/R/F/Tab/Esc. Print the ON/OFF state to the log and show it
  briefly on the overlay (for example in a screen corner: TRANSLATING / OFF).

## DETAILED TASKS
1. Create the project structure in D:\translate_wuwa + PROJECT_CONTEXT.md (goal,
   stack, pipeline, conventions, how to run, how to test - concise, the context
   source for later prompts).
2. requirements.txt (pin versions that work on Windows), .gitignore
   (venv, models/, data/*.db, data/sessions/, __pycache__), README.md (install,
   run, how to test on sample images + on the real game, how to push, explain
   the F8 hotkey and the history folder).
3. config/config.yaml: source_lang=en, target_lang=vi, poll_ms=200,
   diff_threshold, debounce_ms=120, ocr_conf_min=0.5, overlay font/size/color,
   hotkey=F8, device=cpu by default (keep a gpu option in config, but P1 runs
   on CPU - the game is using the GPU).
4. Code the modules (one file per module, small functions, docstrings):
   src/capture.py, src/change.py, src/ocr.py, src/grouping.py,
   src/cache.py (SQLite: cache table + history table with
   timestamp/source/translation/bbox),
   src/translator.py (interface + 2 engines Argos/MarianMT + benchmark to choose),
   src/glossary.py, src/overlay.py, src/session.py (open/append/close the
   session history file),
   src/pipeline.py (connect the stages + measure time per stage),
   src/main.py (entry point).
5. Test fixtures: create 3 sample images at 1920x1080 (draw text with Pillow,
   DO NOT take copyrighted game screenshots): (a) 3-line dialogue WITH a speaker
   name above it, (b) quest + skill description, (c) menu + numbers (to test
   number filtering). Add 1 image at 2560x1600 (the image from (a) scaled up)
   to test that no resolution is hardcoded. Place them in tests/fixtures/.
6. scripts/bench.py: run the pipeline on the 3 sample images and print a table:
   time per stage (capture / diff / OCR / translate / render), total end-to-end,
   cold run (no cache, model just loaded) vs warm run (100% cache hits).
   DO NOT hardcode numbers - measure for real. State clearly whether it is
   under 0.5s or not.
7. pytest tests, at least 8 tests, including: cache hit/miss + normalization,
   line grouping, number filtering, glossary keeping terms untranslated,
   speaker-name detection (with a name: keep the name and format it as
   Name: translated dialogue; without a name: do not invent one),
   translator smoke test (translate 2 sample sentences to Vietnamese, do not
   assert exact wording because the model version may differ),
   session history (turning ON then OFF creates exactly 1 file, with the correct
   format and no duplicated entries),
   pipeline on a sample image returns at least 1 translated block.
8. git init in D:\translate_wuwa + local commit, remote add origin
   https://github.com/TranDaiHiep2006/translate_wuwa then push -u origin main.
   If the GitHub repo does not exist yet or the push fails, record the exact
   error in the REPORT and write the repo-creation + retry instructions in the
   README. Do not pretend the push succeeded.

## ACCEPTANCE CRITERIA FOR P1 (all must pass)
- [ ] python -m src.main runs on Windows, the overlay appears, F8 toggles
      correctly: one press ON means auto-translation starts, pressing again OFF
      stops it completely and clears the overlay.
- [ ] On the 3 sample images: the overlay shows the Vietnamese translation close
      to the original text position, damage/HP numbers are filtered out (no junk
      translations), and a speaker name shows correctly as Name: translated dialogue.
- [ ] On the 2560x1600 fixture: the overlay is still at the correct position,
      not shifted by a hardcoded resolution.
- [ ] Pressing F8 ON then F8 OFF creates exactly 1 file in data/sessions/, named
      with the correct timestamp format, with content in the format
      [time] Name: translated dialogue plus the EN line, and no duplicated entries.
- [ ] Running a second time on the same image: cache hit, total time clearly
      lower than the first run.
- [ ] pytest passes fully. scripts/bench.py runs and prints real numbers.
- [ ] Disconnect the network after the first model download: the tool still
      translates (truly offline).
- [ ] No online API calls, no API key in code/config.
- [ ] Code is pushed to https://github.com/TranDaiHiep2006/translate_wuwa
      (or the REPORT states the exact reason it could not be pushed + how to retry).

## REPORT (mandatory, return at the end, concise, real numbers, in English)
- Files created/changed + local commit hash + GitHub commit link after pushing.
- Translation engine chosen (Argos or MarianMT) + comparison table for latency
  and quality on the 10 sample sentences + reason for the choice. What failed
  with the other engine (if anything).
- Capture library chosen (mss or dxcam) + speed comparison table on the real machine.
- pytest result (number of tests passed/failed).
- Benchmark table from scripts/bench.py: cold vs warm, time per stage,
  total end-to-end on a 1920x1080 image. Conclusion: is it under 0.5s yet?
  Which stage is slowest, and what should P2 optimize first?
- 3 real translation examples (EN -> VI) from the sample images, at least 1 with
  a speaker name + 1 bad translation case (if any) with a note on the cause.
- The content of one real session history file (copy its first 5-10 lines verbatim).
- Bugs / remaining limitations + P2 proposals.
