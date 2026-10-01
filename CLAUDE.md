# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project at a glance

Racerweek is a self-contained mobile browser game: a three-lane endless dodger set across stylized Kuala Lumpur districts. `index.html` is the canonical source. It contains both the crawlable launch page and the expanded v0.4.5 Kuala Lumpur game. There is no package manager, framework, build step or runtime asset loading. Production minification is a release step only, so always edit the readable source, not the generated file.

The original prototype contract (`greybox-A-lanes.md`) was removed from the tree; it is still in git history (before the licence commit) if the core-loop, collision, scoring or determinism rationale is ever needed.

The reference images live in `assets-archive/` (for example `unnamed (2).jpg` for the target look, and `kl-signs-sheet.png` / `kl-signs-in-street.png` for signage) and in `twintower/`. They are references only: the game draws everything with inline Canvas 2D code and must not depend on image files. `arhive/index.html` is the version from before the route was expanded; do not edit it.

## Running and testing

`index.html` works from `file://`. For browser automation a static server is easier:

```sh
python -m http.server 8000     # then open http://127.0.0.1:8000/index.html
```

There is no lint or test runner. The tests are the page's own self-tests: load `?selftest=1` and read the `[selftest]` console lines. They run from `runNextBootTask()` after the boot bake queue finishes:

- `rows=5000 fairness violations=0` (this must be 0)
- `klsFlagSelfTest: OK (0 violations)`
- `kopitiamChinese.usedFallback` / `bananaLeafTamil.usedFallback`: whether the device has fonts for the non-Latin boards
- `kapcaiKeyFor shares`, which should be close to 20/20/20/20/20 for `kapcai`, `kapcaiPlain`, `kapcaiJade`, `kapcaiMagenta`, `kapcaiMelon`

Query parameters:

- `?debug=1` enables the debug overlay and the `COPY STATS` control.
- `?selftest=1` runs the self-tests above.
- `?seed=123` fixes the gameplay sequence.
- `?daily=1` uses the UTC+8 daily seed.
- `?t=name` records a tester name in the session metrics.
- `?log=<url>` sends the whole session JSON with `sendBeacon` after every death and on `pagehide` (`sendRemoteLog`). Without it, session metrics stay only in `localStorage`.
- `?QUALITY=low` or `?QUALITY=high` forces a presentation-quality profile. It never affects gameplay or the RNG.
- `?ga=1` enables Google Analytics off the production host, for a local check. Do not leave it on during automated runs; it sends real hits.
- Any `CONFIG` key can be overridden, for example `?SPEED_START=30&ROW_GAP_T_START=1.4`. `?HITBOX_X=0` disables collisions, for observation-only runs.

For visual checks, test at least 360 x 780 (a tall phone), 360 x 560 (the shortest supported portrait ratio) and 1280 x 720 (desktop letterboxing and keyboard play).

The landing-page nickname is optional, and the field is currently hidden (`hidden` on `#playerName` and its label; remove both to bring it back). A name saved earlier is still pre-filled into the hidden field and applied, so returning players keep their tester name. A non-empty value is normalized, limited to 20 characters, stored as `racerweek_player_name`, and copied into `session.tester` (so it overrides `?t=`). An empty value starts immediately with no tester name. `PLAY NOW` enters the game. After that, mobile uses Pointer Events and desktop uses Arrow Left/Right or A/D. Space/Enter resumes or retries.

## Landing page and search metadata

The launch screen is a compact landing page (`#landing`, z-index 10, above `<canvas id="c">`). It has semantic HTML copy, the optional nickname field (currently hidden) and a `PLAY NOW` button. It stays up while the assets bake, then goes straight into gameplay with no navigation or page load. The dark gradient and sparse stars are generated locally. Once the assets are baked, `drawLandingSkyline` adds a night skyline of baked `KL_LANDMARKS` along the bottom edge (`LANDING_SKYLINE_NARROW` spreads it under the centred copy; `LANDING_SKYLINE_WIDE` keeps it in the side gutters on desktop). It is drawn once, and again on resize, never per frame. There is no car, road, image file, promotional image or external font.

The visible launch content must stay real DOM content, not Canvas-only text. The current search and sharing metadata:

- A descriptive `<title>` and meta description targeting a free Kuala Lumpur browser racing game.
- A canonical URL of `https://racerweek.com/`.
- Open Graph title, description, URL, site name and `en_MY` locale.
- A text-only Twitter summary card. Do not declare a large-image card unless an actual social image is added.
- JSON-LD co-typed as `VideoGame` and `WebApplication`, with `GameApplication`, browser/OS details and a zero-price offer.
- `robots.txt`, `sitemap.xml` and a top-level no-index `404.html`.

The support files are crawler and deployment infrastructure, not game dependencies; keep them in production deployments. The top-level `404.html` matters: without it, Cloudflare Pages assumes a single-page app and can return the homepage for any path, which creates duplicate URLs and soft-404s.

## Architecture

