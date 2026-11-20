# P2 - WuWa Screen Translation Tool: ROI OCR + bug fixes

## ROLE
You are a senior Python developer. You optimize a working Windows desktop tool for speed and correctness, with clean code, tests, and real benchmarks. You never fabricate numbers.

## CONTEXT
- Read PROJECT_CONTEXT.md and REPORT.md first for full project context. They are the canonical sources. Do not paste the whole codebase into your context.
- User: Hiep, plays Wuthering Waves (WuWa) on Windows, game runs borderless.
  Machine: Intel Core i5 Gen 12, 16GB RAM, RTX 3050 Ti Laptop 4GB (VRAM is already
  almost full while playing the game).
- Local path: D:\translate_wuwa
- GitHub repo: https://github.com/TranDaiHiep2006/translate_wuwa
- Workflow: Hiep is the middleman. I write the prompt, Hiep pastes it to Cursor,
  you code + commit + push to the repo above, and return a REPORT. Hiep will
  test on the real machine.
- P1 status (2026-11-20, HEAD 2cfd167, 5 commits, verified on GitHub):
  pytest 44 passed / 0 failed. Tool works fully offline. Engine Argos,
  capture dxcam. Latency cold 1607 ms / warm 787 ms on 1920x1080 fixtures.
  Goal under 0.5 s was NOT reached. Slowest stage is OCR inference
  (660-1898 ms, about 92 percent of the total). Translation is only 59-273 ms cold.
- Keep everything from P1 working. This is an optimization and bug-fix phase,
  not a rebuild. Do not rewrite the pipeline, do not change the translation
  engine, do not change the capture backend, unless a benchmark you run proves
  the change is faster with no accuracy loss.

## GOAL OF P2
Cut end-to-end latency toward under 0.5 s warm, and fix the four main P1 bugs.
P2 succeeds if the warm end-to-end time drops clearly and the four bugs below
are fixed with tests. If under 0.5 s is still not reached, REPORT the real
numbers and name the next bottleneck. NEVER claim under 0.5 s without measuring it.

## ABSOLUTE PROHIBITIONS (unchanged from P1)
- DO NOT read the game memory / process, DO NOT inject, NO DLL, DO NOT modify
  game files, DO NOT automatically press keys / control the game.
- Only allowed: screenshot capture + drawing a separate overlay window outside
  the game.
- DO NOT call any online translation API (Google / DeepL / OpenAI / Gemini...).
  No API key required. After the first model download, the tool must run
  fully OFFLINE.
- DO NOT hardcode 1920x1080 or any resolution. Every pixel value scales with
  the real resolution. Tests must cover 1920x1080 and 2560x1600.
- Keep the code in Python. The bottleneck is ONNX Runtime inference (C++),
  not Python code.

## WORK ITEMS, IN THIS ORDER

### A. ROI OCR - the main work, do this first
- src/change.py already produces a diff mask. Use it to compute the changed
  bounding rectangle of the frame. Expand it by a configurable padding
  (for example 10-20 px at 1080p reference height, scaled at runtime via
  Config.scale()). Crop the frame to that ROI and run OCR only on the ROI.
- Offset every OCR bbox back to full-screen coordinates (x + roi_x, y + roi_y).
  This offset is the most error-prone part: a wrong offset shifts every overlay.
  Add a dedicated test for it.
- Rules: no change -> skip OCR entirely. Small change -> small ROI. Large change
  or first frame -> full-frame fallback. If the union of changed regions covers
  more than 80 percent of the screen, use the full frame instead of a huge ROI.
  Add config keys: roi_enabled (default true), roi_padding_px, roi_min_area,
  roi_full_frame_threshold (default 0.8).
- Keep debounce, grouping, speaker detection, and cache working on the offset
  coordinates exactly as before.
- Target to measure, not to promise: ROI OCR on a dialogue-only change
  100-200 ms (P1 full-frame OCR was about 800 ms warm). Report the measured
  ROI OCR time vs full-frame OCR time on the same images.

