# Racerweek: metrics, player identity and leaderboard groundwork — design

Date: 2026-09-21. Status: approved in brainstorming, awaiting written-spec review.

## 1. Goals and non-goals

**Goals**

1. Collect play metrics from real players, so the README playtest (`README-greybox-pack.md`) can be measured: median retries per session, session length, retry latency, and next-day return. They can also be split by UTM campaign, platform and quality tier.
2. Keep each player's racer name and best score in the browser, on desktop and mobile. Restore them after browser storage is wiped, for example by Safari's 7-day rule.
3. Store every run on Cloudflare (D1), so a leaderboard can be built later without changing the schema.
4. Give every leaderboard player a unique name, owned by their Google account. Guests may not play under a name a leaderboard player has claimed.
5. Never lose a run result, including while redirecting to Google sign-in.

**Non-goals (for now)**

- The leaderboard display and its API (phase 3 gets its own short brainstorm).
- Replay-based anti-cheat (phase 3).
- Admin UI, self-service rename or account deletion (done by hand on request), and a cookie-consent banner.

**Expected load:** 1,000–2,000 players per day.

## 2. Constraints carried over from the project

- The game stays one `index.html` file: vanilla ES2019 and Canvas 2D, with no libraries, web fonts, images or external scripts.
- Gameplay randomness stays on the seeded `mulberry32` stream. Name suggestions use `Math.random`.
- No work is added to the update/render hot paths. Queue work happens only at death, on tab hide, and on page load.
- All `localStorage` access stays wrapped in try/catch, and the game must work when storage is unavailable.
- `?log=` (`sendRemoteLog`), COPY STATS and `gbx_lanes_sessions` keep their current behaviour.
- Fast death-to-retry and one-tap PLAY NOW are preserved.

## 3. Architecture and phases

Cloudflare Pages Functions + D1 on the same origin as the game (`https://racerweek.com/api/*`).

| Phase | Ships | Depends on |
|---|---|---|
| 1 | www→apex redirect, D1, `/api/batch`, `/api/me`, browser run queue, local-best fix, UTM, `quit` records, suggested racer names + name rules (browser-only), debug queue line | — |
| 2 | Google sign-in from the crash screen, name claiming, taken-name check for guests, attaching guest runs to a player, privacy page | phase 1, Google Cloud OAuth client |
| 3 | `bests` table, leaderboard API/UI, replay verification | phase 2 |

Each phase ships and is useful on its own. This spec covers phases 1 and 2 in full; phase 3 is only sketched. Implementation plans are written one phase at a time.

## 4. Identity

All cookies are `HttpOnly; Secure; SameSite=Lax`. They are set only by the server, and scripts never read them.

| Cookie | Path | Lifetime | Content | Phase |
|---|---|---|---|---|
| `rw_did` | `/api` | 400 days, renewed on every `/api` response | random 128-bit device ID (base64url) | 1 |
| `rw_sid` | `/api` | 400 days, renewed | `player_id.issued_at`, signed with HMAC-SHA256 (`AUTH_SECRET`) | 2 |
| `rw_oauth` | `/api/auth` | 10 min | signed `{state, pkce_verifier, t}` | 2 |
| `rw_pending` | `/api` | 30 min | signed `{google_sub, t}` for a new account that hasn't claimed a name yet | 2 |

- **Cookie paths are scoped to every endpoint that reads the cookie, not to where it is set.** `rw_pending` is set by `/api/auth/google/callback` but read by `/api/claim`, so it must stay `Path=/api`.
- **Why server-set cookies:** Safari deletes script-writable storage after 7 days without a visit, but not cookies set by the site's own server (same origin, same IP). The 400-day lifetime is Chrome's maximum.
- **No `devices` table:** the device ID is just a random value, so creating one costs no database write.
- **Where the device ID comes from:** always from the cookie, never from a request body.
- **Signed values:** they are compared in constant time. Changing `AUTH_SECRET` signs everyone out.
- **Prerequisite for phase 1:** `www.racerweek.com` must 301 to `https://racerweek.com`, using a zone Redirect Rule (`https://www.racerweek.com/*` → `https://racerweek.com/${1}`, keep the query string). Otherwise www is a separate origin, with its own `localStorage` and cookie.

