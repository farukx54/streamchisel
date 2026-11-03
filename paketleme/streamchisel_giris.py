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
        open_window(url)
        return
    lic.refresh_in_background()
    srv, url = start_server()
    print("Streamchisel çalışıyor:", url, flush=True)
    win = None if os.environ.get("KLIPO_NO_UI") == "1" else open_window(url, own_profile=True)
    if win is None:  # Edge yok (varsayılan tarayıcı açıldı) ya da test: program açık kalır
        while True:
            time.sleep(3600)
    win.wait()
    # Pencere kapandı: devam eden dışa aktarma varsa bitmesini bekle
    from klipo_app import server as s
    for _ in range(3600):
        with s._lock:
            busy = any(not j["done"] for j in s._jobs.values() if j["kind"] in ("render", "thumbnail"))
        if not busy:
            break
        time.sleep(1)
    srv.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
