"""Setup ile kurulan Streamchisel'in başlangıç noktası (Streamchisel.exe).

- Komut penceresi açılmaz; çıktılar ~/.streamchisel/streamchisel.log dosyasına yazılır.
- Program zaten açıksa ikinci kopya başlatılmaz, mevcut pencere yeniden açılır.
- Pencere kapanınca program da kapanır.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

if not getattr(sys, "frozen", False):  # paketlenmeden denerken proje klasörünü bul
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_DIR = Path.home() / ".streamchisel"
LOG_DIR.mkdir(parents=True, exist_ok=True)
PREFERRED_PORT = 47321


def _log_to_file() -> None:
    if sys.stdout is None or not sys.stdout.isatty():
        f = open(LOG_DIR / "streamchisel.log", "a", encoding="utf-8", buffering=1)
        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        sys.stdout = sys.stderr = f


def _running_instance() -> str | None:
    url = f"http://127.0.0.1:{PREFERRED_PORT}/"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # yerel adres: vekil sunucu kullanma
        with opener.open(url + "api/license", timeout=1.5) as r:
            if "mode" in json.loads(r.read().decode("utf-8")):
                return url
    except Exception:
        return None
    return None


def main() -> None:
    _log_to_file()
    from klipo_app import license as lic
    from klipo_app.server import open_window, start_server

    url = _running_instance()
    if url:  # zaten açık: sadece pencereyi göster
        open_window(url, own_profile=True)
        return
    lic.refresh_in_background()
    srv, url = start_server()
    print("Streamchisel çalışıyor:", url, flush=True)
    if os.environ.get("KLIPO_NO_UI") != "1":
        open_window(url, own_profile=True)
    else:  # test: pencere yok, sonsuza kadar çalış
        while True:
            time.sleep(3600)
    # Pencere açık olduğu sürece arayüz birkaç saniyede bir sinyal gönderir. Sinyal 25 sn
    # kesilirse (pencere kapandı) ve devam eden dışa aktarma yoksa program kapanır.
    # Edge'in kendi süreci izlenmez: pencere kapansa da Edge arka planda kalabiliyor.
    from klipo_app import server as s
    started = time.time()
    while True:
        time.sleep(2)
        quiet = time.time() - s._last_seen["t"]
        if time.time() - started < 90 and quiet < 90:  # pencere ilk açılırken acele etme
            continue
        if quiet < 25:
            continue
        with s._lock:
            busy = any(not j["done"] for j in s._jobs.values())
        if not busy:
            break
    srv.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