## 5. Data model (D1)

The database `racerweek` is created with `--location apac`. The `racerweek-preview` database is used for preview deployments.

### Migration 0001 (phase 1)

```sql
CREATE TABLE batches (
  device_id    TEXT    NOT NULL,          -- from rw_did
  batch_id     TEXT    NOT NULL,          -- client-generated, time-sortable
  v            INTEGER NOT NULL,          -- payload format version (1)
  session_id   TEXT    NOT NULL,          -- existing session.sessionId
  started_at   INTEGER NOT NULL,          -- session start, client clock, ms
  tester       TEXT,                      -- ?t= value
  nickname     TEXT,                      -- racer name used in this session
  version      TEXT    NOT NULL,          -- game VERSION
  platform     TEXT    NOT NULL,          -- 'touch' | 'desktop'
  quality      TEXT    NOT NULL,          -- 'low' | 'high' (tier at page load)
  utm_source   TEXT,
  utm_medium   TEXT,
  utm_campaign TEXT,
  runs         TEXT    NOT NULL,          -- JSON array of runs, see below
  best         INTEGER,                   -- highest eligible score in this batch, NULL if none
  received_at  INTEGER NOT NULL,          -- server clock, ms
  player_id    INTEGER,                   -- set in phase 2
  PRIMARY KEY (device_id, batch_id)
) WITHOUT ROWID;
```

The key starts with the device and the batch ID starts with a timestamp, so the device's batches are stored in time order and no extra index is needed. Examples:
- The latest nickname: `ORDER BY batch_id DESC LIMIT 1`.
- The device's best score: `MAX(best)`.

**Run format (v1).** Each run is an array. The client sends 10 fields; the server appends field 11.

| # | Field | Notes |
|---|---|---|
| 0 | `n` | run number in the session (`runCount`) |
| 1 | `seed` | uint32 (`currentSeed`) |
| 2 | `daily` | 1 if `?daily` and no `?seed`, else 0 |
| 3 | `distance` | integer, `Math.floor(distance)`, exactly as the score uses it |
| 4 | `bonus` | integer, `bonusTotal` |
| 5 | `duration_ms` | `Math.round(runTime * 1000)` |
| 6 | `cause` | `'static'`, `'cutter'` or `'quit'` |
| 7 | `retry_ms` | `retryLatencyMs` or `null` |
| 8 | `played_at` | client clock, ms, at death or hide |
| 9 | `overrides` | the `activeOverrides` string, plus `seed=…` when `?seed` is set; `null` when none |
| 10 | `eligible` | **added by the server**: 1 or 0 |

The client does not send the score. The server computes `score = distance + bonus`.

**Metrics de-duplication.** A run is identified by `(session_id, n)`. The device ID is deliberately left out, so a batch re-sent under a new device ID still de-duplicates. When several records exist (a `quit` snapshot followed by the finished run, or a re-sent batch), the record in the latest `batch_id` wins. `docs/metrics.sql` applies this rule.

### Migration 0002 (phase 2)

```sql
CREATE TABLE players (
  id         INTEGER PRIMARY KEY,
  google_sub TEXT    NOT NULL UNIQUE,
  name       TEXT    NOT NULL,          -- as typed, normalized
  name_key   TEXT    NOT NULL UNIQUE,   -- uniqueness key, see §9
  created_at INTEGER NOT NULL
);
```

### Phase 3 sketch (not built now)

`bests(board, player_id, score, batch_id, achieved_at, PRIMARY KEY (board, player_id))` plus an index on `(board, score DESC)`.
- **Boards:** `all`, and `daily:YYYYMMDD` for daily-seed runs.
- **Writes:** a row is written only when a player improves.
- **Reads:** leaderboard responses are cached at the edge for about 30 s.

