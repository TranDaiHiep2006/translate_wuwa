# P3 RESUME - Continue P3 from src/display.py, do not restart

## ROLE
You are a senior Python developer. You resume an interrupted phase of work, finish it cleanly, and never redo work that is already done. You never fabricate numbers.

## CONTEXT
- This is a RESUME prompt for P3 of the WuWa Screen Translation Tool. The P3 work was interrupted while implementing item F (per-monitor DPI hot-plug) in src/display.py. Do NOT restart P3 from scratch. Do NOT redo items A-E if they are already done and tested.
- Read PROJECT_CONTEXT.md and REPORT.md first for full project context. They are the canonical sources. The P3 brief is in prompt.md from the start of this chat; re-read it before continuing.
- Local path: D:\translate_wuwa
- GitHub repo: https://github.com/TranDaiHiep2006/translate_wuwa
- P2 status (verified on GitHub, code HEAD 29c3eee, report HEAD 430b736, 10 commits): pytest 108 passed. In-game ROI path 143 ms on a good run, full-frame sweep 802 ms warm / 1741 ms cold.
- The user pasted the current src/display.py content into the chat, but the pasted text is corrupted by chat formatting (collapsed import lines, stray markers). The file on disk is the source of truth. Read D:\translate_wuwa\src\display.py from disk and ignore the formatting of the pasted copy.

## FIRST STEP - INSPECT THE CURRENT STATE BEFORE WRITING ANY CODE
1. Run git status and git log --oneline -15. Record which files are modified, staged, untracked, or already committed for P3.
2. Read src/display.py from disk. Run python -m py_compile src/display.py. If it has a syntax error, fix only the syntax, then report what was broken.
3. For each P3 item (A tiled refresh + per-region ROI + parallel OCR, B downscaled diff, C async pipeline, D adaptive grouping, E latency HUD, F hot-plug, G sentence splitter hardening), check the code and the tests and record DONE, PARTIAL, or NOT STARTED, with the evidence (file + test names). Do not trust memory: check the files.
4. Run python -m pytest -q and record the current pass/fail count. If tests fail, fix the failures before adding new work.
5. Report this state check in the final REPORT, so the next reader can see exactly where P3 was resumed from.

## CONTINUE FROM HERE, IN THIS ORDER
1. Finish item F (hot-plug) from the current src/display.py: the file already contains DisplayState, read_dpi, DisplayWatcher (observe, on_changed, describe), and restart_capture. Finish the wiring: poll DisplayWatcher.observe() from the worker thread on every frame (cheap size check; DPI query only when the size changed), on a detected change call restart_capture() to close and recreate the capture backend on the new monitor without restarting the whole tool, resize the overlay, recompute the scaling factor via Config.scale(), and log DisplayWatcher.describe(). The overlay must follow the game to the new monitor with the correct resolution, font size, and bbox scaling. If a clean hot-plug is not possible with dxcam (it binds its output to one device at creation, DXGI Desktop Duplication cannot run from two capture sessions at once), the restart-capture behaviour above is the accepted next best thing: record exactly what works and what does not in the REPORT.
2. Add tests for item F: observe() returns False on the first observation (baseline) and on an unchanged size, returns True on a changed size, restarts is counted by on_changed(), scale() returns height / 1080, describe() contains the size, dpi, detections, and restarts. Add a test that restart_capture() closes the old backend and creates a new one (mock the backend if needed).
3. Then do item G (sentence splitter hardening): extend the abbreviation list and decimal handling, add tests for Dr., Mr., Mrs., e.g., i.e., U.S., decimal commas, and numbers with commas (1,234). Keep the regex splitter as the default and Stanza available as a fallback in config.
4. Then verify any P3 item recorded as PARTIAL in the state check, in the original P3 order (A, then B, then C, then D, then E), and finish it before moving on. Run the tests after each item. Do not start the next item while the previous one has failing tests.
5. Reuse the P3 fixtures (h), (i), (j) if they already exist; create them only if they are missing. Do not regenerate the P1/P2 fixtures.

## FINISH P3
1. Run the full test suite: python -m pytest -q. Requirement: at least 120 tests total, all passing, no regression from the P2 108 tests.
2. Rerun scripts/bench.py. Every latency number must be the median of at least 5 repeated runs, with min and max shown. Print the P2 vs P3 table per stage, cold vs warm, on the same 1920x1080 fixtures, plus a separate in-game ROI table (median/min/max) and a tiled-refresh table for fixture (j).
3. Update PROJECT_CONTEXT.md section 10 with the P3 status and the new config keys, update README.md (tiled refresh, per-region ROI, downscaled diff, async pipeline, adaptive grouping, HUD toggle F9, hot-plug behaviour, new config keys), and append the P3 REPORT to REPORT.md in English.
4. git add, commit, and push to main on https://github.com/TranDaiHiep2006/translate_wuwa. If the push fails, record the exact error in the REPORT and write the retry instructions in the README. Do not pretend the push succeeded.

## ACCEPTANCE CRITERIA FOR P3 (all must pass, same as the original P3 brief)
- [ ] python -m pytest -q passes fully, no regression from the P2 108 tests.
- [ ] A big screen change (fixture j) is refreshed in under 500 ms warm (median of 5 runs). If the target is not reached, the REPORT must state the real median number and the next bottleneck, and must NOT claim it.
- [ ] The in-game ROI path median is under 300 ms warm (median of 5 runs), and the max over those 5 runs is reported. The P2 single best run of 143 ms must NOT be presented as the P3 result.
- [ ] The diff stage median is under 15 ms.
- [ ] The same dialogue groups into the same blocks at normal font and at 0.7x font.
- [ ] The HUD toggle F9 shows and hides the HUD, and the HUD numbers match the bench StageTimings.
- [ ] The display change is detected, the capture restarts cleanly on the new monitor without restarting the tool, and the overlay follows with the correct resolution, font, and bbox scaling.
- [ ] Disconnect the network after the first model download: the tool still translates (truly offline).
- [ ] No online API calls, no API key in code/config. No game memory reading, no injection, no DLL, no game file modification.
- [ ] Code is pushed to https://github.com/TranDaiHiep2006/translate_wuwa (or the REPORT states the exact reason it could not be pushed + how to retry).

## REPORT (mandatory, return at the end, concise, real numbers, in English)
- The state check from the first step: where P3 was resumed from, which items were DONE / PARTIAL / NOT STARTED, the pytest count at resume time.
- Files created/changed in this resume + commit hash + GitHub commit link after pushing.
- Baseline P2 numbers vs P3 numbers, per stage, cold vs warm, on the same 1920x1080 fixtures, every number as median of at least 5 runs with min/max. Separate tables for the in-game ROI path and for the tiled refresh on fixture (j). The ROI engine thread-count sweep table.
- Conclusion: are the P3 targets met? If not, which stage is now the slowest, and what should the next phase optimize first?
- 3 before/after examples: a big screen change refresh, a two-corner change, and the adaptive grouping at 0.7x font.
- pytest result (number of tests passed/failed, total count).
- What works and what does not for per-monitor hot-plug.
- Bugs / remaining limitations + what is still missing before the real-game test.
- Reply in English only in this chat, never Chinese. Paste the full English REPORT here, in English only.
