# Racerweek agent guide

## Project at a glance

This folder contains Racerweek, a self-contained mobile browser game: a three-lane endless dodger set across stylized Kuala Lumpur districts. `index.html` is the canonical source and contains both the crawlable launch page and the expanded v0.4.5 Kuala Lumpur game. There is no package manager, framework, or runtime asset loading. Production minification is a release step only; edit the readable source, not the generated artifact.

The original prototype contract is in `greybox-A-lanes.md`. It remains the source for the core loop, input, collision, scoring, determinism, metrics, and mobile-browser constraints, but `index.html` has since grown into a KL-themed implementation with landmarks, district streets, signs, gates, monorail elements, richer vehicles, and zone transitions.

The initial screen is a compact, image-free landing page with semantic HTML copy, an optional nickname field, and a `PLAY NOW` action. It sits above the game Canvas while assets bake, then transitions directly into gameplay without navigation or another page load. The dark gradient and sparse star field are generated locally; the landing page has no car, landmark montage, road, promotional image, or external font.

Supporting references (currently under `assets-archive/` unless noted):

- `assets-archive/unnamed (2).jpg`: target/inspiration screenshot for the overall game view.
- `assets-archive/kl-signs-sheet.png`: road and shop-sign reference sheet.
- `assets-archive/kl-signs-in-street.png`: examples of the sign system placed in streets.
- `twintower/`: photo references for the Kuala Lumpur twin towers, skybridge, and KLCC podium/entrance.
- `README-greybox-pack.md`: experiment background and the path from greybox to KL art.

These images are references only. The game currently draws everything from inline Canvas 2D code and must not depend on external image files.

## Running and inspecting

`index.html` works from `file://`, but a static server is more convenient for browser automation:

```sh
python -m http.server 8000
```

Then open `http://127.0.0.1:8000/index.html`.

Useful query parameters:

- `?debug=1` enables the debug overlay and `COPY STATS` control.
- `?selftest=1` runs deterministic generation and visual-pack self-tests in the console.
- `?seed=123` fixes the gameplay sequence.
- `?daily=1` uses the UTC+8 daily seed.
- `?t=name` records a tester name in session metrics.
- `?QUALITY=low` or `?QUALITY=high` forces a presentation-quality profile for testing.
- Any key in `CONFIG` can be overridden, for example `?SPEED_START=30&ROW_GAP_T_START=1.4`.

For visual inspection, test at least:

- 360 x 780: representative tall phone.
- 360 x 560: shortest supported portrait ratio.
- 1280 x 720: landscape/desktop letterboxing and keyboard play.

The landing-page nickname is optional. A non-empty value is normalized, limited to 20 characters, stored as `racerweek_player_name`, and copied into `session.tester`; an empty value starts immediately without a tester name. Use the `PLAY NOW` button to enter the game. Once the landing page is dismissed, use Pointer Events on mobile and Arrow Left/Right or A/D on desktop. Space/Enter resumes or retries.

## Landing page and search metadata

The visible launch content must remain available as semantic DOM content rather than Canvas-only text. Current search and sharing metadata includes:

- A descriptive `<title>` and meta description targeting a free Kuala Lumpur browser racing game.
- A canonical URL of `https://racerweek.com/`.
- Open Graph title, description, URL, site name, and `en_MY` locale.
- A text-only Twitter summary card. Do not declare a large-image card unless an actual social image is added.
- JSON-LD co-typed as `VideoGame` and `WebApplication`, with `GameApplication`, browser/OS details, and a zero-price offer.
- `robots.txt`, `sitemap.xml`, and a top-level no-index `404.html`.

The support files are crawler/deployment infrastructure, not runtime game dependencies. Keep them in production deployments. The top-level `404.html` is important: without it, Cloudflare Pages assumes an SPA and can return the homepage for arbitrary paths, producing duplicate URLs or soft-404 behavior.

## File architecture

`index.html` is intentionally large. After the JSON-LD metadata block, its executable code remains ordered in three inline script blocks:

1. KL landmark registry and baked landmark/skyline/monorail rendering.
2. KL street pack: districts, perspective geometry, localized boards, flags, buildings, street furniture, and signs.
3. Game implementation: configuration, RNG, state, resizing, input, generation, update, sprites, world rendering, HUD/screens, audio, metrics/debug, and boot loop.

Landing-page markup and styles appear before the game scripts. The game script owns landing readiness, optional-name persistence, dismissal, and the one-shot star background. Heavy visual baking is split across queued boot tasks so the browser can paint first. The Play button remains disabled and reads `PREPARING…` until `data-game-ready="1"` is set, then changes to `PLAY NOW`.

Important data and rendering systems:

- `CONFIG`: gameplay, projection, fog, zone, and gate tunables. URL overrides are applied immediately after declaration.
- `KL_LANDMARKS`, `KL_PALETTES`, `KL_ZONES`, `KL_TRIO`: source of truth for landmark and zone art.
- `KL_DISTRICTS`, `KL_STREET`, `KL_BOARDS`, `KL_SIGNS`: source of truth for street-level dressing.
- `STATIC_VISUALS`, `VISUAL_SIZE`, `LIGHT_ANCHOR`, `sprites`: obstacle and vehicle presentation.
- `drawSkyAndSkyline`, `drawRoad`, `drawKLStreetBase`, `drawKLStreetSides`, `collectAndSort`, and `render`: principal frame composition path.
- `drawHUD`, `drawZoneBanner`, and `drawScreens`: interface states.
- `renderLandingArt`, `launchForm`, and `landingVisible`: landing background and launch transition.