## 6. Run eligibility and local best

**Modified run.** A run counts as modified when either of these applies:
- Any `CONFIG` key is overridden in the URL (for example `?HITBOX_X=0`).
- `?seed=` is present.

These do **not** make a run modified: `?daily`, `?debug`, `?QUALITY`, `?t`, `?log`, `?selftest`, `?api`, `utm_*`, `fbclid`/`gclid`, and any other unknown parameter. Override detection already matches only exact uppercase `CONFIG` names.

**Local best (`gbx_lanes_best`).** A modified run never updates the local best and never shows NEW BEST. This is a small change inside `triggerDeath`.

**Server `eligible` rule (v1).** A run is eligible only if all of the following hold:
- `overrides` is `null` and `cause` is not `'quit'`.
- The server knows the game `version`. v1 knows `A-0.1`, with `SPEED_START=24`, `SPEED_MAX=72` and `SPEED_RAMP=0.6`.
- All fields are integers within their ranges.
- **Distance ceiling:** `distance ≤ dmax(T) × 1.01 + 5`, where T = `duration_ms / 1000`:
  - `dmax(T) = 24T + 0.3T²` when T ≤ 80.
  - `dmax(T) = 3840 + 72(T − 80)` when T > 80.
  - The 1% allows for the fixed-step integration overshoot (≈0.005·T). The +5 m allows for the 0.01 s rounding of short runs.
- **Bonus ceiling:** `bonus ≤ 100·N(N+1)/2 + 25·N`, where `N = floor(2T) + 2`. This is loose on purpose: it rejects only garbage. `N` deliberately over-estimates the number of rows, because rows are ≥ 0.5 s apart only once the ramp ends and are further apart before that. Do not tighten it without replay data, or honest runs get rejected.

Changing a speed constant in the game requires bumping `VERSION` and adding the new constants on the server in the same release. Eligibility can be recomputed later from the stored raw fields.

## 7. API (phase 1)

Every `/api` response:
- Sends `Cache-Control: no-store`.
- Renews `rw_did` (creating it if missing).

POST requests whose `Origin` header is present and not on the allow-list are rejected with 403. The allow-list comes from the variable `ALLOWED_ORIGINS` (comma-separated):
- `https://racerweek.com` in `wrangler.toml` `[vars]` for production;
- `http://localhost:8788` in `.dev.vars`;
- any `https://*.racerweek.pages.dev` in the preview environment.

All SQL uses prepared statements with bound parameters.

### `POST /api/batch`

- **Body:** `{"batches": [Batch, …]}`, at most 10 batches and at most 64 KB. `Batch` has `v`, `batch_id`, `session` (`id`, `started_at`, `tester`, `nickname`, `version`, `platform`, `quality`, `utm`) and `runs` (1–20 runs).
- **Validation is per batch.** The server:
  - checks types and ranges, with `platform` limited to `touch`/`desktop`, `quality` to `low`/`high` and `cause` to `static`/`cutter`/`quit`. These are enums, not free text;
  - re-cleans the UTM values (see below) and the nickname (name rules, §9);
  - computes `eligible` and `best`.
- Valid batches are written in one `DB.batch()` call using `INSERT OR IGNORE`.
- **Response `200`:** `{"results": {"<batch_id>": "ok" | "dup" | "invalid"}, "player": null}`. `player` is filled in phase 2.
- **Other statuses:**
  - `400`: the body is not parseable JSON.
  - `413`: the body is too large.
  - `503`: D1 error, including the free-plan daily limit being hit.
  - `429`: sent by the Cloudflare rate-limit rule.
- The server accepts every `v` it has ever shipped. Newer servers must not reject older queued batches.

### `GET /api/me`