### B. Overlay text wrapping + opaque background
- Wrap the Vietnamese text inside the bbox width. Grow the bbox vertically
  as needed. Do not change the font size unless the wrapped text still does
  not fit after growing vertically.
- The overlay background must be fully opaque by default (configurable, default
  opaque), so the original English text is hidden, not slightly visible through
  a semi-transparent background.
- Keep the overlay click-through, always on top, never stealing focus, never
  blocking game input. Update data/overlay_demo.png as proof.
- Test: a long translation that overflowed in P1 must now fit inside the bbox
  width with no clipped text.

### C. Sentence-by-sentence translation - fix the lost digits
- P1 bug: Reward: 12000 was translated as Phan thuong:2000. Cause: the merged
  block was translated as one unit and the Argos sentence splitter re-tokenized
  it and lost a digit.
- Fix: split each grouped block into sentences before translation, translate
  each sentence separately, then rejoin with the original separators and spaces.
  Do not split inside numbers, decimals, or abbreviations. Reward: 12000 must
  stay as one unit and come back with 12000 intact.
- Numbers, percentages, and proper nouns must be preserved exactly. Add tests:
  Reward: 12000, 15 percent, and at least one multi-sentence block.
- Cache per sentence as well as per block, so a repeated sentence is a cache hit.
  Keep the glossary placeholder protect/restore working per sentence.
- If the Stanza sentence splitter adds about 200 ms per batch, try a lightweight
  regex splitter first and only fall back to Stanza when needed. Measure and
  report the splitter cost.

### D. Speaker detector: UI-label blacklist + character roster
- P1 bug: Quest, Skill, Inventory, Settings were treated as speaker names.
- Create config/ui_labels.yaml (or add the list to config/config.yaml if that
  fits the existing structure better): a blacklist including Quest, Skill,
  Objective, Mission, Inventory, Settings, Skills, and other common WuWa UI
  labels you find in the fixtures and in the game UI. Matching is
  case-insensitive, after stripping whitespace and an optional trailing colon.
  A line matching the blacklist is NEVER a speaker.
- Create config/roster.yaml: the WuWa playable Resonator names (Rover, Jiyan,
  Changli, Carlotta, Shorekeeper, and the other major playable characters as
  of game version 3.7, plus any NPC names you can list confidently). The file
  must be editable so the user can add names later.
- New speaker rule: a short capitalized line above a dialogue block is a
  speaker ONLY if (a) it is NOT in the blacklist, AND (b) it is either in the
  roster, OR it ends with a colon and is 1-3 words long (this keeps NPC names
  with a colon while blocking bare labels). A standalone menu line with no
  dialogue block below it is never a speaker.
- Update the session history output accordingly: entries previously mislabeled
  as Quest: or Skill: must now show no speaker, or the correct speaker.
- Tests: Quest, Skill, Inventory, Settings must NOT be speakers. Jiyan and
  Rover MUST still be speakers.

### E. Smaller / faster OCR models - experiment only, do this last
- Only after A-D are done and measured: try the PP-OCRv4 mobile detection model
  instead of the bundled server model, and an int8 quantized recognition model.
  Benchmark them on the same fixtures. Switch the default ONLY if the benchmark
  proves they are faster with no accuracy loss on the fixtures. If they are not
  clearly better, keep the P1 models and report the experiment numbers in the
  REPORT. Do not let this item delay or break A-D.

## OUT OF SCOPE FOR P2
- Do not change the translation engine (Argos stays the default).
- Do not change the capture backend (dxcam stays the default).
- Do not add GPU OCR (the RTX 3050 Ti has almost no free VRAM during play).
- Do not add a live latency HUD (that is a later phase, not P2).
- Do not claim a test on the real WuWa client unless you actually ran it there.
  Fixture + real screen capture tests are enough for P2.

