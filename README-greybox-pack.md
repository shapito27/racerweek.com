# KL race game - greybox pack

Three self-contained specs. Each one is a complete prompt: paste ONE file into a fresh model session and it should return one `index.html`.

| File | Codename | Input | Loop it tests |
|---|---|---|---|
| `greybox-A-lanes.md` | LANES | tap left / right | reflex + late-dodge risk |
| `greybox-B-sling.md` | SLING | hold / release | rhythm, grab and release timing |
| `greybox-C-junction.md` | JUNCTION | hold / release | greed vs safety under a chaser |

Every number in the specs is an untested starting value. Expect to tune.

## How to run the experiment
1. Build all three. Time-box each to half a day including tuning. Do not polish, do not add art.
2. First tuning target for each: a first-time player's first run lasts about 15-30 s, and death never feels unfair. Use URL overrides (`?SPEED_START=28`) on your phone instead of redeploying.
3. Host the three files (any static host). Add `?t=<name>` per tester and `?log=<your endpoint>` if you want stats without asking people to press COPY STATS.
4. Send links to 5-8 people with zero explanation. Do not watch over their shoulder on the first session.
5. Compare per game, first session only:
   - median retries per session (primary)
   - median session length
   - average retry latency (low = they are mashing retry = good sign)
   - did anyone open it again unprompted the next day

## Decision rule
- Median retries under 3 -> drop that loop.
- 5 or more -> candidate.
- If two are close, pick the one where YOU catch yourself replaying while testing.
- If none reaches 3: the problem is feel, not theme. Fix restart speed, input latency and first-death fairness before trying new ideas.
(These thresholds are my judgment - no source.)

## Known risks per spec
- A: safest to implement. Risk = feels generic; the near-miss tiers are what should save it.
- B: highest "one more try" ceiling, hardest to tune. If the first corner kills most new players, raise `TRACK_HALF_W` and `ASSIST_RATE` before anything else.
- C: balance between the two death causes is fragile. Watch the death cause counts in the debug overlay.

## Path from greybox to the KL skin (after a winner is picked)
- A -> pseudo-3D road through zones: Bukit Bintang neon, Dataran Merdeka, KL Tower, Petaling Street, Batu Caves. Static obstacles = cones, potholes, double-parked cars. Cutter = the small hatchback that changes lane without signalling. Pickup = teh tarik.
- B -> top-down night street circuit, each post is a roundabout or a landmark junction, corner counter becomes "Selekoh 12". Tyre marks and neon reflections carry the look.
- C -> the most local humour: junctions with kapcai swarms, buses, delivery riders; medians become mamak stalls; the pack is the race field chasing you through town.
- Add only after the loop is proven: start-light reaction launch, daily seed mode (already supported by `?daily=1`), share card, state leaderboard, billboards.

## Reminder on naming
Keep the public name and all assets free of "F1" / "Formula 1", team names, liveries and driver names. Stylised landmarks only.