- **Response:** `{"best": <int>, "nickname": <string|null>, "player": null}`.
  - `best` is `MAX(best)` over the device's batches, and from phase 2 also the player's.
  - `nickname` comes from the device's latest batch.
- **No database write.** When the cookie is missing, the response only sets it.

### UTM cleaning (client and server)

- **Fields:** only `utm_source`, `utm_medium` and `utm_campaign` are read.
- **Cleaning:** each is cut to 64 characters, and any character outside `[A-Za-z0-9._-]` is replaced with `_`. An empty value becomes `null`.
- **Timing:** captured once, at page load.
- **Display:** never rendered without escaping.

## 8. Browser side (phase 1)

### API gating

The network is used only when `location.hostname === 'racerweek.com'` or `?api=1`. `file://` and `python -m http.server` make no requests and produce no console errors.

### Queue storage (one key per item, so two tabs never overwrite each other)

| Key | Content |
|---|---|
| `racerweek_sess_<session_id>` | session info: `started_at`, `tester`, `nickname`, `version`, `platform`, `quality`, `utm`, `updated_at` |
| `racerweek_run_<session_id>_<n>` | one unsealed run (array, fields 0–9) |
| `racerweek_batch_<batch_id>` | one sealed batch, waiting for the server to confirm it |

**IDs.** `batch_id` = `Date.now()` in base36, padded to 9 characters, then `-` and 16 hex characters from `crypto.getRandomValues`.
- **Don't use `crypto.randomUUID`:** it only exists on secure origins, so it would be missing on `http://192.168.x.x` LAN testing. `getRandomValues` works everywhere.
- **Fallback:** `Math.random` is used only if `window.crypto` is missing entirely.
- **Session IDs:** `session_id` keeps the existing `makeSessionId()`.

**Sealing.** Sealing groups a session's unsealed runs (in `n` order, at most 20 per batch) into a new batch key, and only then deletes those run keys. If a crash happens in between, a run can end up in two batches; the de-duplication rule in §5 handles that.

**Size limit.** At most 50 batch keys; beyond that, the oldest `batch_id` is deleted. Unsealed runs from stale sessions are sealed on load, so this limit also bounds them.

**No storage.** If `localStorage` throws, the same logic runs on in-memory maps. Runs are then lost when the page closes, which is acceptable.

### Triggers

1. **At death** (after the existing `triggerDeath` work): write the run key, and create or update the session key (`updated_at`).
   - If this session has ≥ 10 unsealed runs, seal them and send with `fetch(…, {keepalive: true})`.
   - (Phase 2) If a signed-in player just set a new personal best, seal and send immediately.
2. **Tab hidden (`visibilitychange` → hidden) and `pagehide`:**
   - If a run is in progress (PLAYING or PAUSED), write it with `cause='quit'` under its run key, and update the session key. If the player comes back and finishes, the real result overwrites that key, or is sent later with the same `n`.
   - The `quit` snapshot never touches `session.runs`, `gbx_lanes_sessions`, the local best, or `?log=`.
   - Seal the session's unsealed runs.
   - Send every waiting batch with `sendBeacon`, at most 10 batches and ≤ 60 KB per beacon. There is no confirmation, so the batch keys stay.
   - The existing pause-on-hide behaviour is unchanged.
3. **Page load**, after boot. This never delays PLAY NOW.
   - Seal the unsealed runs of *other* sessions whose `updated_at` is more than 10 minutes old (tabs that closed without a hide event), then delete those session keys.
   - Then send every waiting batch with `fetch`, grouped up to 10 per request.
4. **Phase 2:** the sign-in form carries every waiting batch (§10).

**Response handling:**
- `200`: delete the batch keys whose result is `ok`, `dup` or `invalid`.
- `400` or `413`: delete the batches in that request.
- Anything else (network error, `429`, `5xx`, a `404` from a broken deploy, Cloudflare error 1027): keep everything and retry at the next trigger.
- There are no timers or retry loops.

### Restore

