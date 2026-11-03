"""Açılış ekranındaki "Örnek videoyla dene" için telifsiz demo yayın videosu üretir.

Her şey sıfırdan çizilir/sentezlenir: oyun sahnesi, çizgi film avatarlı kamera, sohbet, ses.
Çalıştırma: python tools/demo_uret.py  →  assets/demo/ornek_yayin.mp4 + ornek.json
"""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "demo"
FONT = ROOT / "assets" / "fonts" / "Poppins-Bold.ttf"
W, H, FPS, DUR = 1280, 720, 30, 60.0
SR = 48000
rng = np.random.default_rng(3)

CAM = (24, 24, 330, 250)  # x0, y0, x1, y1 (kamera penceresi)
EVENTS = [(17.5, "BOSS YENİLDİ!", (255, 214, 64)), (41.5, "ZAFER!", (200, 241, 53))]

# Konuşma: (başlangıç, bitiş, metin) — ses bu aralıklarda "konuşur", altyazı da bunu gösterir
LINES = [
    (1.0, 3.2, "Selam millet hoş geldiniz"),
    (4.0, 6.4, "bugün bu bölümü bitireceğiz"),
    (8.0, 10.6, "dikkat boss geliyor"),
    (12.0, 14.8, "hadi hadi hadi az kaldı"),
    (16.6, 20.6, "OHA YENDİK! İnanılmaz!"),
    (23.0, 25.6, "sohbete selam söyleyin"),
    (28.0, 30.8, "şimdi son bölüme geçiyoruz"),
    (33.0, 35.6, "bu atlayış çok zor"),
    (37.0, 39.4, "bir daha deneyelim"),
    (40.8, 45.0, "EVET! Rekor kırdık arkadaşlar!"),
    (48.0, 50.6, "takip etmeyi unutmayın"),
    (53.0, 55.8, "bir sonraki yayında görüşürüz"),
]
LOUD = {4, 9}  # bağırılan satırlar


def font(size):
    return ImageFont.truetype(str(FONT), size)


# --------------------------------------------------------------------------- ses
def synth_audio():
    n = int(SR * DUR)
    t = np.arange(n) / SR
    voice = np.zeros(n)
    mouth = np.zeros(int(DUR * FPS) + 1)  # avatarın ağız açıklığı (0..1)
    for k, (a, b, text) in enumerate(LINES):
        words = text.split()
        loud = k in LOUD
        span = (b - a) / len(words)
        for i, w in enumerate(words):
            syl = max(1, sum(ch in "aeıioöuüAEIİOÖUÜ" for ch in w))
            for j in range(syl):
                s0 = a + i * span + j * span / syl
                d = span / syl * 0.85
                m = int(SR * d)
                tt = np.arange(m) / SR
                f0 = (180 if not loud else 260) * (1 + 0.08 * np.sin(2 * np.pi * 3 * tt)) * (1 + 0.1 * rng.uniform(-1, 1))
                ph = 2 * np.pi * np.cumsum(f0) / SR
                src = sum(np.sin(ph * h) / h for h in range(1, 12))  # gırtlak sesi benzeri
                # basit formantlar: rastgele ünlü
                fm = rng.choice([(700, 1200), (400, 2000), (300, 2300), (500, 900), (350, 800)])
                env = np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 0.6
                y = src * env
                spec = np.fft.rfft(y)
                fr = np.fft.rfftfreq(len(y), 1 / SR)
                shape = np.exp(-((fr - fm[0]) / 180) ** 2) + 0.7 * np.exp(-((fr - fm[1]) / 260) ** 2) + 0.15
                y = np.fft.irfft(spec * shape, len(y))
                i0 = int(s0 * SR)
                voice[i0:i0 + m] += y[: n - i0] * (1.8 if loud else 1.0)
                f_a, f_b = int(s0 * FPS), int((s0 + d) * FPS)
                for f in range(f_a, min(len(mouth), f_b + 1)):
                    mouth[f] = max(mouth[f], (1.0 if loud else 0.6) * math.sin(math.pi * (f - f_a + 0.5) / max(1, f_b - f_a + 1)))
    voice /= np.max(np.abs(voice)) + 1e-9
    voice *= 0.5
    # oyun müziği: yumuşak akorlar
    music = np.zeros(n)
    chords = [(220, 277.2, 329.6), (196, 246.9, 293.7), (174.6, 220, 261.6), (196, 246.9, 293.7)]
    for i in range(int(DUR / 2) + 1):
        c = chords[i % 4]
        a = int(i * 2 * SR); m = min(n - a, 2 * SR)
        if m <= 0:
            break
        tt = np.arange(m) / SR
        music[a:a + m] += sum(np.sin(2 * np.pi * f * tt) for f in c) * np.exp(-tt * 0.9) * 0.05
    # olay sesleri: patlama + kalabalık
    fx = np.zeros(n)
    for at, _, _ in EVENTS:
        a = int(at * SR); m = int(1.6 * SR); tt = np.arange(m) / SR
        boom = np.sin(2 * np.pi * np.cumsum(40 + 90 * np.exp(-tt * 8)) / SR) * np.exp(-tt * 2.5)
        noise = rng.standard_normal(m) * np.exp(-tt * 3) * 0.35
        fx[a:a + m] += (boom + noise) * 0.6
    mix = voice + music + fx
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= 0.9
    st = np.stack([mix, mix], 1)
    p = OUT / "_ses.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())
    return p, mouth


