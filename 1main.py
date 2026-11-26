import network
import socket
import time
import math
from machine import Pin
import neopixel

# --- Wi-Fi Settings ---
WIFI_SSID = "AirFiber-11"
WIFI_PASS = "12345678"

AP_SSID   = "ESP32-LED-Control"
AP_PASS   = "12345678"
HOSTNAME  = "led"  # http://led.local

# --- Hardware Setup ---
PIN_L = 3
PIN_R = 4
NUM_LEDS = 5
ALL_MASK = (1 << NUM_LEDS) - 1  # 0x1F (5 LEDs: 1..5)

npL = neopixel.NeoPixel(Pin(PIN_L, Pin.OUT), NUM_LEDS)
npR = neopixel.NeoPixel(Pin(PIN_R, Pin.OUT), NUM_LEDS)

# --- Control State ---
enL = True
enR = True
ui_mode = "custom"  # "custom" (har LED ka apna color) ya "pattern" (1152 patterns)

maskL = ALL_MASK
maskR = ALL_MASK

# Har LED (1..5) ka default RGB color
colorsL = [
    (255, 0, 80),
    (255, 120, 0),
    (0, 220, 255),
    (130, 60, 255),
    (0, 255, 140),
]
colorsR = [
    (0, 220, 255),
    (130, 60, 255),
    (255, 0, 80),
    (255, 180, 0),
    (0, 255, 140),
]

pattern_id = 1
speed_val = 7       # 1 .. 15
brightness = 140    # 5 .. 255

NUM_BASE = 24
NUM_PAL = 8
NUM_VAR = 6
TOTAL_PATTERNS = NUM_BASE * NUM_PAL * NUM_VAR  # 1152

PALETTES = [
    [(255, 0, 42), (0, 200, 255), (255, 183, 0), (123, 44, 191), (0, 245, 212), (255, 84, 0)],
    [(255, 0, 0), (255, 119, 0), (255, 255, 0), (0, 255, 0), (0, 136, 255), (170, 0, 255)],
    [(0, 229, 255), (0, 119, 255), (58, 12, 163), (247, 37, 133), (114, 9, 183), (76, 201, 240)],
    [(255, 42, 0), (255, 170, 0), (255, 230, 0), (255, 85, 0), (255, 0, 85), (255, 255, 255)],
    [(0, 255, 136), (0, 187, 255), (0, 85, 255), (136, 255, 0), (0, 255, 204), (34, 153, 255)],
    [(255, 0, 85), (255, 119, 170), (119, 0, 255), (0, 221, 255), (255, 170, 0), (255, 0, 170)],
    [(255, 255, 255), (0, 170, 255), (255, 0, 68), (0, 255, 102), (255, 204, 0), (204, 0, 255)],
    [(255, 51, 0), (0, 255, 170), (51, 102, 255), (255, 0, 204), (255, 204, 0), (0, 204, 255)],
]

def apply_br(col):
    return (
        (col[0] * brightness) // 255,
        (col[1] * brightness) // 255,
        (col[2] * brightness) // 255,
    )

def dim(col, pct):
    return apply_br((
        (col[0] * pct) // 255,
        (col[1] * pct) // 255,
        (col[2] * pct) // 255,
    ))

def get_pal(pal, idx):
    return PALETTES[pal % NUM_PAL][idx % 6]

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None

def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])