`index.html` is deliberately large. After the JSON-LD block, the landing markup and styles come first, followed by three inline script blocks in this order:

1. KL landmark registry and baked landmark/skyline/monorail rendering.
2. KL street pack: districts, perspective geometry, localized boards, flags, buildings, street furniture and signs.
3. The game, inside an IIFE: configuration, RNG, state, resizing, input, generation, update, sprites, world rendering, HUD/screens, audio, metrics/debug, landing handling and the boot loop.

Important data and rendering systems:

- `CONFIG`: gameplay, projection, fog, zone and gate tunables. URL overrides are applied right after it is declared.
- `KL_LANDMARKS`, `KL_PALETTES`, `KL_ZONES`, `KL_TRIO`: source of truth for landmark and zone art.
- `KL_DISTRICTS`, `KL_STREET`, `KL_BOARDS`, `KL_SIGNS`: source of truth for street-level dressing.
- `STATIC_VISUALS`, `VISUAL_SIZE`, `LIGHT_ANCHOR`, `sprites`: obstacle and vehicle presentation.
- `drawSkyAndSkyline`, `drawRoad`, `drawKLStreetBase`, `drawKLStreetSides`, `collectAndSort` and `render`: the main frame composition path.
- `drawHUD`, `drawZoneBanner` and `drawScreens`: interface states.
- `renderLandingArt`, `launchForm` and `landingVisible`: the landing background and the launch transition.

**Boot.** The heavy bakes run as queued `bootTasks`, one per `setTimeout`, so the browser can paint between them: skyline, sprites, skyline sprites, then street assets. `<html>` has `data-landing="1"` until the landing page is dismissed, and gets `data-game-ready="1"` when `assetsReady` is set. At that point the button changes from `PREPARING…` to `PLAY NOW`. For browser automation, wait for `html[data-game-ready]` and then click `PLAY NOW`.

**States.** PLAY NOW goes straight to PLAYING through `beginRun(true)`. Nothing ever sets `state = 'READY'` again: death leads to DEAD, and retry goes straight back to PLAYING. The canvas READY screen therefore only exists behind the landing page while booting; players never see it.

**Adaptive quality.**
- `lowResourceDevice` is true when `deviceMemory` or `hardwareConcurrency` is 4 or less, unless `QUALITY` overrides it. It lowers `SPRITE_DPR` and the street bake factor.
- While PLAYING, `updateFPS()` switches street LOD at runtime through `applyStreetLOD()`. It drops to `STREET_LOD_LOW` after 2 seconds below 45 fps, and returns to high after 5 seconds above 56 fps. It never returns to high on a low-resource device.
- For visual QA at a fixed tier, pass `QUALITY=`.

**Identifiers and storage.** The public game and version identifiers are `lanes` and `A-0.1`. Comments describe later visual revisions (`v0.3` to `v0.4.5`); do not assume `VERSION` was bumped for them. Best score, mute state and sessions use `gbx_lanes_best`, `gbx_lanes_mute` and `gbx_lanes_sessions`, built from `GAME_ID`. Renaming `GAME_ID` resets players' stored best scores.

## Guardrails

- Keep the one-file, vanilla ES2019, Canvas 2D implementation unless the user explicitly changes the delivery format.
- The landing art is limited to the gradient, stars and the baked `KL_LANDMARKS` skyline: no image files, no car, no road. Ask before adding other artwork. Its headline, description, form label and district list must stay real HTML for crawlability and accessibility.
- Do not add libraries, web fonts, network requests, runtime image dependencies, service workers, fullscreen calls or orientation locks. The one approved exception is Google Analytics 4 (`GA_ID`, `loadAnalytics`, `gtag`): it runs only on `racerweek.com` (or with `?ga=1`), and the script is injected after the boot bakes finish, never from `<head>`. It sends `game_start` from `beginRun` and `game_over` (score, cause, duration, run number, last announced zone) from `triggerDeath`. Keep `gtag` calls out of the per-frame update and render paths, and the game must keep working when the script is blocked.
- Keep the logical width at 360, with variable logical height and responsive letterboxing.
- Mobile portrait is the primary target, but desktop keyboard play must keep working.
- Keep gameplay randomness on the seeded `mulberry32` stream. Cosmetic variation must not change the gameplay RNG sequence.
- Keep tunable gameplay values in `CONFIG` and URL-overridable.
- Keep object pools. Avoid allocations, array transforms, readbacks, shadows or new gradients in update/render hot paths. Work done at bake time is fine.
- Preserve fast death-to-retry, pause/resume, session metrics, `localStorage` error handling and the remote logging behaviour.
- Keep public art, visible copy, source identifiers and comments free of motorsport-series, manufacturer, team, sponsor, livery and driver trademarks. The player is a generic stylized open-wheel race car. Geographic place names are allowed.
- Do not make the nickname mandatory without explicit approval. One-tap play with an empty name is a deliberate conversion choice.
- Keep canonical, Open Graph, JSON-LD, robots, sitemap and 404 behaviour aligned with `https://racerweek.com/`.
- Do not duplicate landmark drawings. `KL_LANDMARKS` is the single source of truth for a place wherever it appears.
- `KL_STREET.ZONE_LEN` must keep matching the final `CONFIG.ZONE_DIST`, including URL overrides.
- Changing visual size must not silently change collision size. Presentation and the forgiving gameplay hitbox are deliberately separate.
- Preserve user changes in this folder. The repo is pushed to the public GitHub remote `origin` (`git@github.com:shapito27/racerweek.com.git`) on branch `main`, but the reference material is untracked and exists only locally, so do not rely on Git alone for recovery. Everything committed is public: never commit secrets, `.dev.vars`, personal or work email addresses, or local paths. Commits use the repo-local identity `shapito27 <legionerust@yandex.ru>`. `.wrangler/` is ignored.

