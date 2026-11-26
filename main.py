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
NUM_LEDS = 6

npL = neopixel.NeoPixel(Pin(PIN_L, Pin.OUT), NUM_LEDS)
npR = neopixel.NeoPixel(Pin(PIN_R, Pin.OUT), NUM_LEDS)

# --- Control State ---
enL = True
enR = True
manual_mode = False
maskL = 0x3F  # 6 LEDs bitmask (111111)
maskR = 0x3F

pattern_id = 1
speed_val = 7       # 1 (slow) .. 15 (fast)
brightness = 130    # 5 .. 255

NUM_BASE = 24
NUM_PAL = 8
NUM_VAR = 6
TOTAL_PATTERNS = NUM_BASE * NUM_PAL * NUM_VAR  # 1152 Patterns

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

def scale(col, factor):
    f = (factor * brightness) // 65025
    return ((col[0] * f) // 255 if factor != 255 else (col[0] * brightness) // 255,
            (col[1] * f) // 255 if factor != 255 else (col[1] * brightness) // 255,
            (col[2] * f) // 255 if factor != 255 else (col[2] * brightness) // 255)

def apply_br(col):
    return ((col[0] * brightness) // 255,
            (col[1] * brightness) // 255,
            (col[2] * brightness) // 255)

def dim(col, pct):
    return apply_br(((col[0] * pct) // 255, (col[1] * pct) // 255, (col[2] * pct) // 255))

def get_pal(pal, idx):
    return PALETTES[pal % NUM_PAL][idx % 6]

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
    zz_period = (NUM_LEDS - 1) * 2  # 10
    zz_pos = t % zz_period
    if zz_pos >= NUM_LEDS:
        zz_pos = zz_period - zz_pos

    c0 = get_pal(pal, 0)
    c1 = get_pal(pal, 1)
    c2 = get_pal(pal, 2)

    if base == 0:    # Zig-Zag single lit bounce
        return apply_br(c0) if i == zz_pos else (0, 0, 0)
    elif base == 1:  # Zig-Zag with soft tail
        if i == zz_pos: return apply_br(c0)
        return dim(c1, 75) if abs(i - zz_pos) == 1 else (0, 0, 0)
    elif base == 2:  # Alternate odd/even jump
        return apply_br(c0 if ((t // 4) + i) % 2 == 0 else c1)
    elif base == 3:  # Single LED step jump
        return apply_br(get_pal(pal, i)) if i == pos else (0, 0, 0)
    elif base == 4:  # Dual opposite ends meet & split
        return apply_br(c0) if (i == pos or i == (NUM_LEDS - 1 - pos)) else (0, 0, 0)
    elif base == 5:  # Zig-zag dual bar
        return apply_br(c1) if (i == zz_pos or i == ((zz_pos + 2) % NUM_LEDS)) else (0, 0, 0)
    elif base == 6:  # Alternating 2-on 1-off blocks
        return apply_br(get_pal(pal, i + t)) if ((i + t) % 3) < 2 else (0, 0, 0)
    elif base == 7:  # Wave sweep
        d = abs(i - zz_pos)
        return dim(c0, 255 - d * 85) if d < 3 else (0, 0, 0)
    elif base == 8:  # Alternate strobe flash
        return apply_br(c0 if i % 2 == 0 else c1) if ((t // 2) % 2 == 0) else (0, 0, 0)
    elif base == 9:  # Multi-color flow
        return apply_br(get_pal(pal, i + (t // 2)))
    elif base == 10: # Center outward burst
        mid = NUM_LEDS // 2
        st = t % 4
        return apply_br(c2) if (abs(i - mid) == st or abs(i - (mid - 1)) == st) else (0, 0, 0)
    elif base == 11: # Zig-zag color flip at edges
        if i == zz_pos:
            return apply_br(c1 if (zz_pos == 0 or zz_pos == NUM_LEDS - 1) else c0)
        return (0, 0, 0)
    elif base == 12: # Skip-2 jump
        return apply_br(c0) if i == ((t * 2) % NUM_LEDS) else (0, 0, 0)
    elif base == 13: # Smooth breathing wave
        b = int(127 + 127 * math.sin((t * 0.35) + i * 0.7))
        return dim(c0, b)
    elif base == 14: # Two-tone split
        return apply_br(c0 if i < NUM_LEDS // 2 else c1)
    elif base == 15: # Left-Right alternate emphasis
        cond = (i % 2 == 1) if is_right else (i % 2 == 0)
        return (apply_br(c0) if ((t // 3) % 2 == 0) else dim(c1, 60)) if cond else (0, 0, 0)
    elif base == 16: # Zig-zag dual trail
        if i == zz_pos: return apply_br(c0)
        return dim(c2, 120) if i == ((zz_pos + 3) % NUM_LEDS) else (0, 0, 0)
    elif base == 17: # Sparkle
        h = ((i + 1) * 2654435761 ^ (t + pal * 97) * 2246822519) & 0xFFFFFFFF
        return apply_br(get_pal(pal, h >> 16)) if (h >> 24) < 110 else (0, 0, 0)
    elif base == 18: # Knight Rider scanner
        d = abs(i - zz_pos)
        if d == 0: return apply_br(c0)
        if d == 1: return dim(c0, 110)
        return dim(c0, 35) if d == 2 else (0, 0, 0)
    elif base == 19: # 3-step chase
        return apply_br(get_pal(pal, i + t)) if (i % 3 == (t % 3)) else (0, 0, 0)
    elif base == 20: # Inverted zig-zag gap
        return apply_br(c0) if i == zz_pos else dim(c1, 80)
    elif base == 21: # Pulse pair
        p = t % 3
        return apply_br(get_pal(pal, p)) if (i == p * 2 or i == p * 2 + 1) else (0, 0, 0)
    elif base == 22: # Edge ping-pong
        if i == 0 or i == NUM_LEDS - 1:
            return apply_br(c0 if ((t // 3) % 2 == 0) else c1)
        return dim(c2, 140) if i == zz_pos else (0, 0, 0)
    else:            # Matrix step
        return apply_br(get_pal(pal, (i * 2 + t) // 2))

def render(tick):
    for i in range(NUM_LEDS):
        if enL and ((maskL >> i) & 1):
            npL[i] = apply_br(get_pal(pattern_id // 10, i)) if manual_mode else eval_pixel(False, i, tick, pattern_id)
        else:
            npL[i] = (0, 0, 0)

        if enR and ((maskR >> i) & 1):
            npR[i] = apply_br(get_pal((pattern_id // 10) + 2, i)) if manual_mode else eval_pixel(True, i, tick, pattern_id)
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

def build_html():
    btns_l = "".join([
        f"<button class='{'on' if (maskL >> i) & 1 else 'off'}' onclick=\"api('cmd=led&s=L&i={i}')\">L{i}</button>"
        for i in range(NUM_LEDS)
    ])
    btns_r = "".join([
        f"<button class='{'on' if (maskR >> i) & 1 else 'off'}' onclick=\"api('cmd=led&s=R&i={i}')\">R{i}</button>"
        for i in range(NUM_LEDS)
    ])
    return f"""<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>1152 Pattern LED Control</title>
<style>
body{{font-family:Arial,sans-serif;background:#101216;color:#fff;text-align:center;padding:12px;margin:0}}
.card{{background:#1b1f27;border-radius:12px;padding:12px;margin:10px auto;max-width:480px}}
button{{border:none;border-radius:8px;padding:9px 12px;margin:4px;font-weight:bold;cursor:pointer;font-size:13px}}
.pri{{background:#00c6ff;color:#000}}.on{{background:#16a34a;color:#fff}}.off{{background:#dc2626;color:#fff}}
input[type=number]{{width:80px;padding:7px;border-radius:7px;border:1px solid #444;background:#111;color:#fff;text-align:center}}
input[type=range]{{width:68%;vertical-align:middle}}
.meta{{font-size:12px;color:#9ca3af}}
</style></head><body>
<div class="card">
  <h2>Dual Strip Panel (1152 Designs)</h2>
  <button class="{'on' if enL else 'off'}" onclick="api('cmd=strip&s=L')">Left Strip: {'ON' if enL else 'OFF'}</button>
  <button class="{'on' if enR else 'off'}" onclick="api('cmd=strip&s=R')">Right Strip: {'ON' if enR else 'OFF'}</button><br>
  <button class="pri" onclick="api('cmd=mode&m=0')">1152 Patterns Mode</button>
  <button class="pri" onclick="api('cmd=mode&m=1')">Manual LEDs Only</button>
</div>
<div class="card">
  <h3>Pattern #1 - #{TOTAL_PATTERNS}</h3>
  <button class="pri" onclick="stepPat(-1)">Prev</button>
  <input type="number" id="pIn" min="1" max="{TOTAL_PATTERNS}" value="{pattern_id}" onchange="setPat(this.value)">
  <button class="pri" onclick="stepPat(1)">Next</button>
  <button class="pri" onclick="randPat()">Random</button><br>
  <button class="pri" onclick="setPat(1)">Zig-Zag #1</button>
  <button class="pri" onclick="setPat(97)">Alternate #97</button>
  <button class="pri" onclick="setPat(145)">Single Jump #145</button>
  <button class="pri" onclick="setPat(865)">Scanner #865</button><br><br>
  Speed: <input type="range" min="1" max="15" value="{speed_val}" onchange="fetch('/api?cmd=cfg&k=spd&v='+this.value)"><br>
  Brightness: <input type="range" min="5" max="255" value="{brightness}" onchange="fetch('/api?cmd=cfg&k=br&v='+this.value)">
</div>
<div class="card">
  <h3>Individual LED ON/OFF</h3>
  <div>Left: {btns_l}</div>
  <div>Right: {btns_r}</div>
  <button class="on" onclick="api('cmd=all&on=1')">All ON</button>
  <button class="off" onclick="api('cmd=all&on=0')">All OFF</button>
</div>
<div class="card meta">Domain: <b>http://led.local</b> | Home IP: <b>{sta_ip}</b> | AP IP: <b>{ap_ip}</b></div>
<script>
const maxP={TOTAL_PATTERNS};
function api(q){{fetch('/api?'+q).then(()=>location.reload());}}
function setPat(p){{p=Math.max(1,Math.min(maxP,parseInt(p)||1));api('cmd=pat&p='+p);}}
function stepPat(d){{setPat(parseInt(document.getElementById('pIn').value)+d);}}
function randPat(){{setPat(Math.floor(Math.random()*maxP)+1);}}
</script></body></html>"""

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
                manual_mode = (p.get("m") == "1")
            elif cmd == "pat":
                val = int(p.get("p", 1))
                if 1 <= val <= TOTAL_PATTERNS: pattern_id = val
            elif cmd == "cfg":
                val = int(p.get("v", 5))
                if p.get("k") == "spd": speed_val = max(1, min(15, val))
                if p.get("k") == "br": brightness = max(5, min(255, val))
            elif cmd == "led":
                idx = int(p.get("i", -1))
                if 0 <= idx < NUM_LEDS:
                    if p.get("s") == "L": maskL ^= (1 << idx)
                    if p.get("s") == "R": maskR ^= (1 << idx)
            elif cmd == "all":
                on = (p.get("on") == "1")
                maskL = 0x3F if on else 0x00
                maskR = 0x3F if on else 0x00

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