def eval_pixel(is_right, i, tick, pid):
    idx = pid - 1
    var = idx % NUM_VAR
    pal = (idx // NUM_VAR) % NUM_PAL
    base = (idx // (NUM_VAR * NUM_PAL)) % NUM_BASE

    rev = (var % 2 == 1)
    phase = (var // 2) * 2
    t = (-tick if rev else tick) + phase
    if is_right and (base % 2 == 1):
        t = -t

    pos = t % NUM_LEDS
    zz_period = (NUM_LEDS - 1) * 2  # 5 LEDs ke liye 0..4..0 (period 8)
    zz_pos = t % zz_period
    if zz_pos >= NUM_LEDS:
        zz_pos = zz_period - zz_pos

    c0 = get_pal(pal, 0)
    c1 = get_pal(pal, 1)
    c2 = get_pal(pal, 2)

    if base == 0:
        return apply_br(c0) if i == zz_pos else (0, 0, 0)
    elif base == 1:
        if i == zz_pos: return apply_br(c0)
        return dim(c1, 75) if abs(i - zz_pos) == 1 else (0, 0, 0)
    elif base == 2:
        return apply_br(c0 if ((t // 4) + i) % 2 == 0 else c1)
    elif base == 3:
        return apply_br(get_pal(pal, i)) if i == pos else (0, 0, 0)
    elif base == 4:
        return apply_br(c0) if (i == pos or i == (NUM_LEDS - 1 - pos)) else (0, 0, 0)
    elif base == 5:
        return apply_br(c1) if (i == zz_pos or i == ((zz_pos + 2) % NUM_LEDS)) else (0, 0, 0)
    elif base == 6:
        return apply_br(get_pal(pal, i + t)) if ((i + t) % 3) < 2 else (0, 0, 0)
    elif base == 7:
        d = abs(i - zz_pos)
        return dim(c0, 255 - d * 85) if d < 3 else (0, 0, 0)
    elif base == 8:
        return apply_br(c0 if i % 2 == 0 else c1) if ((t // 2) % 2 == 0) else (0, 0, 0)
    elif base == 9:
        return apply_br(get_pal(pal, i + (t // 2)))
    elif base == 10:
        mid = NUM_LEDS // 2
        st = t % 3
        return apply_br(c2) if abs(i - mid) == st else (0, 0, 0)
    elif base == 11:
        if i == zz_pos:
            return apply_br(c1 if (zz_pos == 0 or zz_pos == NUM_LEDS - 1) else c0)
        return (0, 0, 0)
    elif base == 12:
        return apply_br(c0) if i == ((t * 2) % NUM_LEDS) else (0, 0, 0)
    elif base == 13:
        b = int(127 + 127 * math.sin((t * 0.35) + i * 0.7))
        return dim(c0, b)
    elif base == 14:
        return apply_br(c0 if i < NUM_LEDS // 2 else c1)
    elif base == 15:
        cond = (i % 2 == 1) if is_right else (i % 2 == 0)
        return (apply_br(c0) if ((t // 3) % 2 == 0) else dim(c1, 60)) if cond else (0, 0, 0)
    elif base == 16:
        if i == zz_pos: return apply_br(c0)
        return dim(c2, 120) if i == ((zz_pos + 2) % NUM_LEDS) else (0, 0, 0)
    elif base == 17:
        h = ((i + 1) * 2654435761 ^ (t + pal * 97) * 2246822519) & 0xFFFFFFFF
        return apply_br(get_pal(pal, h >> 16)) if (h >> 24) < 110 else (0, 0, 0)
    elif base == 18:
        d = abs(i - zz_pos)
        if d == 0: return apply_br(c0)
        if d == 1: return dim(c0, 110)
        return dim(c0, 35) if d == 2 else (0, 0, 0)
    elif base == 19:
        return apply_br(get_pal(pal, i + t)) if (i % 3 == (t % 3)) else (0, 0, 0)
    elif base == 20:
        return apply_br(c0) if i == zz_pos else dim(c1, 80)
    elif base == 21:
        p = t % NUM_LEDS
        return apply_br(get_pal(pal, p)) if i == p else (0, 0, 0)
    elif base == 22:
        if i == 0 or i == NUM_LEDS - 1:
            return apply_br(c0 if ((t // 3) % 2 == 0) else c1)
        return dim(c2, 140) if i == zz_pos else (0, 0, 0)
    else:
        return apply_br(get_pal(pal, (i * 2 + t) // 2))

def render(tick):
    for i in range(NUM_LEDS):
        if enL and ((maskL >> i) & 1):
            if ui_mode == "custom":
                npL[i] = apply_br(colorsL[i])
            else:
                npL[i] = eval_pixel(False, i, tick, pattern_id)
        else:
            npL[i] = (0, 0, 0)

        if enR and ((maskR >> i) & 1):
            if ui_mode == "custom":
                npR[i] = apply_br(colorsR[i])
            else:
                npR[i] = eval_pixel(True, i, tick, pattern_id)
        else:
            npR[i] = (0, 0, 0)

    npL.write()
    npR.write()

# --- Connect Wi-Fi (AP + STA) ---
sta = network.WLAN(network.STA_IF)
ap = network.WLAN(network.AP_IF)

ap.active(True)
ap.config(essid=AP_SSID, password=AP_PASS)

sta.active(True)
try:
    sta.config(dhcp_hostname=HOSTNAME)
except Exception:
    pass
sta.connect(WIFI_SSID, WIFI_PASS)

print("Connecting to AirFiber-11...")
t0 = time.ticks_ms()
while not sta.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 12000:
    time.sleep_ms(300)

sta_ip = sta.ifconfig()[0] if sta.isconnected() else "Not Connected"
ap_ip = ap.ifconfig()[0]
print("Home Wi-Fi IP:", sta_ip)
print("AP Wi-Fi IP:", ap_ip)
print("Domain: http://led.local")

def led_cards_html(side, mask_val, col_list):
    out = []
    for i in range(NUM_LEDS):
        num = i + 1
        is_on = bool((mask_val >> i) & 1)
        hx = rgb_to_hex(col_list[i])
        out.append(
            f"<div class='led-item'>"
            f"<div class='led-top'>"
            f"<span class='led-tag'>{side}{num}</span>"
            f"<button class='mini-btn {'is-on' if is_on else 'is-off'}' onclick=\"api('cmd=led&s={side}&n={num}')\">{'ON' if is_on else 'OFF'}</button>"
            f"</div>"
            f"<input type='color' class='cpick' value='{hx}' onchange=\"setCol('{side}',{num},this.value)\">"
            f"</div>"
        )
    return "".join(out)

def build_html():
    left_ui = led_cards_html("L", maskL, colorsL)
    right_ui = led_cards_html("R", maskR, colorsR)
    custom_active = "active-pill" if ui_mode == "custom" else ""
    pat_active = "active-pill" if ui_mode == "pattern" else ""

    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio LED Control</title>
<style>
:root {{
  --bg: #090c14;
  --card: rgba(20, 27, 45, 0.82);
  --card-border: rgba(255, 255, 255, 0.09);
  --text: #f8fafc;
  --muted: #94a3b8;
  --accent: #38bdf8;
  --accent2: #a855f7;
  --ok: #22c55e;
  --bad: #ef4444;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 16px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: radial-gradient(circle at top left, #172554 0%, var(--bg) 48%),
              radial-gradient(circle at bottom right, #3b0764 0%, var(--bg) 55%);
  color: var(--text);
  min-height: 100vh;
}}
.wrap {{ max-width: 640px; margin: 0 auto; }}
.header {{
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 16px 18px; border-radius: 18px;
  background: var(--card); border: 1px solid var(--card-border);
  backdrop-filter: blur(12px); margin-bottom: 14px;
}}
.title {{ font-size: 19px; font-weight: 700; letter-spacing: 0.3px; }}
.sub {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
.mode-switch {{ display: flex; gap: 8px; background: rgba(2,6,23,0.65); padding: 4px; border-radius: 12px; border: 1px solid var(--card-border); }}
.pill {{
  border: none; padding: 8px 14px; border-radius: 9px; font-weight: 600; font-size: 12.5px;
  background: transparent; color: var(--muted); cursor: pointer; transition: 0.2s;
}}
.active-pill {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; box-shadow: 0 4px 14px rgba(56,189,248,0.3); }}
.card {{
  background: var(--card); border: 1px solid var(--card-border); border-radius: 18px;
  padding: 16px; margin-bottom: 14px; backdrop-filter: blur(12px);
  box-shadow: 0 12px 30px rgba(0,0,0,0.35);
}}
.sec-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }}
.sec-title {{ font-size: 15px; font-weight: 700; }}
.master-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.m-btn {{
  padding: 12px; border-radius: 12px; border: 1px solid transparent; font-weight: 700; font-size: 14px;
  cursor: pointer; transition: 0.18s;
}}
.on {{ background: rgba(34,197,94,0.16); color: #4ade80; border-color: rgba(34,197,94,0.4); }}
.off {{ background: rgba(239,68,68,0.16); color: #f87171; border-color: rgba(239,68,68,0.4); }}
.led-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }}
@media (max-width: 480px) {{ .led-grid {{ grid-template-columns: repeat(3, 1fr); }} }}
.led-item {{
  background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px; padding: 8px 6px; display: flex; flex-direction: column; align-items: center; gap: 7px;
}}
.led-top {{ display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 0 2px; }}
.led-tag {{ font-size: 12px; font-weight: 700; color: #e2e8f0; }}
.mini-btn {{
  border: none; border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 700; cursor: pointer;
}}
.is-on {{ background: #16a34a; color: #fff; }}
.is-off {{ background: #334155; color: #cbd5e1; }}
.cpick {{
  width: 42px; height: 34px; border: none; border-radius: 8px; background: none; cursor: pointer; padding: 0;
}}
.btn {{
  border: none; border-radius: 10px; padding: 9px 13px; font-weight: 600; font-size: 13px;
  cursor: pointer; background: rgba(56,189,248,0.16); color: #7dd3fc; border: 1px solid rgba(56,189,248,0.3);
}}
.btn-prim {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }}
.btn-red {{ background: rgba(239,68,68,0.18); color: #fca5a5; border: 1px solid rgba(239,68,68,0.35); }}
.pat-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: center; margin-bottom: 10px; }}
input[type=number] {{
  width: 92px; padding: 8px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.16);
  background: rgba(2,6,23,0.7); color: #fff; font-size: 14px; font-weight: 700; text-align: center;
}}
.slider-box {{ margin-top: 10px; text-align: left; font-size: 13px; color: var(--muted); }}
.slider-line {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
input[type=range] {{ width: 100%; accent-color: var(--accent); cursor: pointer; }}
.footer {{ font-size: 11.5px; color: var(--muted); text-align: center; line-height: 1.6; }}
.footer b {{ color: #e2e8f0; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <div class="title">Dual Strip Studio</div>
      <div class="sub">5 LEDs / Strip • Per-LED Color &amp; {TOTAL_PATTERNS} Patterns</div>
    </div>
    <div class="mode-switch">
      <button class="pill {custom_active}" onclick="setMode('custom')">Per-LED Color</button>
      <button class="pill {pat_active}" onclick="setMode('pattern')">1152 Patterns</button>
    </div>
  </div>

  <div class="card">
    <div class="sec-head">
      <span class="sec-title">Master Strip Control</span>
      <div>
        <button class="btn" onclick="api('cmd=all&on=1')">All 1-5 ON</button>
        <button class="btn-red" onclick="api('cmd=all&on=0')">All OFF</button>
      </div>
    </div>
    <div class="master-row">
      <button class="m-btn {'on' if enL else 'off'}" onclick="api('cmd=strip&s=L')">Left Strip: {'ON' if enL else 'OFF'}</button>
      <button class="m-btn {'on' if enR else 'off'}" onclick="api('cmd=strip&s=R')">Right Strip: {'ON' if enR else 'OFF'}</button>
    </div>
  </div>

  <div class="card">
    <div class="sec-head">
      <span class="sec-title">Left Strip (1 – 5) Custom Colors</span>
      <input type="color" class="cpick" value="#38bdf8" title="Apply same color to Left 1-5" onchange="fillSide('L',this.value)">
    </div>
    <div class="led-grid">{left_ui}</div>
  </div>

  <div class="card">
    <div class="sec-head">
      <span class="sec-title">Right Strip (1 – 5) Custom Colors</span>
      <input type="color" class="cpick" value="#a855f7" title="Apply same color to Right 1-5" onchange="fillSide('R',this.value)">
    </div>
    <div class="led-grid">{right_ui}</div>
  </div>

  <div class="card">
    <div class="sec-head">
      <span class="sec-title">Pattern Engine (#1 – #{TOTAL_PATTERNS})</span>
      <span style="font-size:12px;color:#7dd3fc;">Active: #{pattern_id}</span>
    </div>
    <div class="pat-row">
      <button class="btn" onclick="stepPat(-1)">◀ Prev</button>
      <input type="number" id="pIn" min="1" max="{TOTAL_PATTERNS}" value="{pattern_id}" onchange="setPat(this.value)">
      <button class="btn" onclick="stepPat(1)">Next ▶</button>
      <button class="btn-prim" onclick="randPat()">Random</button>
    </div>
    <div class="pat-row">
      <button class="btn" onclick="setPat(1)">Zig-Zag #1</button>
      <button class="btn" onclick="setPat(97)">Alternate #97</button>
      <button class="btn" onclick="setPat(145)">Single Jump #145</button>
      <button class="btn" onclick="setPat(865)">Scanner #865</button>
    </div>
    <div class="slider-box">
      <div class="slider-line"><span>Pattern Speed</span><span id="spdLbl">{speed_val}</span></div>
      <input type="range" min="1" max="15" value="{speed_val}" oninput="document.getElementById('spdLbl').innerText=this.value" onchange="fetch('/api?cmd=cfg&k=spd&v='+this.value)">
    </div>
    <div class="slider-box">
      <div class="slider-line"><span>Master Brightness</span><span id="brLbl">{brightness}</span></div>
      <input type="range" min="5" max="255" value="{brightness}" oninput="document.getElementById('brLbl').innerText=this.value" onchange="fetch('/api?cmd=cfg&k=br&v='+this.value)">
    </div>
  </div>

  <div class="footer">
    Domain: <b>http://led.local</b> • Home IP: <b>{sta_ip}</b> • AP IP: <b>{ap_ip}</b>
  </div>
</div>

<script>
const maxP = {TOTAL_PATTERNS};
function api(q) {{ fetch('/api?' + q).then(() => location.reload()); }}
function setMode(m) {{ api('cmd=mode&m=' + encodeURIComponent(m)); }}
function setCol(s, n, hex) {{
  const c = hex.replace('#', '');
  fetch('/api?cmd=col&s=' + s + '&n=' + n + '&hex=' + c);
}}
function fillSide(s, hex) {{
  const c = hex.replace('#', '');
  api('cmd=fill&s=' + s + '&hex=' + c);
}}
function setPat(p) {{
  p = Math.max(1, Math.min(maxP, parseInt(p) || 1));
  api('cmd=pat&p=' + p);
}}
function stepPat(d) {{
  setPat(parseInt(document.getElementById('pIn').value) + d);
}}
function randPat() {{
  setPat(Math.floor(Math.random() * maxP) + 1);
}}
</script>
</body>
</html>"""

def parse_params(path):
    params = {}
    if "?" in path:
        qs = path.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
    return params

# --- Non-blocking Web Server ---
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 80))
srv.listen(3)
srv.setblocking(False)

tick = 0
last_step = time.ticks_ms()

while True:
    try:
        conn, addr = srv.accept()
        conn.settimeout(0.5)
        req = conn.recv(512).decode("utf-8", "ignore")
        first_line = req.split("\r\n")[0] if req else ""
        path = first_line.split(" ")[1] if len(first_line.split(" ")) > 1 else "/"

        if path.startswith("/api"):
            p = parse_params(path)
            cmd = p.get("cmd", "")
            if cmd == "strip":
                if p.get("s") == "L": enL = not enL
                if p.get("s") == "R": enR = not enR
            elif cmd == "mode":
                m = p.get("m", "custom")
                if m in ("custom", "pattern"):
                    ui_mode = m
            elif cmd == "col":
                side = p.get("s", "")
                num = int(p.get("n", 0))
                rgb = hex_to_rgb(p.get("hex", ""))
                idx = num - 1
                if rgb and 0 <= idx < NUM_LEDS:
                    if side == "L": colorsL[idx] = rgb
                    elif side == "R": colorsR[idx] = rgb
                    ui_mode = "custom"
            elif cmd == "fill":
                side = p.get("s", "")
                rgb = hex_to_rgb(p.get("hex", ""))
                if rgb:
                    if side == "L":
                        for k in range(NUM_LEDS): colorsL[k] = rgb
                    elif side == "R":
                        for k in range(NUM_LEDS): colorsR[k] = rgb
                    ui_mode = "custom"
            elif cmd == "pat":
                val = int(p.get("p", 1))
                if 1 <= val <= TOTAL_PATTERNS:
                    pattern_id = val
                    ui_mode = "pattern"
            elif cmd == "cfg":
                val = int(p.get("v", 5))
                if p.get("k") == "spd": speed_val = max(1, min(15, val))
                if p.get("k") == "br": brightness = max(5, min(255, val))
            elif cmd == "led":
                idx = int(p.get("n", 0)) - 1
                if 0 <= idx < NUM_LEDS:
                    if p.get("s") == "L": maskL ^= (1 << idx)
                    if p.get("s") == "R": maskR ^= (1 << idx)
            elif cmd == "all":
                on = (p.get("on") == "1")
                maskL = ALL_MASK if on else 0x00
                maskR = ALL_MASK if on else 0x00

            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nOK")
        else:
            html = build_html().encode("utf-8")
            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
            conn.sendall(html)
        conn.close()
    except OSError:
        pass

    interval = 340 - (speed_val * 20)
    if time.ticks_diff(time.ticks_ms(), last_step) >= interval:
        last_step = time.ticks_ms()
        tick += 1
        render(tick)
    time.sleep_ms(5)
