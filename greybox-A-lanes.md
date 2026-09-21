# Greybox A - "LANES" (3-lane endless dodger)

## 0. Instructions to the implementing model
You are implementing a playable greybox prototype of a mobile browser game. Follow this spec exactly. Where the spec is silent, choose the simplest option and list it under "Assumptions" after the code. Do not add features. Do not add art. Output one complete `index.html`.

Purpose: measure whether the core loop makes people retry. Feel (input latency, restart speed, feedback) matters more than content.

All numbers below are untested starting values. They must live in CONFIG.

This document has two parts: the game spec (sections 1-9) and the SHARED REQUIREMENTS (sections S1-S15). Both are mandatory.

Storage prefix / game id: `lanes`. Version string: `A-0.1`.

## 1. Concept
The player's car drives forward automatically on a 3-lane road. Speed rises over time. Obstacles arrive in rows. The player switches lanes to avoid them. Dodging late ("near miss") gives bonus points and builds a combo. One hit = dead. Instant retry.

Skill tested: spatial reflex plus deliberate risk (waiting longer before dodging).

READY instruction line: `TAP left / right to change lane. Dodge LATE for bonus.`

## 2. World model
- Lateral position `x` in lane units. Lane centres: `-1, 0, +1`. Road edges at `x = -1.5` and `x = +1.5`.
- Depth `z` in metres ahead of the player. Player's rear bumper is at `z = 0`, front at `z = CAR_LEN`.
- The player does not move in z. Every world object's z decreases by `speed * dt` each step. `distance += speed * dt`.
- Objects are recycled to their pool when `z < -8`.

## 3. Projection (fake perspective)
```
s(z)        = 1 / (1 + z * PERSP_K)              // valid for z > -1 / PERSP_K
HORIZON_Y   = VIEW_H * 0.22
PLAYER_Y    = VIEW_H - 130
screenY(z)  = HORIZON_Y + (PLAYER_Y - HORIZON_Y) * s(z)
screenX(x,z)= 180 + x * LANE_W * s(z)
widthPx(w,z)= w * LANE_W * s(z)                  // w in lane units
```
- An object spanning `z0..z0+len` is drawn as a rectangle from `screenY(z0 + len)` (top) to `screenY(z0)` (bottom), width taken at `z0`.
- Road: filled trapezoid between `x = -1.5` and `x = +1.5`, from `z = -8` to `z = Z_FAR`.
- Lane dashes at `x = -0.5` and `x = +0.5`: length 3 m, every 9 m. Dash i starts at `z = i * 9 - (distance % 9)`.
- Roadside posts at `x = -1.8` and `x = +1.8`: 1 m long, every 18 m, same scrolling method. Dashes and posts are the only speed cue - they must be there.
- Draw order: road -> dashes -> posts -> pickups and obstacles from far to near -> player -> HUD.

## 4. Controls
- `INPUT_MODE = 'tap'` (default): `pointerdown` on the left half of the canvas = move one lane left; right half = one lane right.
- `INPUT_MODE = 'swipe'`: on `pointermove`, when horizontal travel since `pointerdown` exceeds 18 units, move one lane in that direction. One move per gesture.
- Keyboard: ArrowLeft / A, ArrowRight / D.
- Target lane is clamped to `[-1, +1]`. A move at the edge is ignored (no penalty).
- Lane change: `x` tweens from its CURRENT value to the target lane centre over `LANE_CHANGE_T` with ease-out quad. A new input during a tween retargets immediately from the current `x`. No input queue.

## 5. Difficulty curve
`t` = seconds since run start.
```
speed   = min(SPEED_MAX, SPEED_START + SPEED_RAMP * t)
k       = clamp(t / RAMP_TIME, 0, 1)
rowGapT = lerp(ROW_GAP_T_START, ROW_GAP_T_MIN, k)
```
Rows are scheduled by distance: keep `nextRowDist`. When `distance + Z_SPAWN >= nextRowDist`, spawn a row at `z = nextRowDist - distance`, then `nextRowDist += speed * rowGapT`. First row: `nextRowDist = 90`.

## 6. Row generation
Row types (chosen with the seeded RNG):
- `SINGLE`: one random lane blocked.
- `DOUBLE`: two lanes blocked. Only when `distance >= DOUBLE_FROM_DIST`. Probability lerps `DOUBLE_CHANCE_START -> DOUBLE_CHANCE_END` with `k`.
- `CUTTER`: exactly one obstacle, of kind cutter (section 7). Only when `distance >= CUTTER_FROM_DIST`, probability `CUTTER_CHANCE`.