`GET /api/me` is called after boot, only when `gbx_lanes_best` is missing from `localStorage`, or after returning from sign-in (phase 2).
- **Best score:** `bestScore = max(local, server)`.
- **Nickname:** the server's nickname replaces the name field only if the player has not edited or rerolled it.

### Tester tag

`session.tester` = the `?t=` value if present, otherwise the racer name. Batches store `tester` and `nickname` separately.

### Debug overlay (`?debug=1`)

One added line: `queue runs R · batches B · last HTTP S`.

## 9. Racer names

### Rules (shared by guests and leaderboard names)

- **Normalization:** trim, then collapse runs of whitespace to a single space.
- **Valid:** 3–20 characters, matching `^[A-Za-z0-9 _-]+$`.
- **`name_key`:** lowercase, with spaces, `_` and `-` removed. It must be ≥ 3 characters. "Ali Racer", "ali_racer" and "ALIRACER" share one key.
- **Blocked names:**
  - Reserved `name_key`s such as `racerweek`, `admin`, `moderator`, `official`, `support`, `guest`, `player`, `system`, `null` and `undefined` are blocked by exact match.
  - A short offensive-word list in English and Malay is matched as substrings of `name_key`. The owner reviews that list before phase 1 ships.
- **One rule set, two copies:** `index.html` holds a browser copy for hints, marked `/* @shared:names begin */ … /* @shared:names end */`. The server copy lives in `lib/names.mjs` and has the final say. A unit test extracts the browser copy and checks that both copies give the same answers on the same list of cases.

### Suggested names (phase 1, browser-only)

- **Format:** `Adjective Noun NN`, where NN is 10–99.
- **Words:** about 30 adjectives and 30 nouns, a KL-flavoured mix of English and Malay (for example Kilat, Pantas, Laju, Turbo, Neon / Harimau, Kancil, Enggang, Tapir, Kapcai, Durian). Nothing ethnic, religious, slang or trademarked. The owner reviews the final list.
- **Always valid:** every combination is ≤ 20 characters, valid and not blocked. A unit test checks every combination.
- **Source of randomness:** `Math.random`, never the gameplay RNG.

### Landing behaviour

- **First visit** (no `racerweek_player_name`): the field holds a suggested name as a real value, not a placeholder. PLAY NOW works immediately.
- **The ⚄ button** (inline SVG, accessible name "Suggest another name") sits inside the field and swaps in a new suggestion with a short slide animation. It works while the game is still loading. The animation is skipped under `prefers-reduced-motion`.
- **Focus** selects the whole value, so typing replaces it.
- **The field can't stay empty:**
  - Leaving it empty refills it with a new suggestion.
  - PLAY NOW while empty fills in a suggestion, pulses gently, and shows "We picked a name for you — tap PLAY NOW or change it". It does not start the game.
- **Invalid name:** PLAY NOW is blocked, the rule message appears under the field, and focus returns to it.
- **Label:** "Racer name" (was "Nickname (optional)"), with the hint "Your racer name · tap ⚄ for another".
- **Saving:** the name is saved to `racerweek_player_name` at PLAY NOW, as today, so returning visitors keep it.
- **Saved names from before this change:** a saved name that fails the rules (for example non-Latin, or shorter than 3 characters) is replaced by a suggestion at load. The hint reads "Please pick a new racer name (letters, digits, space, _ or -)".
- **Restoring from the server:** a nickname from `/api/me` is used only if it passes the rules.

### Taken-name check for guests (phase 2)

- **Endpoint:** `GET /api/name?n=…` returns `{"status": "free" | "taken" | "yours" | "invalid"}`. It's a single indexed read, sent with `no-store`.
- **While typing:** the check runs 400 ms after the last keystroke. Results are cached per value for the current page.
- **Hint text:**
  - `taken`: "Taken by a leaderboard player".
  - `invalid`: the rule message.
- **On PLAY NOW:**
  - `taken` or `invalid`: blocked.
  - A check still running: wait up to 1 s.
  - No answer (offline, no API, error): allowed.