# --------------------------------------------------------------------------- görüntü
def sky(w, h):
    g = np.linspace(0, 1, h)[:, None]
    top, bot = np.array([46, 32, 92]), np.array([255, 140, 96])
    arr = top[None, None, :] * (1 - g[:, :, None]) + bot[None, None, :] * g[:, :, None]  # (h, 1, 3)
    return Image.fromarray(np.ascontiguousarray(np.broadcast_to(arr, (h, w, 3))).astype(np.uint8))


def avatar(open_mouth, blink, t):
    """Kendi çizdiğimiz yayıncı avatarı (gerçek kişi değil)."""
    w, h = CAM[2] - CAM[0], CAM[3] - CAM[1]
    im = Image.new("RGB", (w, h), (34, 40, 58))
    d = ImageDraw.Draw(im)
    # oda arka planı: raf + led ışık
    d.rectangle([0, h - 70, w, h], fill=(28, 30, 44))
    d.rectangle([20, 30, 120, 36], fill=(80, 60, 50))
    for i, c in enumerate([(200, 241, 53), (90, 169, 255), (255, 107, 107)]):
        d.rectangle([28 + i * 30, 10, 48 + i * 30, 30], fill=c)
    led = int(127 + 127 * math.sin(t * 2))
    d.rectangle([w - 10, 0, w, h], fill=(led, 60, 255 - led))
    bob = math.sin(t * 2.2) * 3
    cx, cy = w // 2 + 10, int(h * 0.52 + bob)
    d.ellipse([cx - 95, cy + 60, cx + 95, cy + 200], fill=(90, 70, 200))  # gövde (hoodie)
    d.ellipse([cx - 62, cy - 70, cx + 62, cy + 62], fill=(244, 196, 160))  # kafa
    d.chord([cx - 66, cy - 80, cx + 66, cy + 20], 180, 360, fill=(60, 40, 30))  # saç
    # kulaklık
    d.arc([cx - 78, cy - 92, cx + 78, cy + 40], 190, 350, fill=(30, 30, 30), width=10)
    d.rounded_rectangle([cx - 86, cy - 24, cx - 62, cy + 26], 8, fill=(200, 241, 53))
    d.rounded_rectangle([cx + 62, cy - 24, cx + 86, cy + 26], 8, fill=(200, 241, 53))
    # gözler
    for ex in (cx - 24, cx + 24):
        if blink:
            d.line([ex - 10, cy - 6, ex + 10, cy - 6], fill=(30, 30, 30), width=4)
        else:
            d.ellipse([ex - 10, cy - 16, ex + 10, cy + 4], fill=(255, 255, 255))
            d.ellipse([ex - 5, cy - 11, ex + 5, cy - 1], fill=(30, 30, 40))
    # ağız
    mo = 4 + open_mouth * 22
    d.ellipse([cx - 16, cy + 24 - mo / 4, cx + 16, cy + 24 + mo], fill=(150, 40, 60))
    d.ellipse([cx - 40, cy + 6, cx - 26, cy + 16], fill=(250, 150, 140))
    d.ellipse([cx + 26, cy + 6, cx + 40, cy + 16], fill=(250, 150, 140))
    # mikrofon
    d.rectangle([cx - 120, cy + 40, cx - 108, cy + 160], fill=(60, 60, 70))
    d.rounded_rectangle([cx - 132, cy + 10, cx - 96, cy + 70], 14, fill=(40, 40, 48))
    return im


