"""Streamchisel'in hazır ses efektlerini sıfırdan sentezler (telif yok, tamamen bize ait).

Çalıştırma: python tools/sfx_uret.py  →  assets/sfx/*.wav
"""
import json
import wave
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parent.parent / "assets" / "sfx"
rng = np.random.default_rng(7)


def t(d):
    return np.arange(int(SR * d)) / SR


def env(n, a=0.005, r=None, curve=4.0):
    """Atak + üstel sönüm zarfı."""
    x = np.ones(n)
    na = max(1, int(SR * a))
    x[:na] = np.linspace(0, 1, na)
    if r is None:
        x[na:] = np.exp(-curve * np.linspace(0, 1, n - na))
    return x


def lowpass(x, cutoff):
    """Tek kutuplu alçak geçiren; cutoff dizi olabilir (zamanla değişen)."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev = (1 - a[i]) * x[i] + a[i] * prev
        y[i] = prev
    return y


def bandnoise(d, f0, f1):
    n = rng.standard_normal(int(SR * d))
    f = np.geomspace(f0, f1, len(n))
    return lowpass(n, f) - lowpass(n, f * 0.35)


CATS = {"whoosh": "Geçiş", "yukselis": "Geçiş", "vurus": "Vuruş", "davul": "Gerilim", "ding": "Arayüz",
        "pop": "Arayüz", "tik": "Arayüz", "korna": "Komik", "basari": "Oyun", "hata": "Oyun"}


def tone(f, d=None):
    """Frekansı (sabit ya da dizi) sinüse çevirir."""
    f = np.full(int(SR * d), float(f)) if d is not None else f
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def saw(f):
    return 2 * ((np.cumsum(f) / SR) % 1) - 1


def square(f):
    return np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR))


def gate(tt, a=0.01, r=0.05):
    d = tt[-1] if len(tt) else 0
    return np.clip(np.minimum(tt / max(a, 1e-4), (d - tt) / max(r, 1e-4)), 0, 1)


def place(buf, x, at):
    i = int(at * SR)
    if i >= len(buf):
        return buf
    m = min(len(x), len(buf) - i)
    buf[i:i + m] += x[:m]
    return buf


def bell(f, d, decay=3.0):
    tt = t(d)
    return sum(a * np.sin(2 * np.pi * f * m * tt) * np.exp(-tt * decay * k)
               for m, a, k in [(1, 1, 1), (2.0, .45, 1.7), (3.0, .2, 2.6), (4.2, .12, 3.5)])


def save(name, x, label, cat=None, peak=0.89):
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    rms = float(np.sqrt(np.mean(x ** 2)))
    x *= min(1.0, 10 ** (-14 / 20) / max(rms, 1e-9))  # uzun/dolgun sesler diğerlerini bastırmasın
    fade = min(len(x), int(SR * 0.01))
    x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    return {"id": name, "label": label, "category": cat or CATS.get(name, "Diğer"),
            "duration": round(len(x) / SR, 2)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lib = []

    d = 0.7; n = int(SR * d)
    sweep = np.concatenate([np.geomspace(300, 3500, n // 2), np.geomspace(3500, 500, n - n // 2)])
    e = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    lib.append(save("whoosh", (lowpass(rng.standard_normal(n), sweep) - lowpass(rng.standard_normal(n), 120)) * e, "Whoosh geçiş"))

    tt = t(0.55); f = 55 + 110 * np.exp(-tt * 18)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.002, curve=6)
    click = bandnoise(0.03, 3000, 1500) * env(int(SR * 0.03), 0.001, curve=8)
    boom[:len(click)] += click * 0.6
    lib.append(save("vurus", boom, "Vuruş"))

    tt = t(1.2)
    bell = sum(a * np.sin(2 * np.pi * f * tt) * np.exp(-tt * k) for f, a, k in [(1318.5, 1, 3), (2637, .5, 5), (3951, .25, 8), (1975, .2, 4)])
    lib.append(save("ding", bell * env(len(tt), 0.002, curve=0.0001), "Ding"))

    tt = t(0.14); f = 900 * np.exp(-tt * 18) + 200
    lib.append(save("pop", np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.001, curve=7), "Pop"))

    d = 1.6; tt = t(d); f = np.geomspace(180, 1600, len(tt))
    riser = 0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * bandnoise(d, 400, 6000)
    lib.append(save("yukselis", riser * np.linspace(0, 1, len(tt)) ** 2, "Yükseliş"))

    tt = t(0.95); vib = 1 + 0.006 * np.sin(2 * np.pi * 6 * tt)
    horn = sum(2 * ((np.cumsum(f * vib) / SR) % 1) - 1 for f in (466.2, 554.4, 698.5))
    horn = lowpass(horn, 2800) * np.clip(np.minimum(tt / 0.03, (0.95 - tt) / 0.12), 0, 1)
    lib.append(save("korna", horn, "Korna"))

    parts = []
    for f in (523.3, 659.3, 784.0, 1046.5):
        tt = t(0.12 if f != 1046.5 else 0.45)
        parts.append(np.sin(2 * np.pi * f * tt) * env(len(tt), 0.003, curve=3) + 0.3 * np.sin(4 * np.pi * f * tt) * env(len(tt), 0.003, curve=5))
    lib.append(save("basari", np.concatenate(parts), "Başarı"))

    tt = t(0.5)
    buzz = np.sign(np.sin(2 * np.pi * 140 * tt)) + 0.6 * np.sign(np.sin(2 * np.pi * 147 * tt))
    lib.append(save("hata", lowpass(buzz, 1800) * np.clip(np.minimum(tt / 0.01, (0.5 - tt) / 0.05), 0, 1), "Hata"))

    tt = t(0.06)
    lib.append(save("tik", bandnoise(0.06, 5000, 2500) * env(len(tt), 0.0005, curve=10), "Tık"))

    d = 1.4; n = int(SR * d)
    hits = np.zeros(n)
    k = 0.0
    while k < d - 0.1:
        i = int(k * SR); s = bandnoise(0.05, 2500, 900) * env(int(SR * 0.05), 0.001, curve=6)
        hits[i:i + len(s)] += s[: n - i]
        k += 0.11 - 0.06 * (k / d)
    lib.append(save("davul", hits * np.linspace(0.4, 1, n), "Davul gerilimi"))

    lib += extra()

    (OUT / "library.json").write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "LICENSE.txt").write_text("Bu ses efektleri Streamchisel için tools/sfx_uret.py ile sıfırdan sentezlenmiştir.\n"
                                     "Kullanıcılar ürettikleri videolarda serbestçe kullanabilir.\n", encoding="utf-8")
    print(len(lib), "efekt üretildi")


def extra():
    """v0.7 ile gelen 25 efekt."""
    out = []

    # Kalp atışı: iki kez "güm-güm"
    buf = np.zeros(int(SR * 1.8))
    for at in (0.0, 0.2, 0.9, 1.1):
        tt = t(0.25); f = 45 + 50 * np.exp(-tt * 25)
        place(buf, tone(f) * env(len(tt), 0.004, curve=9) * (1 if at in (0.0, 0.9) else 0.7), at)
    out.append(save("kalp_atisi", np.tanh(buf * 1.5), "Kalp atışı", "Gerilim"))

    # Lazer
    tt = t(0.35); f = 2600 * np.exp(-tt * 9) + 180
    out.append(save("lazer", (0.7 * tone(f) + 0.3 * square(f * 0.5)) * env(len(tt), 0.002, curve=3), "Lazer", "Oyun"))

    # Boing (yay)
    tt = t(0.8); f = 220 * (1 + 0.5 * np.sin(2 * np.pi * 11 * tt) * np.exp(-tt * 3.5)) * (1 + 0.3 * tt)
    out.append(save("boing", tone(f) * env(len(tt), 0.003, curve=3.5), "Boing", "Komik"))

    # Para (altın toplama)
    a = square(np.full(int(SR * 0.07), 987.8)) * 0.8
    b = square(np.full(int(SR * 0.4), 1318.5)) * env(int(SR * 0.4), 0.001, curve=5)
    out.append(save("para", lowpass(np.concatenate([a, b]), 5000), "Para", "Oyun"))

    # Seviye atla: hızlı arpej
    notes = [523.3, 659.3, 784.0, 1046.5, 1318.5, 1568.0, 2093.0]
    parts = [square(np.full(int(SR * (0.055 if i < 6 else 0.4)), f)) * env(int(SR * (0.055 if i < 6 else 0.4)), 0.002, curve=1.5 if i < 6 else 4)
             for i, f in enumerate(notes)]
    out.append(save("seviye_atla", lowpass(np.concatenate(parts), 6000) * 0.8, "Seviye atla", "Oyun"))

    # Patlama
    d = 1.8; tt = t(d)
    rumble = lowpass(rng.standard_normal(len(tt)), 3500 * np.exp(-tt * 3) + 120) * np.exp(-tt * 2.2)
    sub = tone(38 + 60 * np.exp(-tt * 8)) * np.exp(-tt * 2.5)
    out.append(save("patlama", np.tanh(2.2 * (rumble * 3 + sub)), "Patlama", "Vuruş"))

    # Kılıç: savrulma + metal tınlaması
    d = 1.1; n = int(SR * d)
    sw = bandnoise(0.25, 800, 5000) * np.sin(np.linspace(0, np.pi, int(SR * 0.25))) ** 2
    tt = t(0.9)
    ring = sum(a * np.sin(2 * np.pi * f * tt) * np.exp(-tt * k) for f, a, k in [(2150, 1, 4), (3310, .7, 5), (4720, .5, 6), (5930, .35, 8), (7400, .2, 10)])
    buf = np.zeros(n); place(buf, sw * 0.8, 0); place(buf, ring * 0.6, 0.2)
    out.append(save("kilic", buf, "Kılıç", "Vuruş"))

    # Fotoğraf makinesi deklanşörü
    buf = np.zeros(int(SR * 0.35))
    for at, g in ((0.0, 1.0), (0.09, 0.8)):
        cl = bandnoise(0.04, 6000, 2000) * env(int(SR * 0.04), 0.0005, curve=9)
        place(buf, cl * g, at)
    place(buf, bandnoise(0.09, 1500, 900) * 0.2 * np.hanning(int(SR * 0.09)), 0.005)
    out.append(save("kamera", buf, "Deklanşör", "Arayüz"))

    # Düşüş: aşağı inen ıslık + yere çarpma
    tt = t(1.1); f = np.geomspace(2200, 320, len(tt)) * (1 + 0.01 * np.sin(2 * np.pi * 7 * tt))
    fall = tone(f) * gate(tt, 0.02, 0.05) * 0.6
    tt2 = t(0.4); thud = tone(60 + 80 * np.exp(-tt2 * 30)) * env(len(tt2), 0.002, curve=8)
    out.append(save("dusme", np.concatenate([fall, thud]), "Düşüş", "Komik"))

    # Kaydırmalı düdük (yukarı)
    tt = t(0.75); f = np.geomspace(420, 1900, len(tt)) * (1 + 0.025 * np.sin(2 * np.pi * 9 * tt))
    out.append(save("slayt_dudugu", (tone(f) + 0.05 * rng.standard_normal(len(tt))) * gate(tt, 0.03, 0.08), "Düdük", "Komik"))

    # Kapı zili (ding-dong)
    buf = np.zeros(int(SR * 1.8)); place(buf, bell(659.3, 1.0, 2.2), 0); place(buf, bell(523.3, 1.4, 1.8), 0.45)
    out.append(save("kapi_zili", buf, "Kapı zili", "Arayüz"))

    # Alkış: binlerce kısa el çırpması
    d = 2.6; n = int(SR * d); buf = np.zeros(n)
    clap = lambda: bandnoise(0.02, rng.uniform(1500, 3500), rng.uniform(700, 1400)) * env(int(SR * 0.02), 0.0005, curve=7)  # noqa: E731
    shape = lambda x: np.clip(min(x / 0.25, (d - x) / 0.9), 0, 1)  # noqa: E731
    claps = [clap() for _ in range(40)]
    for _ in range(900):
        at = rng.uniform(0, d - 0.03)
        if rng.random() < shape(at):
            place(buf, claps[rng.integers(40)] * rng.uniform(0.3, 1), at)
    out.append(save("alkis", buf, "Alkış", "Komik", peak=0.8))

    # Glitch: kesik kesik dijital bozulma
    d = 0.6; n = int(SR * d); buf = np.zeros(n); at = 0.0
    while at < d - 0.02:
        L = rng.uniform(0.015, 0.06)
        tt = t(L); kind = rng.integers(3)
        if kind == 0:
            s2 = square(np.full(len(tt), rng.uniform(80, 1200)))
        elif kind == 1:
            s2 = rng.standard_normal(len(tt))
        else:
            s2 = np.round(tone(np.full(len(tt), rng.uniform(200, 3000))) * 3) / 3
        if rng.random() > 0.2:
            place(buf, s2 * rng.uniform(0.4, 1), at)
        at += L
    out.append(save("glitch", np.round(buf * 6) / 6, "Glitch", "Geçiş", peak=0.8))

    # Bas düşüşü (808)
    tt = t(1.4); f = 32 + 130 * np.exp(-tt * 3.5)
    out.append(save("bas_dusus", np.tanh(2.5 * tone(f)) * env(len(tt), 0.004, curve=2.2), "Bas düşüşü", "Geçiş"))

    # Plak çizilmesi
    d = 0.55; tt = t(d)
    rate = 1 + 0.9 * np.sin(2 * np.pi * 3.2 * tt + 1.2)
    sc = lowpass(rng.standard_normal(len(tt)), 600 + 3500 * np.abs(rate)) - lowpass(rng.standard_normal(len(tt)), 300)
    sc += 0.5 * saw(140 * (0.4 + np.abs(rate)))
    out.append(save("plak_cizik", sc * gate(tt, 0.01, 0.06), "Plak cızırtısı", "Komik"))

    # Bildirim
    buf = np.zeros(int(SR * 0.55))
    place(buf, tone(880, 0.25) * env(int(SR * .25), 0.004, curve=4), 0)
    place(buf, tone(1318.5, 0.35) * env(int(SR * .35), 0.004, curve=4), 0.12)
    out.append(save("bildirim", buf, "Bildirim", "Arayüz"))

    # Geri sayım: 3-2-1-başla
    buf = np.zeros(int(SR * 3.8))
    for i in range(3):
        place(buf, tone(880, 0.16) * gate(t(0.16), 0.005, 0.03), i)
    place(buf, (tone(1760, 0.7) + 0.4 * tone(2637, 0.7)) * env(int(SR * .7), 0.005, curve=2.5), 3)
    out.append(save("geri_sayim", buf, "Geri sayım", "Gerilim"))

    # Sihir: yükselen parıltılar
    d = 1.6; buf = np.zeros(int(SR * d))
    for i in range(55):
        at = rng.uniform(0, d - 0.35); f = 1800 + 4500 * (at / d) + rng.uniform(-400, 400)
        place(buf, tone(f, 0.3) * env(int(SR * 0.3), 0.002, curve=7) * rng.uniform(0.3, 1), at)
    shim = bandnoise(d, 4000, 9000) * 0.15 * np.sin(np.linspace(0, np.pi, int(SR * d)))
    out.append(save("sihir", buf + shim, "Sihir", "Geçiş"))

    # Telefon titreşimi
    buf = np.zeros(int(SR * 1.1))
    for at in (0.0, 0.6):
        tt = t(0.42); bz = lowpass(square(np.full(len(tt), 165)) * (1 + 0.3 * np.sin(2 * np.pi * 33 * tt)), 900)
        place(buf, bz * gate(tt, 0.02, 0.03), at)
    out.append(save("titresim", buf, "Titreşim", "Arayüz"))

    # Su damlası
    tt = t(0.22); f = 500 + 1300 * (1 - np.exp(-tt * 60))
    out.append(save("damla", tone(f) * env(len(tt), 0.001, curve=9), "Damla", "Arayüz"))

    # Rüzgâr geçişi
    d = 2.4; tt = t(d)
    cut = 500 + 1600 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.6 * tt - 1.5)) + 400 * np.sin(2 * np.pi * 2.3 * tt)
    wind = lowpass(rng.standard_normal(len(tt)), cut) - lowpass(rng.standard_normal(len(tt)), 150)
    out.append(save("ruzgar", wind * np.sin(np.linspace(0, np.pi, len(tt))) ** 1.2, "Rüzgâr", "Geçiş", peak=0.75))

    # Gerilim dronu: yükselen uyumsuz katman
    d = 3.2; tt = t(d)
    drone = sum(saw(np.full(len(tt), f)) for f in (55, 55.4, 82.6, 116.5))
    drone = lowpass(drone, 300 + 1500 * (tt / d) ** 2)
    hi = 0.15 * (tone(np.full(len(tt), 1244.5)) + tone(np.full(len(tt), 1318.5))) * (tt / d) ** 3
    out.append(save("gerilim", (drone * 0.4 + hi) * (tt / d) ** 1.5 * gate(tt, 0.05, 0.02), "Gerilim", "Gerilim", peak=0.8))

    # Dramatik "dan dan daaan"
    buf = np.zeros(int(SR * 2.4))
    for at, f, L in ((0.0, 146.8, 0.28), (0.36, 146.8, 0.28), (0.72, 138.6, 1.6)):
        tt = t(L); vib = np.ones(len(tt)) + (0.008 * np.sin(2 * np.pi * 5 * tt) if L > 1 else 0)
        br = sum(saw(f * m * vib) / m for m in (1, 2.0, 1.5))
        br = lowpass(br, 2200) * gate(tt, 0.015, 0.15 if L > 1 else 0.04)
        tim = tone(55 + 40 * np.exp(-tt * 20)) * np.exp(-tt * 6)
        place(buf, br * 0.6 + tim, at)
    out.append(save("dramatik", buf, "Dramatik", "Gerilim"))

    # Üzgün trombon (yanlış cevap)
    buf = np.zeros(int(SR * 2.5)); at = 0.0
    for f, L in ((293.7, 0.42), (277.2, 0.42), (261.6, 0.42), (246.9, 1.1)):
        tt = t(L); vib = np.ones(len(tt)) + (0.02 * np.sin(2 * np.pi * 6 * tt) * np.clip(tt / 0.3, 0, 1) if L > 1 else 0)
        wah = 600 + 1400 * np.sin(np.pi * np.clip(tt / min(L, 0.42), 0, 1))
        place(buf, lowpass(saw(f * vib) + 0.5 * saw(f * 2 * vib), wah) * gate(tt, 0.03, 0.08), at)
        at += L + 0.02
    out.append(save("yanlis_cevap", buf, "Üzgün trombon", "Komik"))

    # Daktilo: tuş vuruşları ve satır sonu zili
    buf = np.zeros(int(SR * 1.5)); at = 0.0
    for _ in range(9):
        k = bandnoise(0.035, rng.uniform(2500, 4500), rng.uniform(900, 1600)) * env(int(SR * 0.035), 0.0005, curve=8)
        thunk = tone(rng.uniform(140, 200), 0.035) * env(int(SR * 0.035), 0.001, curve=9) * 0.5
        place(buf, k + thunk, at); at += rng.uniform(0.07, 0.12)
    place(buf, bell(2093, 0.5, 4) * 0.5, at + 0.05)
    out.append(save("daktilo", buf, "Daktilo", "Arayüz"))

    return out


if __name__ == "__main__":
    main()