- **Suggestions:** a suggestion that comes back `taken` is replaced silently, if the player hasn't touched it.
- **Saved name:** a saved name is checked once per visit. If it is now taken by someone else, the field is cleared, a fresh suggestion is filled in, and the message reads "Your saved name was claimed by a leaderboard player — please choose another".
- **Signed-in players:** the field shows their leaderboard name, read-only, with a small "Sign out" link. No check is needed.

## 10. Google sign-in (phase 2)

**Crash-screen control.** A DOM button over the canvas reading "Save to leaderboard · Sign in with Google", in its own area at the bottom.
- **When it shows:** in DEAD state, 700 ms after the crash.
- **When it's hidden:** at retry, for signed-in players, when the API is off, and in in-app browsers (user agent matches `FBAN|FBAV|FB_IAB|Instagram|Line/|TikTok|musical_ly|BytedanceWebview|Snapchat`). In-app browsers show the text "Open in Chrome or Safari to join the leaderboard" instead.
- **Taps:** taps on the button never reach the canvas.
- **Keyboard:** the global `keydown` handler (`index.html`, the Space/Enter branch) must skip its `preventDefault`/retry when the sign-in control has focus. Otherwise Space/Enter keep retrying.
- **Branding:** follows Google's sign-in branding rules, with the "G" mark as inline SVG.

**Flow**

1. **Tap.** A hidden form sends `POST /api/auth/google/start`, with field `batches` holding all waiting batches as JSON.
   - The body is `application/x-www-form-urlencoded`, not JSON. The server reads the `batches` field, parses it, and runs the same per-batch validator and insert as `/api/batch`. **Runs are stored before leaving the site.**
   - `/api/batch`'s "400 = unparseable JSON" rule does not apply here. A missing or broken `batches` field is ignored, and sign-in continues, because metrics must never block sign-in.
   - It creates `state` and a PKCE verifier (S256), sets `rw_oauth`, and replies `303` to Google's authorization endpoint with `response_type=code`, `scope=openid`, `prompt=select_account`, `code_challenge` and `state`.
   - The browser keeps its batch keys, because the navigation means it never sees a confirmation. After returning, it re-sends them; they come back as `dup` and are deleted.
2. **`GET /api/auth/google/callback`.** The server:
   - checks `state` against `rw_oauth`;
   - exchanges the code (client secret + verifier) at Google's token endpoint;
   - decodes the ID token and checks `iss` (`https://accounts.google.com` or `accounts.google.com`), `aud` (= client ID) and `exp`. The signature check is skipped because the token comes straight from Google over TLS, which OIDC Core §3.1.3.7 permits.
   - Only `sub` is used. No email or name is requested or stored.
3. **Known `sub`:** set `rw_sid`, attach runs (step 5), and redirect to `/?signin=ok`.
4. **New `sub`:** set `rw_pending` and redirect to `/?claim=1`.
   - The landing page shows "Choose your leaderboard name", prefilled with the current racer name, with the live check running. **Save name** sends `POST /api/claim {"name": …}`.
   - **`200`:** the player row is created, `rw_sid` is set, `rw_pending` is cleared, runs are attached, and the response is `{name, best}`.
   - **`409 taken`:** "taken, try another".
   - **`422 invalid`:** the rule message.
   - **`401 expired`:** "Sign-in expired, please sign in again".
5. **Attaching runs:** `UPDATE batches SET player_id = ? WHERE device_id = ? AND player_id IS NULL`. Every guest run from this device joins the player; runs already attached to someone else stay theirs.
6. **Back on the landing page:**
   - It calls `/api/me` and shows "Signed in as NAME · best N saved".
   - It removes the query with `history.replaceState`.
   - It caches `{name}` in `racerweek_player` for the next load.