The public game/version identifiers are `lanes` and `A-0.1`. Internal comments also describe later visual revisions (`v0.3` through `v0.4.5`); do not assume the public version was updated with those revisions.

## Guardrails for changes

- Preserve the one-file, vanilla ES2019, Canvas 2D implementation unless the user explicitly changes the delivery format.
- Preserve the current image-free landing design unless the user explicitly requests artwork. Its headline, description, form label, and district list must remain real HTML for crawlability and accessibility.
- Do not add libraries, web fonts, network requests, runtime image dependencies, service workers, fullscreen calls, or orientation locks.
- Keep the logical width at 360 and retain variable logical height/responsive letterboxing behavior.
- Treat mobile portrait as primary, but keep desktop keyboard play functional.
- Keep gameplay randomness on the seeded `mulberry32` stream. Cosmetic variation must not alter the gameplay RNG sequence.
- Keep tunable gameplay values in `CONFIG` and URL-overridable.
- Preserve object pools and avoid allocations, array transforms, readbacks, shadows, or new gradients inside update/render hot paths. Baking-time work is acceptable.
- Preserve fast death-to-retry behavior, pause/resume behavior, session metrics, localStorage error handling, and remote logging semantics.
- Keep public art, visible copy, source identifiers, and comments clear of motorsport-series, manufacturer, team, sponsor, livery, and driver trademarks. The player is a generic stylized open-wheel race car. Geographic place names are allowed.
- Do not make the nickname mandatory without explicit approval; one-tap empty-name play is an intentional conversion optimization.
- Keep canonical, Open Graph, JSON-LD, robots, sitemap, and 404 behavior aligned with `https://racerweek.com/`.
- Do not duplicate landmark drawings. `KL_LANDMARKS` is the single source of truth for a place wherever it appears.
- `KL_STREET.ZONE_LEN` must continue to match the final `CONFIG.ZONE_DIST`, including URL overrides.
- Changes to visual size must not silently change collision dimensions; presentation and the forgiving gameplay hitbox are deliberately separate.
- Preserve user changes in this folder. It is a local Git repo (no remote) but reference material is untracked, so do not rely on Git alone for recovery or state inspection.

## Verification expectations

After gameplay or rendering changes:

1. Load the page with no console or page errors.
2. Confirm the landing page is visible while booting, the button changes from `PREPARING…` to `PLAY NOW`, and `data-game-ready="1"` appears.
3. Test both conversion paths: submit an empty nickname and submit a normalized named nickname. Both must dismiss the landing page and start gameplay; only the named path should persist a tester name.
4. Run `?selftest=1`; fairness violations must remain zero, and `klsFlagSelfTest` must report `OK (0 violations)`.
5. Check READY/launch, PLAYING, PAUSED, DEAD, and retry states.
6. In `index.html`, check every district: Bukit Bintang, Jalan Petaling, Pasar Seni, Little India, Dataran Merdeka, the silent Ilham stretch, KLCC, and Batu Caves. Verify each announced-zone gate and transition. Ilham intentionally has no gate, title, chime, or player-facing name; death there must report Dataran Merdeka as the last announced zone.
7. Verify hazards and pickups at far, mid, and collision distance—not only static beauty shots.
8. Check 360 x 780, 360 x 560, and a desktop landscape viewport.
9. Confirm the mute target, debug corner gesture, debug copy fallback, resize/orientation handling, and visibility pause.
10. When changing timing or projection, test both normal values and safe URL overrides such as `HITBOX_X=0` for observation-only runs.
11. For SEO changes, inspect the rendered title, description, canonical, social metadata, JSON-LD, visible `<h1>`, form label, and optional nickname behavior.
12. For a production release, verify `/` returns `200`, `/robots.txt` returns `200 text/plain`, `/sitemap.xml` returns `200 application/xml`, and an unknown path returns a real `404` containing `noindex`.

Current Chromium inspection produces no page errors. It does emit a Canvas 2D performance warning because the font-support probe calls `getImageData`; this occurs during setup rather than the frame loop.

## Cloudflare Pages release

Production is the Cloudflare Pages project `racerweek` with canonical domain `https://racerweek.com/`. Both apex and `www` are configured as Pages custom domains. `https://racerweek.pages.dev` is intentionally not a public alternate: a Cloudflare Bulk Redirect rule sends it and its subpaths to the canonical domain with a permanent redirect while preserving path suffixes and query strings.

Do not deploy the readable project directory wholesale because it contains reference material. Build a small temporary output containing only the production files:

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

After deployment, verify the custom domain rather than relying only on the unique deployment URL. Also confirm that `racerweek.pages.dev` returns `301` to `racerweek.com` for both `/` and a sample path/query. Cloudflare Pages already supplies optimized CDN caching, Brotli, HTTP/3, and global delivery; avoid custom Cache Everything rules because they can serve stale Pages assets after a deployment.

Nameserver changes can remain cached at recursive resolvers after the registry delegation is correct. If a request still reaches the former Porkbun/OpenResty origin, compare the `.com` delegation and multiple public resolvers before changing Pages or DNS records.
