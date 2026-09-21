# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the main guide: architecture, guardrails, verification checklist and the Cloudflare Pages release steps. It is imported below. This file adds only details that `AGENTS.md` does not cover.

@AGENTS.md

## Self-test output

There is no build, lint or test runner. Load `index.html?selftest=1` and read the `[selftest]` console lines. They run from `runNextBootTask()` after the boot bake queue finishes:

- `rows=5000 fairness violations=0`: this must be 0.
- `klsFlagSelfTest: OK (0 violations)`
- `kopitiamChinese.usedFallback` / `bananaLeafTamil.usedFallback`: whether the device has fonts for the non-Latin boards.
- `kapcaiKeyFor shares`: should be close to 20/12/8/20/20/20 for `kapcai`, `kapcaiPlain`, `kapcaiPillion`, `kapcaiJade`, `kapcaiMagenta`, `kapcaiMelon`.

## Additional notes

- **`?log=<url>`.** If set, the session JSON is sent with `sendBeacon` on `pagehide` (`sendRemoteLog`). With no `log` parameter, session metrics stay only in `localStorage`.
- **Persisted keys.** Best score, mute state and sessions use `gbx_lanes_best`, `gbx_lanes_mute` and `gbx_lanes_sessions`, built from `GAME_ID`. The nickname uses `racerweek_player_name`. Renaming `GAME_ID` resets players' stored best scores.
- **Start-up state.** The first run goes from PLAY NOW straight to PLAYING through `beginRun(true)`. The canvas READY screen only appears later. `<html>` has `data-landing="1"` until the landing page is dismissed.
- **Adaptive LOD.**
  - `lowResourceDevice` is true when `deviceMemory` or `hardwareConcurrency` is 4 or less, unless `QUALITY` overrides it. It lowers `SPRITE_DPR` and the street bake factor.
  - While PLAYING, `updateFPS()` switches to `STREET_LOD_LOW` after 2 seconds below 45 fps. It switches back to high after 5 seconds above 56 fps, but never on a low-resource device.
  - For visual QA at a fixed tier, pass `QUALITY=`.
- **Git.**
  - `master` is the only branch and there is no remote. Cloudflare's `--branch main` is a Pages deployment label, not a git branch.
  - The reference images (`arhive/`, `assets-archive/`, `twintower/`, root `*.png`) are deliberately untracked. `.wrangler/` is ignored.