7. **From then on:**
   - Batch inserts carry `player_id` whenever `rw_sid` is valid.
   - A batch response with `player: null` clears the cached signed-in state.
   - **Sign out** sends `POST /api/auth/logout`, which clears `rw_sid`.

**Failures**
- **Cancelled at Google, or `error=`:** redirect to `/?signin=cancelled`, showing "Your runs are saved on this device".
- **Bad or expired `state`, or a failed token exchange:** redirect to `/?signin=failed`, showing "Sign-in failed, please try again".

**Privacy page (`/privacy.html`, static, linked as "Privacy" from the landing page).**
- **Stored:** the device cookie, runs and session info, UTM values, racer name, Google account ID and leaderboard name.
- **Not stored:** email, real name, IP address.
- **Contact** for deletion or renames: privacy@racerweek.com.

## 11. Security summary

- Prepared statements only.
- Size limits on every body. Per-field validation.
- Origin allow-list on POST.
- Cookie flags as in §4. HMAC-signed values, compared in constant time.
- Secrets live only in Pages secrets or `.dev.vars` (gitignored), never in the repo or in logs.
- No IP address or full user agent is stored.
- **Rate limiting:** one Cloudflare rate-limiting rule on `/api/*`, 20 requests per 10 s per IP, blocking for 10 s. A burst of name checks while typing stays well under it, and so does sharing a carrier NAT. A blocked request gets `429`, which the client treats as retry-later.
- **Limits of that protection:** per-IP limits cannot fully protect the free-plan daily quota. The Workers Paid plan does, by turning the quota cliff into a small usage cost.

## 12. Capacity (2,000 players/day; 1.5 visits and 10–30 runs per player per day)

| | Typical | Heavy | Free limit |
|---|---|---|---|
| Function requests/day | ~12k | ~16k | 100k (resets 00:00 UTC) |
| D1 row-writes/day | ~12k | ~20k | 100k |
| D1 row-reads/day | small | small | 5M |
| Storage growth | ~2 MB/day | ~4.5 MB/day | 500 MB per database |

- **First visits:** the request figures include one `/api/me` call per first visit or Safari-wiped visit (≈ +1–2k/day). A first visit cannot be told apart from a wiped one without another cookie, so this call is accepted rather than avoided.
- **When the free limit is hit:** only `/api` fails. Static files never invoke Functions, so the game keeps working and runs wait in the queue.
- **Storage is the first limit,** at roughly 3–8 months. Check with `npx wrangler d1 info racerweek`.
- **Upgrade trigger:** move to **Workers Paid ($5/month)** at about 400 MB or before the leaderboard is promoted, whichever comes first. Paid includes 5 GB of storage and 50M writes per month.
- **No cleanup code:** deleting rows also counts as writes, and Pages Functions cannot run cron jobs.

## 13. Repository, build and deploy

```
index.html                 game + landing
privacy.html               phase 2
functions/api/batch.js, me.js                                   phase 1
functions/api/name.js, claim.js, auth/google/start.js,
functions/api/auth/google/callback.js, auth/logout.js           phase 2
lib/*.mjs                  shared server code (outside functions/, which would turn files into routes)
migrations/0001_batches.sql, 0002_players.sql
wrangler.toml              name, compatibility_date, pages_build_output_dir = "dist",
                           D1 bindings (production + preview), [vars] GOOGLE_CLIENT_ID
tests/*.test.mjs           node --test tests/  (Node 22, no dependencies, no package.json)
scripts/build.sh           minify index.html, 404.html, privacy.html into dist/, copy robots.txt, sitemap.xml
docs/metrics.sql           playtest queries (retries/session, session length, retry latency,
                           next-day return; by UTM, platform, quality), applying the §5 de-duplication rule
.gitignore                 + dist/  .dev.vars
robots.txt                 + Disallow: /api/
```

**Release:** `scripts/build.sh`, then `npx wrangler pages deploy --branch main --commit-dirty=true` from the repo root.
- **Bindings:** once `wrangler.toml` exists, it is the source of truth for bindings.
- **Migrations:** `npx wrangler d1 migrations apply racerweek --remote`, run before deploying code that needs them.