Fairness rules (hard requirements):
1. Never block all three lanes.
2. Reachability: at least one open lane of the new row must be the same as, or adjacent to, an open lane of the previous row. If the rolled row violates this, re-roll (max 10 tries, then fall back to `SINGLE` in a lane that satisfies it).
3. For reachability purposes a `CUTTER` row counts as having only its starting lane blocked.

Pickups (only if `PICKUPS = 1`): with probability `PICKUP_CHANCE` per row, place one pickup halfway between this row and the next (`z_row + speed * rowGapT / 2`) in a random lane. Collect when `|px - pickupX| < 0.5` and the pickup's z is within `0..CAR_LEN`. Reward: `PICKUP_VALUE`, popup `+25`, no combo effect.

Self-test: with `?selftest=1`, generate 5000 rows without rendering and `console.log` the number of fairness violations (must be 0), then start normally.

## 7. Obstacles
- Static obstacle: width 0.68 lane units visually, length `OBST_LEN`, colour danger.
- Cutter: same size, drawn with a lighter danger tint `#ff8a4d`. When its `z < CUTTER_TRIGGER_Z` it starts a telegraph of `CUTTER_TELEGRAPH` seconds (blink at 10 Hz plus a small triangle pointing in the move direction), then tweens to an adjacent lane over `CUTTER_MOVE_T` (linear). Target lane: the player's current target lane if adjacent (probability `CUTTER_AIM`), otherwise a random adjacent lane. A cutter moves once.

## 8. Collision, near miss, scoring
Collision (checked every update step, using continuous x values):
```
hit = |px - ox| < 2 * HITBOX_X   AND   ox_z < CAR_LEN   AND   ox_z + OBST_LEN > 0
```
`HITBOX_X` is deliberately smaller than the visuals (forgiving).

Near miss = late dodge:
- Each obstacle has `threat = false` and `minTTI = Infinity`.
- Each step, with `tti = z / speed`: if `0 < tti <= NEAR_TTI` and `|px - ox| < 2 * HITBOX_X`, set `threat = true` and `minTTI = min(minTTI, tti)`.
- When the obstacle has fully passed (`z + OBST_LEN < 0`) without a hit and `threat` is true -> near miss.
- Tier: `minTTI <= NEAR_TTI_INSANE` -> base `NEAR_BONUS * 2`, popup `CLOSE!!`; else base `NEAR_BONUS`, popup `CLOSE`.
- Combo: `combo += 1` on each near miss; resets to 0 when `COMBO_WINDOW` seconds pass without one. Awarded bonus = `base * combo`. Popup shows `CLOSE x3 +150`.
- An obstacle in a lane the player never occupied inside the TTI window must never trigger a near miss.

Score = `floor(distance) + bonusTotal`. HUD shows the total.

`deathCause`: `static` or `cutter`.

## 9. CONFIG starting values
```
LANE_W: 84,              // logical units per lane at player depth
PERSP_K: 0.045,
Z_SPAWN: 160,            // m
Z_FAR: 400,              // m, road draw distance
CAR_LEN: 4.5,  OBST_LEN: 4.5,          // m
HITBOX_X: 0.34,          // lane units, half-width
SPEED_START: 24, SPEED_MAX: 72, SPEED_RAMP: 0.6,   // m/s, m/s, m/s per s
RAMP_TIME: 90,           // s
ROW_GAP_T_START: 1.15, ROW_GAP_T_MIN: 0.50,        // s
LANE_CHANGE_T: 0.09,     // s
INPUT_MODE: 'tap',
NEAR_TTI: 0.40, NEAR_TTI_INSANE: 0.18,             // s
NEAR_BONUS: 50, COMBO_WINDOW: 3.0,
DOUBLE_FROM_DIST: 250, DOUBLE_CHANCE_START: 0.2, DOUBLE_CHANCE_END: 0.6,
CUTTER_FROM_DIST: 600, CUTTER_CHANCE: 0.25, CUTTER_AIM: 0.7,
CUTTER_TRIGGER_Z: 70, CUTTER_TELEGRAPH: 0.45, CUTTER_MOVE_T: 0.35,
PICKUPS: 1, PICKUP_CHANCE: 0.5, PICKUP_VALUE: 25
```

