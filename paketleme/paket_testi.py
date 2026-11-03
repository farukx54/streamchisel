"""Paketlenmiş Streamchisel.exe'yi gerçek işlerle dener (GitHub derlemesinde çalışır).

Örnek videoyu açar; kamera arama, ses dalgası ve en iyi anları AYNI ANDA başlatır
(gerçek kullanımda olduğu gibi), sonra kısa bir klip dışa aktarır. Biri hata verirse çıkış kodu 1.
"""
import json
import sys
import time
import urllib.request

B = "http://127.0.0.1:47321"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with op.open(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def wait(job, name, limit=600):
    t0 = time.time()
    while time.time() - t0 < limit:
        j = call(f"/api/job/{job}")
        if j.get("done"):
            if j.get("error"):
                print(f"HATA {name}: {j['error']}")
                return None
            print(f"tamam {name} ({time.time() - t0:.1f} sn)")
            return j["result"]
        time.sleep(1)
    print(f"HATA {name}: zaman aşımı")
    return None


for _ in range(60):  # program açılana kadar bekle
    try:
        print("lisans:", call("/api/license")["mode"]); break
    except Exception:
        time.sleep(2)
else:
    print("HATA: program açılmadı"); sys.exit(1)

media = call("/api/demo", {})["data"]["media"]
path = media["path"]
print("örnek video:", media["name"], media["duration"], "sn")
jobs = {
    "kamera": call("/api/detect", {"path": path, "start": 0, "end": 30})["job"],
    "zaman çizelgesi": call("/api/timeline", {"path": path})["job"],
    "en iyi anlar": call("/api/highlights", {"path": path, "clip_len": 15, "count": 3})["job"],
}
res = {k: wait(v, k) for k, v in jobs.items()}
ok = all(r is not None for r in res.values())
if ok:
    print("bulunan anlar:", [(h["start"], h["end"]) for h in res["en iyi anlar"]["items"]])
    ok = ok and bool(res["zaman çizelgesi"].get("peaks")) and bool(res["zaman çizelgesi"].get("strip"))
proj = {"input": path, "output_name": "paket_testi", "range": {"start": 15, "end": 20},
        "layout": {"preset": "stack"}, "silence": {"enabled": True},
        "subtitles": {"enabled": True, "chunks": [[{"start": 16.6, "end": 17.4, "text": "OHA"}, {"start": 17.4, "end": 18.2, "text": "YENDİK!"}]], "animation": "bounce"},
        "hook": {"enabled": True, "text": "Test"}, "progress": {"enabled": True},
        "audio": {"source_volume": 1, "sfx": [{"path": "sfx:patlama", "time": 17.5, "volume": 0.8}],
                  "enhance": {"denoise": True, "normalize": True}},
        "export": {"quality": "balanced", "encoder": "auto"}}
r = wait(call("/api/render", {"project": proj, "label": "test"})["job"], "dışa aktarma")
ok = ok and r is not None
if r:
    print("çıktı:", r["output"], r["duration"], "sn, kodlayıcı:", r["encoder"])
print("SONUÇ:", "BAŞARILI" if ok else "BAŞARISIZ")
sys.exit(0 if ok else 1)