## DETAILED TASKS
1. Baseline first, before changing any code: run python -m pytest -q (expect
   44 passed) and python scripts/bench.py (expect cold about 1607 ms, warm
   about 787 ms). Record these numbers. If the baseline does not match, stop
   and report the difference before changing code.
2. Implement A, then B, then C, then D, in that order. Run the tests after each
   item. Do not start the next item while the previous one has failing tests.
3. New fixtures (draw with Pillow, do not use copyrighted game screenshots):
   (d) the same frame twice, only the bottom dialogue box changed (ROI test),
   (e) a long dialogue that needs wrapping, (f) a quest block with Reward: 12000,
   (g) a menu with Quest, Skill, Inventory, Settings labels. Place them in
   tests/fixtures/. Reuse the P1 fixtures for regression.
4. Tests: at least 10 new tests, total at least 54, including: ROI coordinate
   offset is correct, ROI skips an unchanged frame, ROI falls back to full frame
   on a large change, wrapped text fits inside the bbox width, opaque background
   hides the original text, sentence translation preserves 12000, blacklist
   blocks Quest and Skill, roster accepts Jiyan and Rover, session history no
   longer labels Quest or Skill as speakers, pipeline on a sample image still
   returns at least 1 translated block.
5. Benchmark: rerun scripts/bench.py and scripts/bench_translation.py. Print a
   P1 vs P2 table per stage, cold vs warm, on the same 1920x1080 fixtures.
   Also print a separate ROI vs full-frame OCR table from fixture (d).
6. Update PROJECT_CONTEXT.md section 10 with the P2 status and the new config
   keys, update README.md (ROI, wrapping, sentence translation, roster and
   blacklist, new config keys), and append the P2 REPORT to REPORT.md in English.
7. git add, commit, and push to main on
   https://github.com/TranDaiHiep2006/translate_wuwa. If the push fails,
   record the exact error in the REPORT and write the retry instructions in
   the README. Do not pretend the push succeeded.

## ACCEPTANCE CRITERIA FOR P2 (all must pass)
- [ ] python -m pytest -q passes fully, no regression from the P1 44 tests.
- [ ] Warm end-to-end time is clearly lower than the P1 787 ms. Target warm
      under 500 ms. If the target is not reached, the REPORT must state the
      real warm number and the next bottleneck, and must NOT claim under 500 ms.
- [ ] ROI OCR on a dialogue-only change is measured and reported, with the
      full-frame OCR time on the same image for comparison.
- [ ] Reward: 12000 is translated with 12000 intact (not 2000).
- [ ] Quest, Skill, Inventory, Settings are never shown as speakers. Jiyan and
      Rover are still shown as speakers.
- [ ] A long Vietnamese translation wraps inside the bbox width with no clipped
      text, and the original English text is hidden by the opaque background.
- [ ] Disconnect the network after the first model download: the tool still
      translates (truly offline).
- [ ] No online API calls, no API key in code/config. No game memory reading,
      no injection, no DLL, no game file modification.
- [ ] Code is pushed to https://github.com/TranDaiHiep2006/translate_wuwa
      (or the REPORT states the exact reason it could not be pushed + how to retry).

## REPORT (mandatory, return at the end, concise, real numbers, in English)
- Files created/changed + commit hash + GitHub commit link after pushing.
- Baseline P1 numbers vs P2 numbers, per stage, cold vs warm, on the same
  1920x1080 fixtures. ROI OCR time vs full-frame OCR time on fixture (d).
- Conclusion: is warm end-to-end under 500 ms yet? If not, which stage is now
  the slowest, and what should P3 optimize first?
- 3 before/after examples: the Reward: 12000 fix, a speaker fix (Quest/Skill
  no longer a speaker, Jiyan still a speaker), and a wrapping fix.
- pytest result (number of tests passed/failed, total count).
- Bugs / remaining limitations + P3 proposals.
- Reply in English only in this chat, never Chinese. Paste the full English
  REPORT here, in English only.