## 10. Game-specific acceptance
- [ ] Lane change is visible on the frame after the press.
- [ ] `?selftest=1` reports 0 fairness violations.
- [ ] Holding one lane and never moving: no near-miss awards ever fire.
- [ ] Dodging at the last moment awards `CLOSE` / `CLOSE!!` and the combo multiplies.
- [ ] Cutter always telegraphs before moving and never moves twice.
- [ ] Debug overlay shows speed, rowGapT, distance, combo.
- [ ] Target feel (to verify by hand, not enforceable in code): a first-time player survives roughly 15-30 s on the first run.

---

# SHARED REQUIREMENTS (mandatory, same for every greybox)

## S1. Tech constraints
- One file: `index.html` with inline CSS and JS. Vanilla JS (ES2019), Canvas 2D. No libraries, no build step, no network requests, no images, no web fonts (use `system-ui, sans-serif`).
- Must run from `file://` and from any static host.
- Primary target: mobile portrait - Android Chrome, iOS Safari, and in-app webviews (WhatsApp, Instagram, TikTok). Desktop must be playable with keyboard for development.
- Do not use: Fullscreen API, Screen Orientation lock, service workers, `alert()`.

## S2. Canvas and scaling
- Logical width is always 360 units. Logical height `VIEW_H` is variable - never hardcode 640.
- On load and on `resize` / `orientationchange`:
  - `w = innerWidth, h = innerHeight`
  - If `h / w >= 560 / 360`: `scale = w / 360`, `VIEW_H = min(800, h / scale)`. If `h / scale > 800`, letterbox vertically (center canvas).
  - Else (landscape / desktop): `VIEW_H = 640`, `scale = h / 640`, center canvas horizontally.
  - Canvas CSS size = `360 * scale` by `VIEW_H * scale`. Backing store = CSS size * `min(devicePixelRatio, 2)`. Apply `ctx.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0)` so all drawing uses logical units.
- Page background `#0b0d12`. Body: `position: fixed; inset: 0; height: 100dvh` (with `100vh` fallback), `margin: 0; overflow: hidden`.

## S3. Game loop
- `requestAnimationFrame` render. Fixed update step of 1/60 s with an accumulator. Clamp frame delta to 0.1 s. Max 5 update steps per frame.
- States: `READY` (first load only) -> `PLAYING` -> `DEAD` -> `PLAYING` ...
- On `visibilitychange` to hidden while `PLAYING`: pause. On return: show "TAP TO RESUME", reset accumulator, resume on next press.

## S4. Input plumbing
- Use Pointer Events on the canvas: `pointerdown`, `pointerup`, `pointercancel`, `pointermove` (only if the game needs it). Use `setPointerCapture`.
- Keyboard mirrors touch for desktop (keys defined per game).
- Kill every browser gesture:
  - viewport meta: `width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover`
  - CSS on `html, body, canvas`: `touch-action: none; overscroll-behavior: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; -webkit-tap-highlight-color: transparent`
  - `preventDefault()` on `contextmenu`, `gesturestart`, `dblclick`, and on `touchmove` (registered with `{ passive: false }`).
- Input must be processed in the same frame it arrives. No debouncing, no input delay.

## S5. Death and restart (the most important part of the prototype)
- On death: hit-stop 100 ms (world frozen, still rendering) -> death panel is visible immediately after, no entrance animation longer than 150 ms.
- Input lock: ignore presses for 250 ms after the moment of death (prevents accidental restart). After that, ANY fresh `pointerdown` anywhere (except the mute button) or Space/Enter restarts.
- A press that was already held at the moment of death does not count - require a new `pointerdown`.
- Restart goes straight to `PLAYING`. No countdown, no fade, no menu. The restart press also counts as game input for the new run.
- Target: a player who mashes the screen is playing again in under 0.5 s after dying.

## S6. HUD and screens
- HUD: score top-center (bold, ~48 units), best score top-left (small), combo text under score when combo > 1, mute toggle top-right (tap target at least 44 x 44 units).
- READY screen: codename, the one-line instruction given in the game spec, "TAP TO START".
- First run only: the instruction stays on screen for 3 s, then fades out.
- Death panel (whole screen is the retry button): final score, best, delta line (`NEW BEST` or `N from best`), `run #N` (session run counter), `TAP TO RETRY`.
- Greybox palette: background `#0b0d12`, road / track `#262b36`, markings `#8a93a6`, player `#e8f1ff`, danger `#ff4d4d`, pickup `#ffd23f`, bonus feedback `#3dff8b`, text `#ffffff`. Rectangles, circles and lines only.