CHAT = ["ahmet: selam!", "zeynep: hoş geldin", "mert: boss zor", "ece: GG", "kaan: OHAAA", "deniz: efsane",
        "ayşe: yangın var", "can: rekor mu?", "burak: KG", "elif: takip ettim", "efe: tekrar izle", "selin: wow"]


def frames(mouth):
    base_sky = sky(W, H)
    f_big, f_hud, f_chat, f_title = font(84), font(26), font(18), font(16)
    stars = rng.uniform(0, 1, (60, 3))
    for fi in range(int(DUR * FPS)):
        t = fi / FPS
        im = base_sky.copy()
        d = ImageDraw.Draw(im)
        for sx, sy, sz in stars:
            if sy < 0.45:
                d.ellipse([sx * W, sy * H, sx * W + 2 + sz * 2, sy * H + 2 + sz * 2], fill=(255, 240, 220))
        d.ellipse([W * 0.72, H * 0.12, W * 0.72 + 110, H * 0.12 + 110], fill=(255, 220, 150))
        # paralaks dağlar
        for layer, (col, amp, spd, base) in enumerate([((90, 60, 130), 70, 20, 0.62), ((60, 40, 100), 50, 45, 0.72),
                                                        ((40, 30, 70), 35, 90, 0.82)]):
            pts = [(0, H)]
            for x in range(0, W + 41, 40):
                xx = x + t * spd
                y = H * base - amp * (0.6 * math.sin(xx / 140 + layer) + 0.4 * math.sin(xx / 57 + layer * 2))
                pts.append((x, y))
            pts.append((W, H))
            d.polygon(pts, fill=col)
        # zemin
        d.rectangle([0, H * 0.86, W, H], fill=(30, 22, 40))
        off = (t * 140) % 80
        for x in range(-80, W + 80, 80):
            d.rectangle([x - off, H * 0.86, x - off + 40, H * 0.86 + 6], fill=(200, 241, 53))
        # karakter
        jump = max(0.0, math.sin((t % 2.4) / 2.4 * math.pi * 2)) * 90 if (t % 2.4) < 1.2 else 0
        px, py = W * 0.42, H * 0.86 - 70 - jump
        d.rounded_rectangle([px, py, px + 50, py + 70], 10, fill=(90, 169, 255))
        d.rectangle([px + 30, py + 14, px + 44, py + 26], fill=(255, 255, 255))
        # paralar
        for k in range(6):
            cxp = (k * 260 + 400 - t * 140) % (W + 200) - 100
            d.ellipse([cxp, H * 0.62, cxp + 26, H * 0.62 + 26], fill=(255, 214, 64), outline=(200, 140, 30), width=3)
        # boss (8–17.5 sn arası)
        if 8 <= t < 17.5:
            bx = W * 0.72 + math.sin(t * 3) * 20
            d.ellipse([bx, H * 0.42, bx + 220, H * 0.42 + 220], fill=(160, 40, 80))
            d.ellipse([bx + 50, H * 0.5, bx + 90, H * 0.5 + 40], fill=(255, 255, 255))
            d.ellipse([bx + 130, H * 0.5, bx + 170, H * 0.5 + 40], fill=(255, 255, 255))
            hp = max(0, 1 - (t - 8) / 9.5)
            d.rectangle([W * 0.35, 30, W * 0.35 + 400, 50], fill=(40, 20, 30))
            d.rectangle([W * 0.35, 30, W * 0.35 + 400 * hp, 50], fill=(255, 80, 100))
            d.text((W * 0.35, 54), "BOSS", font=f_title, fill=(255, 255, 255))
        # HUD
        d.text((W - 230, H - 52), f"SKOR {int(t * 137):06d}", font=f_hud, fill=(255, 255, 255))
        d.text((380, H - 52), "CAN 100", font=f_hud, fill=(255, 107, 107))
        # olay yazıları + flaş
        for at, txt, col in EVENTS:
            if at <= t < at + 2.2:
                k = t - at
                if k < 0.15:
                    d.rectangle([0, 0, W, H], fill=(255, 255, 255))
                sc = min(1.0, 0.5 + k * 3)
                fnt = font(int(84 * sc))
                tw = d.textlength(txt, font=fnt)
                d.text(((W - tw) / 2 + 60, H * 0.32), txt, font=fnt, fill=col, stroke_width=6, stroke_fill=(20, 10, 30))
        # sohbet kutusu
        chat = Image.new("RGBA", (260, 300), (14, 15, 17, 190))
        cd = ImageDraw.Draw(chat)
        cd.text((12, 8), "SOHBET", font=f_title, fill=(200, 241, 53))
        shown = int(t * 0.9) + 3
        for j in range(8):
            idx = shown - 8 + j
            if idx >= 0:
                cd.text((12, 36 + j * 32), CHAT[idx % len(CHAT)], font=f_chat, fill=(230, 230, 235))
        im.paste(chat, (W - 280, 80), chat)
        # kamera
        cam = avatar(float(mouth[min(fi, len(mouth) - 1)]), (fi % 110) < 4, t)
        im.paste(cam, CAM[:2])
        d.rectangle([CAM[0] - 3, CAM[1] - 3, CAM[2] + 2, CAM[3] + 2], outline=(200, 241, 53), width=3)
        yield im.tobytes()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wav, mouth = synth_audio()
    out = OUT / "ornek_yayin.mp4"
    ff = [sys.argv[1] if len(sys.argv) > 1 else "ffmpeg", "-y", "-v", "error",
          "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
          "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(ff, stdin=subprocess.PIPE)
    for buf in frames(mouth):
        p.stdin.write(buf)
    p.stdin.close(); p.wait()
    wav.unlink()
    # Hazır proje: kamera kutusu, altyazı ve kanca hazır
    words = []
    for a, b, text in LINES:
        ws = text.split(); span = (b - a) / len(ws)
        words += [{"start": round(a + i * span, 3), "end": round(a + (i + 1) * span, 3), "text": w} for i, w in enumerate(ws)]
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= 3 or w["start"] - cur[-1]["end"] > 0.6 or cur[-1]["text"][-1] in ".!?"):
            chunks.append(cur); cur = []
        cur.append(w)
    chunks.append(cur)
    cam = {"x": CAM[0] / W, "y": CAM[1] / H, "w": (CAM[2] - CAM[0]) / W, "h": (CAM[3] - CAM[1]) / H}
    data = {"version": 1, "app": "streamchisel", "demo": True,
            "S": {"preset": "stack", "camera": cam, "autoCam": True, "pack": "enerjik", "style": "bold", "anim": "bounce",
                  "hook": {"on": True, "text": "Boss'u tek seferde yendi!", "style": "box", "dur": 3, "y": 0.16},
                  "pb": {"on": True, "pos": "bottom", "color": "#C8F135"}},
            "P": {"range": {"start": 6.0, "end": 26.0}, "splits": [], "cuts": [], "zooms": [], "sfx": [
                {"id": "d1", "path": "sfx:patlama", "label": "Patlama", "url": "/sfx/patlama.wav", "time": 17.5, "volume": 0.8}]},
            "T": {"start": 0, "end": DUR, "language": "tr", "chunks": chunks}}
    (OUT / "ornek.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