**Secrets:** `npx wrangler pages secret put AUTH_SECRET --project-name racerweek` (value from `openssl rand -base64 32`) and `GOOGLE_CLIENT_SECRET`. They take effect from the next deploy.

**Local development:** `npx wrangler pages dev` with the local D1, `.dev.vars` and `?api=1`. The Google OAuth client also lists `http://localhost:8788/api/auth/google/callback`.

**Owner actions in the Cloudflare dashboard:** the www redirect rule (§4) and the rate-limiting rule (§11).

**Owner actions in Google Cloud:**
- A project with an OAuth consent screen: External, app name Racerweek, authorized domain `racerweek.com`, privacy URL, scope `openid`.
- A Web-application client with both redirect URIs.
- Publish the app.

## 14. Testing

- **Unit tests (`node --test tests/`):**
  - name normalization, rules, `name_key` and blocklist;
  - the browser and server name rules agreeing;
  - every suggested-name combination being valid;
  - the distance and bonus ceilings, including the rounding and tolerance edge cases (T = 0.5 s, 1 s, 80 s, 300 s);
  - batch validation, including a bad batch among good ones;
  - UTM cleaning;
  - HMAC cookie signing and rejection of tampered values;
  - the ID-token claim checks.
- **Local end-to-end** (`wrangler pages dev` + a curl smoke script):
  - batch insert, then re-send (the results say `dup`);
  - `400` and `413`;
  - a mixed batch with valid and invalid runs;
  - `/api/me` without and with a cookie;
  - phase 2: name check, claim conflict, the full sign-in flow against the `localhost` callback.
- **Browser:**
  - the existing checklist in `CLAUDE.md`;
  - playing offline, then reloading online (each batch stored exactly once);
  - two tabs playing at the same time;
  - a beacon being sent when the tab is hidden;
  - a `quit` record, then resuming (the final result wins);
  - suggested-name UX (reroll, emptying the field, editing, invalid and taken names, restore after a wipe);
  - no network calls and no console errors under `python -m http.server` and `file://`;
  - `?selftest=1` still showing 0 fairness violations;
  - 360 × 780, 360 × 560 and desktop.
- **After the first production deploy:** compare the D1 row-write counts in the dashboard with §12, and confirm that `www` and `pages.dev` both return 301.

## 15. CLAUDE.md changes (made alongside each phase)

- **Network rule:** "No network requests" becomes "only same-origin `/api/*`, gated by hostname or `?api=1`".
- **Nickname rule:** "one-tap empty-name play" becomes "one-tap play with a suggested racer name. The name is never empty, and follows the §9 rules". Verification step 3 is updated to match.
- **New material:** commands (`node --test`, `wrangler pages dev`, migrations), the new release steps, and the new `localStorage` keys and cookies.
- **New rule:** bump `VERSION` in the same release as any change to speed or scoring constants, and add the matching server constants (§6).

## 16. To verify early in implementation

1. Real D1 row-write counts: a `WITHOUT ROWID` insert, and an ignored duplicate. Local D1 doesn't report them.
2. The flag syntax `wrangler d1 create --location apac`.
3. Whether the free plan includes one rate-limiting rule, and its allowed periods.
4. Whether Pages automatically invokes Functions for `/api/*` only.
5. Whether `wrangler pages dev` can serve the readable repo root while `pages_build_output_dir = "dist"`, and whether `pages deploy` with no folder argument uses the folder from `wrangler.toml`.
6. What Google requires to publish an `openid`-only app, and its button branding rules.
7. Whether `visibilitychange` fires on iOS when the app is swiped away.
8. The exact in-app browser user-agent strings.
9. The load assumptions in §12, checked against real phase 1 data.
10. Coordinating with the session currently editing Ilham Tower in `index.html` before phase 1 touches the same file.
