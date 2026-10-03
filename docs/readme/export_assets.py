#!/usr/bin/env python3
"""Regenerate the README images straight from index.html.

Everything is rendered by the game's own drawing code in headless Chrome, so
the tiles always match what players see. Nothing in index.html is changed.

    python3 docs/readme/export_assets.py            # everything
    python3 docs/readme/export_assets.py tiles      # landmarks, vehicles, signs
    python3 docs/readme/export_assets.py streets    # one screenshot per district

Needs: pip install playwright (uses the installed Google Chrome).
"""
import base64
import functools
import http.server
import pathlib
import sys
import threading

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "img"

# Landmark tiles: (KL_LANDMARKS id, zone key whose sky is used, skip groups)
LANDMARKS = [
    ("twinTowers", "klcc", []),
    ("klTower", "bukitBintang", []),
    ("merdeka118", "petalingStreet", []),
    ("exchange106", "brickfields", []),
    ("sultanAbdulSamad", "dataranMerdeka", []),
    ("centralMarket", "pasarSeni", []),
    ("kasturiGate", "pasarSeni", []),
    ("petalingGate", "petalingStreet", []),
    ("littleIndiaGate", "brickfields", []),
    ("sentralTowers", "brickfields", []),
    ("theanHou", "theanHou", []),
    ("ilhamTower", "ilham", []),
    ("greatEasternMall", "ampang", []),
    ("batuCaves", "batuCaves", []),
    ("monorailStation", "bukitBintang", []),
]

# District screenshots: zone key -> file name. The names are what README.md links to, so they
# stay put when a zone is added to KL_ZONES; a zone that is not listed here gets no screenshot.
DISTRICT_FILES = {
    "bukitBintang": "district-1-bukitBintang.png",
    "petalingStreet": "district-2-petalingStreet.png",
    "pasarSeni": "district-3-pasarSeni.png",
    "brickfields": "district-4-brickfields.png",
    "theanHou": "district-4b-theanHou.png",
    "dataranMerdeka": "district-5-dataranMerdeka.png",
    "ilham": "district-6-ilham.png",
    "klcc": "district-7-klcc.png",
    "ampang": "district-8-ampang.png",
    "batuCaves": "district-9-batuCaves.png",
}
STREET_SPEED = 72   # m/s, fixed for the whole screenshot run

# Order of makeSprite() calls in buildSprites(); kapcai keys follow KAPCAI_KEYS.
SPRITE_ORDER = ["playerCar", "hatchback", "kapcai", "kapcaiPlain",
                "kapcaiJade", "kapcaiMelon", "kapcaiMagenta", "coneRow", "barrier"]

# Records every canvas created by makeSprite() (the sprite table lives inside the game's IIFE).
CAPTURE_SPRITES = """
(() => {
  const orig = Document.prototype.createElement;
  window.__spriteCanvases = [];
  Document.prototype.createElement = function (tag) {
    const el = orig.apply(this, arguments);
    if (String(tag).toLowerCase() === 'canvas' && (new Error().stack || '').indexOf('makeSprite') !== -1) window.__spriteCanvases.push(el);
    return el;
  };
})();
"""

# Shared helpers injected into the page for tile composition.
TILE_JS = """
window.__rw = {
  mk(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; },
  sky(g, W, H, cols) {
    const grd = g.createLinearGradient(0, 0, 0, H);
    grd.addColorStop(0, cols[0]); grd.addColorStop(0.6, cols[1]); grd.addColorStop(1, cols[2]);
    g.fillStyle = grd; g.fillRect(0, 0, W, H);
    const rnd = klLcg(W * 7 + H);
    for (let i = 0; i < 70; i++) { g.globalAlpha = 0.25 + rnd() * 0.5; g.fillStyle = '#ffffff'; g.fillRect(rnd() * W, rnd() * H * 0.6, 1.4, 1.4); }
    g.globalAlpha = 1;
  },
  ground(g, W, H, y) { g.fillStyle = '#07080c'; g.fillRect(0, y, W, H - y); g.fillStyle = 'rgba(255,210,140,0.18)'; g.fillRect(0, y, W, 2); },
  png(c) { return c.toDataURL('image/png'); },
  fit(src, w, h, maxW, maxH) { const s = Math.min(maxW / w, maxH / h); return s; }
};
"""


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d/index.html" % httpd.server_address[1]