## Verification

After gameplay or rendering changes:

1. Load the page with no console or page errors.
2. Confirm the landing page is visible while booting, the button changes from `PREPARING…` to `PLAY NOW`, and `data-game-ready="1"` appears.
3. Test both ways in: no saved name, and a saved `racerweek_player_name` (check it gets normalized). Both must dismiss the landing page and start play; only the saved one should set a tester name. If the nickname field is visible again, also test typing a name. Check the landing skyline appears after `PLAY NOW` is enabled and does not cover the copy.
4. Run `?selftest=1` and check the expected lines above.
5. Check the launch, PLAYING, PAUSED, DEAD and retry states.
6. Check every district: Bukit Bintang, Jalan Petaling, Pasar Seni, Little India, Dataran Merdeka, the silent Ilham stretch, KLCC, the silent Jalan Ampang stretch (Great Eastern Mall) and Batu Caves. Verify each announced zone's gate and transition. The silent stretches intentionally have no gate, title, chime or player-facing name, so a death in Ilham must report Dataran Merdeka and a death in Ampang must report KLCC as the last announced zone.
7. Check hazards and pickups at far, mid and collision distance, not only in static beauty shots.
8. Check 360 x 780, 360 x 560 and a desktop landscape viewport.
9. Confirm the mute target, the debug corner gesture, the debug copy fallback, resize/orientation handling and pause-on-hidden.
10. When changing timing or projection, test both the normal values and safe URL overrides such as `HITBOX_X=0`.
11. For SEO changes, inspect the rendered title, description, canonical, social metadata, JSON-LD, visible `<h1>`, form label and nickname behaviour.
12. For a production release, check that `/` returns `200`, `/robots.txt` returns `200 text/plain`, `/sitemap.xml` returns `200 application/xml`, and an unknown path returns a real `404` containing `noindex`.

Chromium currently shows no page errors. It does show a Canvas 2D performance warning, because the font-support probe calls `getImageData`; that happens during setup, not in the frame loop.

## Cloudflare Pages release

Production is the Cloudflare Pages project `racerweek`, with canonical domain `https://racerweek.com/`.
- **Custom domains:** apex and `www` are both configured. `www` should 301 to the apex through a zone Redirect Rule, so the game only ever runs on one origin (one `localStorage`, one cookie).
- **`racerweek.pages.dev`:** not a public alternative. A Bulk Redirect sends it and its subpaths to the canonical domain with a 301, keeping paths and query strings.

Do not deploy the project directory as-is, because it contains reference material. Build a small temporary folder with only the production files:

```sh
mkdir -p /tmp/racerweek-cloudflare-optimized
npx -y html-minifier-terser@7.2.0 index.html \
  -o /tmp/racerweek-cloudflare-optimized/index.html \
  --collapse-whitespace --remove-comments --remove-redundant-attributes \
  --remove-script-type-attributes --remove-style-link-type-attributes \
  --minify-css true --minify-js true
npx -y html-minifier-terser@7.2.0 404.html \
  -o /tmp/racerweek-cloudflare-optimized/404.html \
  --collapse-whitespace --remove-comments --minify-css true
cp robots.txt sitemap.xml /tmp/racerweek-cloudflare-optimized/
npx -y wrangler@latest pages deploy /tmp/racerweek-cloudflare-optimized \
  --project-name racerweek --branch main --commit-dirty=true
```

`--branch main` is a Pages deployment label, not a git branch.

After deploying:
- **Check the custom domain,** not just the unique deployment URL.
- **Check the redirects:** `racerweek.pages.dev` and `www.racerweek.com` should both return `301` to `racerweek.com`, for `/` and for a sample path with a query string.
- **Don't add caching rules.** Cloudflare Pages already provides CDN caching, Brotli, HTTP/3 and global delivery. Custom Cache Everything rules can serve stale files after a deploy.

Resolvers can keep old nameserver records cached after the registry delegation is correct. If a request still reaches the former Porkbun/OpenResty origin, compare the `.com` delegation and several public resolvers before changing Pages or DNS records.