## S7. Minimal juice (mandatory - a loop with no feedback cannot be evaluated)
- Screen shake on death: 8 units amplitude, decays over 250 ms.
- Bonus popup text: floats up 40 units and fades over 600 ms. Pool of 8.
- Screen-edge flash on bonus: `#3dff8b`, 120 ms.
- Audio, WebAudio oscillators only, no files:
  - bonus blip: square wave, 60 ms, frequency `440 * 2^(min(combo, 12) / 12)`
  - death: sawtooth 300 Hz sliding to 80 Hz over 250 ms
  - new best: three-note rising arpeggio
  - Create / resume `AudioContext` on the first `pointerdown`. Mute state persists.
- Haptics: `navigator.vibrate(15)` on bonus, `navigator.vibrate(80)` on death. Feature-check first (iOS has no support).

## S8. Determinism
- All gameplay randomness goes through a seeded `mulberry32` PRNG. Never call `Math.random()` for gameplay.
- `?seed=123` -> every run uses that seed. `?daily=1` -> seed is `YYYYMMDD` computed in UTC+8. Default -> new random seed per run.
- Same seed must produce the same level sequence.

## S9. CONFIG and URL overrides
- One `const CONFIG = { ... }` object at the top of the script. Every tunable number lives there with a short comment. No magic numbers in logic.
- Any URL param whose key matches a CONFIG key overrides it (parse as number when numeric, else string). Example: `?SPEED_START=30&NEAR_BONUS=80`.
- Active overrides are listed in the debug overlay.

## S10. Metrics (the reason this prototype exists)
Record per run: `{ n, seed, durationS, score, deathCause, retryLatencyMs }` where `retryLatencyMs` = time from previous death to this run's start (null for run 1).

Per session (one page load): `{ game, version, sessionId, tester, startedAt, runs: [...], lastActivityAt }`.
- `tester` comes from `?t=name` (optional).
- Keep the session in memory. On each death and on `pagehide`, write it to localStorage under `gbx_<game>_sessions` (array, keep last 50). Wrap every storage call in try/catch.
- Also persist best score and mute flag under the same prefix.

Debug overlay:
- Enabled by `?debug=1` or by tapping the top-left corner 5 times within 2 s.
- Shows: FPS (1 s average), current difficulty values (speed etc.), seed, active overrides, and session stats: runs, retries (runs - 1), average and median run duration, average retry latency, best score, death cause counts.
- `COPY STATS` button: copies the session JSON via `navigator.clipboard.writeText`. If that fails, show the JSON in a full-screen `<textarea>` with a close button so it can be copied manually.

Remote logging (implement - about 10 lines):
- If `?log=<url>` is present, send the session JSON to that URL on each death and on `pagehide` using `navigator.sendBeacon(url, new Blob([json], { type: 'text/plain' }))`. Fail silently.

## S11. Performance
- No allocations inside the update / render loop: pre-allocated pools for obstacles, popups, particles. No `filter` / `map` / spread / closures per frame.
- No `shadowBlur`, no per-frame gradients, no `getImageData`.
- Must hold 60 fps on a low-end Android phone.

## S12. Code layout (in this order, separated by comment banners)
`CONFIG` -> RNG -> state -> resize -> input -> level generation -> update -> render -> HUD / screens -> audio -> metrics / debug -> boot.
Plain functions and objects are fine. Short comments only where the logic is not obvious.

## S13. Out of scope for every greybox
Art, landmarks, branding, menus, settings, tutorials beyond the one-line instruction, leaderboards, sharing, accounts, analytics SDKs, ads, car selection, upgrades, multiplayer, start-light sequence.

## S14. Deliverable
1. One code block containing the complete `index.html`. No placeholders, no "rest unchanged", no TODOs.
2. After the code: `Assumptions` (choices made where the spec was silent) and `Tune first` (the 5 CONFIG keys most likely to change feel).

## S15. Shared acceptance checklist
- [ ] Opens from `file://`, zero console errors.
- [ ] On a phone: no scroll, no zoom, no text selection, no context menu during play.
- [ ] Death to playing again with one press; under 0.5 s is achievable.
- [ ] A held press at death does not restart; a fresh press does.
- [ ] Same `?seed=` gives an identical level sequence.
- [ ] Debug overlay toggles both ways; `COPY STATS` works or falls back to textarea.
- [ ] Rotate / resize does not break layout or gameplay.
- [ ] Audio only starts after first press; mute persists across reloads.
- [ ] Tab hidden -> paused; returns with "TAP TO RESUME".
- [ ] All tunables are in CONFIG and overridable via URL.