def save(name, data_url):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    print("  wrote", (OUT / name).relative_to(ROOT))


def export_tiles(browser, url):
    page = browser.new_page(viewport={"width": 360, "height": 780}, device_scale_factor=2)
    page.add_init_script(CAPTURE_SPRITES)
    page.goto(url + "?QUALITY=high")
    page.wait_for_selector("html[data-game-ready]", state="attached", timeout=60000)
    page.evaluate(TILE_JS)

    print("landmarks")
    for lm_id, zone_key, skip in LANDMARKS:
        data = page.evaluate("""([id, zoneKey, skip]) => {
          const R = window.__rw, T = 640, lm = KL_LANDMARKS[id];
          const zone = KL_ZONES.find(z => z.key === zoneKey);
          const c = R.mk(T, T), g = c.getContext('2d');
          R.sky(g, T, T, zone.sky);
          const floorY = T - 44;
          R.ground(g, T, T, floorY);
          // fit the landmark into the tile, then bake it at that size (2x) so the glow scales with it
          const h = Math.min(T - 110, (T - 70) * lm.h / lm.w);
          const r = bakeLandmark(id, h, { bake: 2, skipGroups: skip }, R.mk);
          if (id === 'monorailStation') {
            const pier = bakeLandmark('monorailPier', 150, { bake: 2 }, R.mk);
            const beamY = floorY - 150 + 20;
            drawBaked(g, pier, T / 2 - 150, floorY); drawBaked(g, pier, T / 2 + 150, floorY);
            g.fillStyle = '#5d6676'; g.fillRect(0, beamY, T, 10);
            drawBaked(g, r, T / 2, beamY);
            const train = bakeLandmark('monorailTrain', 58, { bake: 2 }, R.mk);
            drawBaked(g, train, T / 2 + 40, beamY + 10);
          } else if (id === 'sultanAbdulSamad') {
            // framed like the Dataran Merdeka photo: KL Tower small behind, lawn and royal palms in front
            const lawnTop = T - 150;
            const tower = bakeLandmark('klTower', 250, { bake: 2 }, R.mk);
            drawBaked(g, tower, T / 2 - 70, lawnTop - 20, 0.8);
            drawBaked(g, r, T / 2, lawnTop + 4);
            const lawn = g.createLinearGradient(0, lawnTop, 0, T);
            lawn.addColorStop(0, '#1d4428'); lawn.addColorStop(1, '#0d2415');
            g.fillStyle = lawn; g.fillRect(0, lawnTop, T, T - lawnTop);
            g.fillStyle = 'rgba(255,210,140,0.16)'; g.fillRect(0, lawnTop, T, 2);
            const palm = bakeLandmark('royalPalm', 150, { bake: 2 }, R.mk);
            [38, 128, 214, 426, 512, 602].forEach(x => drawBaked(g, palm, x, lawnTop + 26));
          } else {
            drawBaked(g, r, T / 2, floorY + 4);
          }
          return R.png(c);
        }""", [lm_id, zone_key, skip])
        save("landmark-%s.png" % lm_id, data)

    print("vehicles and hazards")
    n = page.evaluate("window.__spriteCanvases.length")
    if n != len(SPRITE_ORDER):
        raise SystemExit("expected %d sprite canvases, captured %d - buildSprites() changed?" % (len(SPRITE_ORDER), n))
    for i, key in enumerate(SPRITE_ORDER):
        data = page.evaluate("""(i) => {
          const R = window.__rw, src = window.__spriteCanvases[i], T = 360;
          const c = R.mk(T, T), g = c.getContext('2d');
          const grd = g.createLinearGradient(0, 0, 0, T);
          grd.addColorStop(0, '#1a1d26'); grd.addColorStop(1, '#2b2f3a');
          g.fillStyle = grd; g.fillRect(0, 0, T, T);
          g.fillStyle = 'rgba(255,255,255,0.45)';
          for (let y = -10; y < T; y += 60) { g.fillRect(16, y, 5, 34); g.fillRect(T - 21, y, 5, 34); }   // lane dashes
          const s = Math.min((T - 60) / src.width, (T - 60) / src.height);
          const w = src.width * s, h = src.height * s;
          g.fillStyle = 'rgba(0,0,0,0.45)'; g.beginPath(); g.ellipse(T / 2, (T + h) / 2 - 4, w * 0.48, 10, 0, 0, 6.2832); g.fill();
          g.drawImage(src, (T - w) / 2, (T - h) / 2, w, h);
          return R.png(c);
        }""", i)
        save("vehicle-%s.png" % key, data)

    print("street details")
    sheets = page.evaluate("""() => {
      const R = window.__rw, A = buildKLStreetAssets(R.mk, 2), out = {};
      function sheet(items, cols, cellW, cellH, bg) {
        const pad = 18, rows = Math.ceil(items.length / cols);
        const W = cols * cellW + (cols + 1) * pad, H = rows * cellH + (rows + 1) * pad;
        const c = R.mk(W, H), g = c.getContext('2d');
        g.fillStyle = bg; g.fillRect(0, 0, W, H);
        items.forEach((it, i) => {
          const x = pad + (i % cols) * (cellW + pad), y = pad + Math.floor(i / cols) * (cellH + pad);
          const s = Math.min(cellW / it.w, cellH / it.h), w = it.w * s, h = it.h * s;
          g.drawImage(it.canvas, x + (cellW - w) / 2, y + (cellH - h) / 2, w, h);
        });
        return R.png(c);
      }
      const b = A.board;
      out.boards = sheet([b.once.kopitiamChinese, b.once.bananaLeafTamil].concat(b.heritage, b.modern, b.indian), 3, 380, 160, '#221a17');
      const S = A.sign;
      out.signs = sheet([S.speed60, S.speed30, S.noUturn, S.straight, S.busStop, S.roadworks, S.awas, S.tamat], 4, 190, 150, '#15181f');
      out.sepang = sheet([S.sepang], 1, 540, 448, '#15181f');
      out.blades = sheet([].concat(A.blade.heritage, A.blade.modern, A.blade.indian), 12, 60, 198, '#221a17');
      out.flag = sheet([A.flag], 1, 400, Math.round(400 * A.flag.h / A.flag.w), '#1a2030');
      out.lamps = sheet(A.pillar.concat([A.lampSpiral]), 4, 120, 320, '#1a1422');
      out.fallback = b.once.kopitiamChinese.usedFallback || b.once.bananaLeafTamil.usedFallback;
      return out;
    }""")
    if sheets.pop("fallback"):
        print("  WARNING: no CJK/Tamil font here - the kopitiam / banana-leaf boards used the Latin fallback")
    for k, v in sheets.items():
        save("street-%s.png" % k, v)
    page.close()


def export_streets(browser, url):
    print("district screenshots")
    ctx = browser.new_context(viewport={"width": 360, "height": 720}, device_scale_factor=2,
                              is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.clock.install()
    page.goto(url + "?QUALITY=high&seed=7&SPEED_START=%d&SPEED_MAX=%d&HITBOX_X=0" % (STREET_SPEED, STREET_SPEED))
    for _ in range(600):                                   # boot bakes are queued setTimeouts
        if page.evaluate("document.documentElement.hasAttribute('data-game-ready')"):
            break
        page.clock.run_for(100)
    else:
        raise SystemExit("game never became ready")
    zones = page.evaluate("KL_ZONES.map(z => z.key)")
    zone_dist = page.evaluate("KL_STREET.ZONE_LEN")
    page.click("text=PLAY NOW")
    t = 0.0
    for i, key in enumerate(zones):
        name = DISTRICT_FILES.get(key)
        if not name:
            continue                                       # zone without a README shot
        # SPEED_START = SPEED_MAX pins the speed, so distance is exactly speed * run time.
        # (The HUD score is no use for calibration: it also counts pickup bonuses.)
        # Aim for the middle of each zone. Batu Caves only takes over the skyline late
        # (its gate is delayed), so shoot that one near the end.
        frac = 0.85 if key == 'batuCaves' else 0.5
        target = (i + frac) * zone_dist / STREET_SPEED
        page.clock.run_for(int((target - t) * 1000))
        t = target
        page.screenshot(path=str(OUT / name))
        print("  wrote", name)
    ctx.close()


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, url = serve()
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome")
            except Exception:
                # No Google Chrome here (e.g. WSL): Playwright's own Chromium works, but it only has
                # the fonts installed on this machine, so text can differ from the committed images.
                print("WARNING: Google Chrome not found - using Playwright's bundled Chromium")
                browser = p.chromium.launch()
            if what in ("all", "tiles"):
                export_tiles(browser, url)
            if what in ("all", "streets"):
                export_streets(browser, url)
            browser.close()
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
