"""Streamchisel editörünün yerel sunucusu.

Sadece bu bilgisayardan (127.0.0.1) erişilir. Arayüz (web/index.html) bu sunucuya
istek atar; sunucu da çekirdek motoru (klipo_core) çağırır. İleride Tauri sürümünde
aynı arayüz kullanılacak, sadece bu katman Rust tarafına taşınacak.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# Paketlenmiş (Setup ile kurulmuş) sürümde dosyalar PyInstaller'ın açtığı klasördedir
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ROOT = _BASE / "klipo_app"
WEB = ROOT / "web"
FONTS = _BASE / "assets" / "fonts"
sys.path.insert(0, str(_BASE))

from klipo_core.ffmpeg_tools import probe  # noqa: E402
from klipo_app import license as lic  # noqa: E402

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".avi", ".m4v"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
SFX_DIR = _BASE / "assets" / "sfx"

# Sadece kullanıcının seçtiği / indirdiği / ürettiği dosyalar tarayıcıya verilir
_allowed: set[str] = set()
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def default_out_dir() -> Path:
    d = Path.home() / "Videos" / "Streamchisel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def allow(path: str) -> str:
    p = str(Path(path).resolve())
    _allowed.add(p.lower())
    return p


def is_allowed(path: str) -> bool:
    return str(Path(path).resolve()).lower() in _allowed


# --------------------------------------------------------------------------- işler (arka plan)

_last_seen = {"t": time.time()}  # pencereden son sinyal (Setup sürümü kapanmak için buna bakar)
_render_sem = threading.Semaphore(1)  # dışa aktarmalar sırayla: bilgisayar kasılmasın


def start_job(kind: str, fn, label: str = "") -> str:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "label": label, "stage": "queued", "progress": 0.0, "done": False,
           "error": None, "result": None, "events": {}, "cancel": False, "created": time.time()}
    with _lock:
        _jobs[jid] = job

    def emit(ev: dict) -> None:
        with _lock:
            job["stage"] = ev.get("stage", job["stage"])
            job["progress"] = float(ev.get("progress", job["progress"]))
            extra = {k: v for k, v in ev.items() if k not in ("stage", "progress")}
            if extra:
                job["events"][job["stage"]] = extra

    def runner() -> None:
        try:
            if kind in ("render", "thumbnail"):
                with _render_sem:
                    if job["cancel"]:
                        raise RuntimeError("İptal edildi.")
                    res = fn(emit)
            else:
                res = fn(emit)
            with _lock:
                job.update(result=res, done=True, stage="done", progress=1.0)
        except Exception as e:  # arayüzde gösterilecek
            traceback.print_exc()
            with _lock:
                job.update(error=str(e), done=True, stage="error")

    threading.Thread(target=runner, daemon=True).start()
    return jid


def job_download(url: str, quality: str):
    from klipo_core.download import download

    def fn(emit):
        path = download(url, str(default_out_dir() / "indirilenler"), quality, emit)
        return {"path": allow(path), "name": Path(path).name}
    return fn


def job_render(project: dict):
    from klipo_core.render import render

    def fn(emit):
        _prepare_project(project)
        out_name = _safe_name(project.pop("output_name", None) or Path(project["input"]).stem + "_dikey")
        project["output"] = str(_unique(default_out_dir() / f"{out_name}.mp4"))
        res = render(project, emit)
        allow(res["output"])
        return res
    return fn


def job_detect(path: str, start: float, end: float | None):
    from klipo_core.detect import find_faces

    def fn(emit):
        if not is_allowed(path):
            raise PermissionError("Bu dosya editörde açılmamış.")
        emit({"stage": "detect", "progress": 0.1})
        return find_faces(path, start or 0.0, end)
    return fn


def job_transcribe(path: str, start: float, end: float | None, model: str, language: str | None,
                   translate: bool = False):
    from klipo_core.subtitles import transcribe

    def fn(emit):
        if not is_allowed(path):
            raise PermissionError("Bu dosya editörde açılmamış.")
        emit({"stage": "transcribe", "progress": 0.0})
        words, lang = transcribe(path, start or 0.0, end, model, language or None,
                                 on_progress=lambda p: emit({"stage": "transcribe", "progress": p}),
                                 task="translate" if translate else "transcribe",
                                 on_download=lambda: emit({"stage": "model", "progress": 0.0}))
        off = start or 0.0  # arayüz kaynak videonun mutlak zamanlarıyla çalışır
        return {"language": lang, "start": off, "end": end,
                "words": [{"start": round(w.start + off, 3), "end": round(w.end + off, 3), "text": w.text}
                          for w in words]}
    return fn


def job_silence(path: str, threshold_db: float, min_silence: float):
    from klipo_core.silence import detect_silences

    def fn(emit):
        if not is_allowed(path):
            raise PermissionError("Bu dosya editörde açılmamış.")
        emit({"stage": "silence", "progress": 0.1})
        sil = detect_silences(path, threshold_db, min_silence)
        dur = probe(path)["duration"]
        return {"silences": [[round(a, 3), round(min(b, dur), 3)] for a, b in sil]}
    return fn


def job_highlights(path: str, start: float, end: float | None, clip_len: float, count: int, words):
    from klipo_core.highlights import curve_preview, find_highlights

    def fn(emit):
        if not is_allowed(path):
            raise PermissionError("Bu dosya editörde açılmamış.")
        emit({"stage": "highlights", "progress": 0.0})
        items = find_highlights(path, start or 0.0, end, clip_len, count, words,
                                on_progress=lambda p: emit({"stage": "highlights", "progress": p * 0.9}))
        curve = curve_preview(path, start or 0.0, end)
        return {"items": items, "curve": curve}
    return fn


def job_timeline(path: str):
    from klipo_core.peaks import RATE, STRIP_H, STRIP_N, filmstrip, waveform

    def fn(emit):
        if not is_allowed(path):
            raise PermissionError("Bu dosya editörde açılmamış.")
        res: dict = {"rate": RATE, "count": STRIP_N, "height": STRIP_H}
        # Önce kare şeridi (hızlı), sonra dalga (uzun yayında birkaç saniye sürer)
        try:
            res["strip"] = filmstrip(path, lambda p: emit({"stage": "strip", "progress": p * 0.3})).name
        except Exception:
            traceback.print_exc()
        pk = waveform(path, lambda p: emit({"stage": "wave", "progress": 0.3 + p * 0.7}))
        res["peaks"] = pk.name if pk else None
        return res
    return fn


def _prepare_project(project: dict) -> dict:
    """Arayüzden gelen projeyi doğrular; logo ve ses yollarını hazırlar."""
    if not is_allowed(project.get("input", "")):
        raise PermissionError("Bu dosya editörde açılmamış.")
    logo_png = project.pop("logo_png", None)
    if logo_png and project.get("logo"):
        import base64
        data = base64.b64decode(logo_png.split(",", 1)[1])
        f = app_dir() / "tmp" / f"logo_{uuid.uuid4().hex[:8]}.png"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(data)
        project["logo"]["path"] = str(f)
    else:
        project["logo"] = None
    aud = project.get("audio") or {}
    for item in ([aud.get("music")] if aud.get("music") else []) + list(aud.get("sfx") or []):
        pth = item.get("path", "")
        if not pth.startswith("sfx:") and not is_allowed(pth):
            raise PermissionError("Ses dosyası editörde seçilmemiş.")
    return project


def _safe_name(name: str, fallback: str = "klip") -> str:
    name = "".join(c for c in (name or "") if c not in '<>:"/\\|?*').strip()
    return name or fallback


def _unique(path: Path) -> Path:
    i, p = 1, path
    while p.exists():
        p = path.with_name(f"{path.stem} ({i}){path.suffix}")
        i += 1
    return p


def job_thumbnail(project: dict, t: float | None, title: str, style: str):
    from klipo_core.render import render_thumbnail

    def fn(emit):
        proj = _prepare_project(project)
        name = _safe_name(proj.pop("output_name", None) or Path(proj["input"]).stem, "kapak")
        out = _unique(default_out_dir() / "kapaklar" / f"{name}_kapak.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        proj["output"] = str(out.with_suffix(".mp4"))
        res = render_thumbnail(proj, t, title, str(out), style, emit)
        allow(res["output"])
        return res
    return fn


# --------------------------------------------------------------------------- projeler (.scproj)

def projects_dir() -> Path:
    d = default_out_dir() / "projeler"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _allow_project_files(data: dict) -> None:
    """Proje açılınca içindeki video/müzik/logo dosyaları tekrar kullanılabilsin."""
    media = data.get("media") or {}
    for pth in (media.get("path"), ((data.get("S") or {}).get("music") or {}).get("path"),
                (((data.get("S") or {}).get("logo") or {}).get("file") or {}).get("path")):
        if pth and Path(pth).is_file():
            allow(pth)
    for fx in (data.get("P") or {}).get("sfx") or []:
        pth = fx.get("path", "")
        if pth and not pth.startswith("sfx:") and Path(pth).is_file():
            allow(pth)


def list_projects() -> list[dict]:
    out = []
    for f in sorted(projects_dir().glob("*.scproj"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"path": str(f), "name": f.stem, "video": (d.get("media") or {}).get("name"),
                        "saved": int(f.stat().st_mtime)})
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- telefona gönder (yerel ağ + QR)

_shares: dict[str, dict] = {}
_share_srv = {"port": None}


def lan_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # paket gönderilmez; sadece hangi ağ kartının kullanıldığını öğrenir
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class ShareHandler(BaseHTTPRequestHandler):
    """Sadece paylaşılan dosyayı, rastgele anahtarla ve 30 dakikalığına verir."""
    server_version = "Streamchisel"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        sh = _shares.get(parts[0]) if parts and parts[0] else None
        if not sh or sh["expires"] < time.time() or not Path(sh["path"]).is_file():
            self.send_response(404); self.end_headers(); self.wfile.write("Bağlantının süresi doldu.".encode("utf-8"))
            return
        f = Path(sh["path"])
        if len(parts) == 1:  # telefonda açılan küçük sayfa
            name = f.name.replace("&", "&amp;").replace("<", "&lt;")
            is_img = f.suffix.lower() in (".jpg", ".jpeg", ".png")
            media = (f'<img src="/{parts[0]}/dosya" alt="">' if is_img else
                     f'<video src="/{parts[0]}/dosya" controls playsinline></video>')
            html = f"""<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Streamchisel</title><style>body{{margin:0;background:#0e0f11;color:#eee;font:16px system-ui;padding:16px;text-align:center}}
video,img{{width:100%;max-height:70vh;border-radius:12px;background:#000}}a{{display:block;margin:16px 0;padding:14px;border-radius:10px;background:#C8F135;color:#111;font-weight:700;text-decoration:none}}
p{{color:#999;font-size:13px}}</style><h3>{name}</h3>{media}<a href="/{parts[0]}/dosya?indir=1" download="{name}">İndir</a>
<p>iPhone: videoyu açıp paylaş → "Videoyu kaydet". Android: İndir'e dokun.</p></html>"""
            data = html.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        size = f.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, z = rng[6:].split(",")[0].partition("-")
            start = int(a) if a else max(0, size - int(z))
            end = min(int(z) if (a and z) else size - 1, size - 1)
            self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if "indir=1" in self.path:
            from urllib.parse import quote
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(f.name)}")
        self.end_headers()
        try:
            with open(f, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass


def share_file(path: str) -> dict:
    import secrets

    if _share_srv["port"] is None:
        srv = ThreadingHTTPServer(("0.0.0.0", 0), ShareHandler)
        _share_srv["port"] = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    token = secrets.token_urlsafe(12)
    _shares[token] = {"path": path, "expires": time.time() + 30 * 60}
    url = f"http://{lan_ip()}:{_share_srv['port']}/{token}"
    svg = None
    try:
        import segno
        svg = segno.make(url, error="m").svg_inline(scale=6, border=2, dark="#111111", light="#ffffff")
    except Exception:
        pass
    return {"url": url, "svg": svg, "minutes": 30}


# --------------------------------------------------------------------------- kalıcı durum (ayarlar, düzenler, son projeler)

def app_dir() -> Path:
    d = Path.home() / ".streamchisel"
    d.mkdir(parents=True, exist_ok=True)
    return d


_state_lock = threading.Lock()


def load_state() -> dict:
    try:
        return json.loads((app_dir() / "state.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(patch: dict) -> dict:
    with _state_lock:
        st = load_state()
        for k in ("settings", "layouts"):
            if k in patch:
                st[k] = patch[k]
        tmp = app_dir() / "state.json.tmp"
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(app_dir() / "state.json")
        return st


def remember_recent(info: dict) -> None:
    with _state_lock:
        st = load_state()
        rec = [r for r in st.get("recent", []) if r.get("path", "").lower() != info["path"].lower()]
        rec.insert(0, {"path": info["path"], "name": info["name"], "duration": info.get("duration"),
                       "opened": int(time.time())})
        st["recent"] = rec[:8]
        tmp = app_dir() / "state.json.tmp"
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(app_dir() / "state.json")


def recent_list() -> list[dict]:
    out = []
    for r in load_state().get("recent", []):
        if Path(r["path"]).is_file():
            allow(r["path"])
            out.append(r)
    return out


def thumbnail(path: str) -> Path | None:
    """Son projeler listesi için küçük resim (önbellekli)."""
    import hashlib

    from klipo_core.ffmpeg_tools import find_tool, run

    d = app_dir() / "thumbs"
    d.mkdir(exist_ok=True)
    f = d / (hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16] + ".jpg")
    if not f.exists():
        try:
            t = max(0.0, probe(path)["duration"] * 0.2)
            run([find_tool("ffmpeg"), "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path,
                 "-frames:v", "1", "-vf", "scale=320:-2", str(f)], check=False)
        except Exception:
            return None
    return f if f.exists() else None


# --------------------------------------------------------------------------- Windows yardımcıları

def pick_file(kind: str = "video") -> str | None:
    """Windows dosya seçme penceresi (tkinter, Python ile birlikte gelir)."""
    import tkinter as tk
    from tkinter import filedialog

    ext, title, label = {
        "video": (VIDEO_EXT, "Yayın kaydını seç", "Video"),
        "image": (IMAGE_EXT, "Logo seç", "Görsel"),
        "audio": (AUDIO_EXT, "Ses dosyası seç", "Ses"),
    }[kind]
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title=title, filetypes=[(label, " ".join("*" + e for e in sorted(ext))), ("Tümü", "*.*")])
    root.destroy()
    return path or None


def reveal(path: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(Path(path))])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", str(Path(path).parent)])


def open_file(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


# --------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Streamchisel/0.8"

    def log_message(self, fmt, *args):  # konsolu kirletme
        pass

    # yardımcılar
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _check_origin(self) -> bool:
        # Başka bir sitenin bu yerel sunucuya istek atmasını engelle
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and urlparse(origin).netloc != host:
            self._json({"error": "izin yok"}, 403)
            return False
        if not host.startswith(("127.0.0.1", "localhost")):
            self._json({"error": "izin yok"}, 403)
            return False
        return True

    # GET
    def do_GET(self):
        if not self._check_origin():
            return
        _last_seen["t"] = time.time()
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._static(WEB / "index.html")
            if u.path.startswith("/static/"):
                f = (WEB / unquote(u.path[len("/static/"):])).resolve()
                if WEB in f.parents and f.is_file():
                    return self._static(f)
                return self._json({"error": "yok"}, 404)
            if u.path == "/media":
                return self._media(q.get("path", ""))
            if u.path.startswith("/fonts/"):
                f = (FONTS / unquote(u.path[len("/fonts/"):])).resolve()
                if FONTS in f.parents and f.is_file():
                    return self._static(f)
                return self._json({"error": "yok"}, 404)
            if u.path.startswith("/api/job/"):
                jid = u.path.rsplit("/", 1)[-1]
                with _lock:
                    job = _jobs.get(jid)
                    data = json.loads(json.dumps(job)) if job else None
                return self._json(data or {"error": "iş bulunamadı"}, 200 if data else 404)
            if u.path == "/api/ping":
                return self._json({"ok": True})
            if u.path == "/api/license":
                return self._json({**lic.status(), "update": lic.cached_update(), "version": __import__("klipo_core").__version__})
            if u.path == "/api/jobs":
                with _lock:
                    items = [{k: j[k] for k in ("id", "kind", "label", "stage", "progress", "done", "error", "result", "created")}
                             for j in _jobs.values() if j["kind"] in ("render", "thumbnail")]
                return self._json({"items": sorted(items, key=lambda j: j["created"])[-30:]})
            if u.path == "/api/projects":
                return self._json({"items": list_projects(), "dir": str(projects_dir())})
            if u.path == "/api/autosave":
                f = app_dir() / "autosave.scproj"
                if not f.is_file():
                    return self._json({"data": None})
                data = json.loads(f.read_text(encoding="utf-8"))
                _allow_project_files(data)
                return self._json({"data": data})
            if u.path.startswith("/cache/"):
                import re
                from klipo_core.peaks import cache_dir
                name = unquote(u.path[len("/cache/"):])
                if not re.fullmatch(r"[0-9a-f]{20}\.(peaks|strip\.jpg)", name):
                    return self._json({"error": "yok"}, 404)
                f = cache_dir() / name
                return self._static(f) if f.is_file() else self._json({"error": "yok"}, 404)
            if u.path == "/api/sfx":
                return self._json({"items": json.loads((SFX_DIR / "library.json").read_text(encoding="utf-8"))})
            if u.path.startswith("/sfx/"):
                f = (SFX_DIR / unquote(u.path[len("/sfx/"):])).resolve()
                if SFX_DIR in f.parents and f.suffix == ".wav" and f.is_file():
                    return self._static(f)
                return self._json({"error": "yok"}, 404)
            if u.path == "/api/state":
                st = load_state()
                # Kayıtlı müzik ve logo dosyaları yeniden açılışta da kullanılabilsin
                for layer in [st.get("settings") or {}] + [l.get("data") or {} for l in st.get("layouts", [])]:
                    for pth in ((layer.get("music") or {}).get("path"), ((layer.get("logo") or {}).get("file") or {}).get("path")):
                        if pth and Path(pth).is_file():
                            allow(pth)
                return self._json({"settings": st.get("settings"), "layouts": st.get("layouts", []),
                                   "recent": recent_list()})
            if u.path == "/api/thumb":
                p = q.get("path", "")
                if not is_allowed(p):
                    return self._json({"error": "izin yok"}, 403)
                f = thumbnail(p)
                return self._static(f) if f else self._json({"error": "yok"}, 404)
            if u.path == "/api/info":
                from klipo_core.ffmpeg_tools import detect_encoder
                return self._json({"encoder": detect_encoder(), "out_dir": str(default_out_dir())})
            return self._json({"error": "yok"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        if not self._check_origin():
            return
        _last_seen["t"] = time.time()
        u = urlparse(self.path)
        try:
            if u.path == "/api/upload":  # sürükle-bırak: dosya gövdede akarak gelir
                return self._json(self._upload())
            b = self._body()
            if u.path == "/api/bye":  # pencere kapanıyor: birkaç saniye içinde yeniden bağlanmazsa program kapanır
                _last_seen["t"] = time.time() - 20
                return self._json({"ok": True})
            if u.path == "/api/log":  # arayüz hataları komut penceresine yazılır (destek için)
                print(f"[ARAYÜZ HATASI] {str(b.get('msg'))[:500]}\n{str(b.get('stack'))[:1500]}", flush=True)
                return self._json({"ok": True})
            if u.path == "/api/state":
                save_state(b)
                return self._json({"ok": True})
            if u.path == "/api/detect":
                return self._json({"job": start_job("detect", job_detect(b["path"], b.get("start"), b.get("end")))})
            if u.path == "/api/transcribe":
                return self._json({"job": start_job("transcribe", job_transcribe(
                    b["path"], b.get("start"), b.get("end"), b.get("model", "small"), b.get("language"),
                    bool(b.get("translate"))))})
            if u.path == "/api/license/activate":
                try:
                    return self._json(lic.activate(str(b.get("key", ""))))
                except lic.LicenseError as e:
                    return self._json({"error": str(e), "code": e.code}, 400)
            if u.path == "/api/license/deactivate":
                try:
                    return self._json(lic.deactivate())
                except lic.LicenseError as e:
                    return self._json({"error": str(e), "code": e.code}, 400)
            if u.path == "/api/license/refresh":
                lic.refresh(force=True); lic.check_update()
                return self._json({**lic.status(), "update": lic.cached_update()})
            if u.path == "/api/openurl":
                url = str(b.get("url", ""))
                upd = lic.cached_update() or {}
                if url and url in (lic.settings().get("buy_url"), upd.get("url")) and url.startswith("https://"):
                    webbrowser.open(url)
                    return self._json({"ok": True})
                return self._json({"error": "izin yok"}, 403)
            if u.path == "/api/timeline":
                return self._json({"job": start_job("timeline", job_timeline(b["path"]))})
            if u.path == "/api/highlights":
                return self._json({"job": start_job("highlights", job_highlights(
                    b["path"], b.get("start"), b.get("end"), float(b.get("clip_len", 45)),
                    int(b.get("count", 6)), b.get("words")))})
            if u.path == "/api/thumbnail":
                b["project"]["watermark"] = lic.settings().get("watermark", "Streamchisel") if lic.status()["watermark"] else ""
                return self._json({"job": start_job("thumbnail", job_thumbnail(
                    b["project"], b.get("time"), str(b.get("title", "")), b.get("style", "title")),
                    label=str(b.get("label") or "Kapak"))})
            if u.path == "/api/suggest":
                from klipo_core.suggest import suggest
                return self._json(suggest(str(b.get("text", "")), b.get("language"), b.get("platform", "genel"),
                                          str(b.get("channel", "")), str(b.get("game", ""))))
            if u.path == "/api/cancel":
                with _lock:
                    j = _jobs.get(b.get("job", ""))
                    if j and j["stage"] == "queued":
                        j["cancel"] = True
                return self._json({"ok": bool(j)})
            if u.path == "/api/jobs/clear":
                with _lock:
                    for k in [k for k, j in _jobs.items() if j["done"]]:
                        del _jobs[k]
                return self._json({"ok": True})
            if u.path in ("/api/project/save", "/api/autosave"):
                data = b.get("data") or {}
                if u.path == "/api/autosave":
                    f = app_dir() / "autosave.scproj"
                else:
                    f = projects_dir() / (_safe_name(b.get("name"), "proje") + ".scproj")
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                tmp.replace(f)
                return self._json({"ok": True, "path": str(f), "name": f.stem})
            if u.path == "/api/project/open":
                f = Path(b.get("path", "")).resolve()
                if f.parent != projects_dir().resolve() or f.suffix != ".scproj":
                    if not b.get("picked"):
                        return self._json({"error": "izin yok"}, 403)
                data = json.loads(f.read_text(encoding="utf-8"))
                _allow_project_files(data)
                media = data.get("media") or {}
                if media.get("path") and not Path(media["path"]).is_file():
                    return self._json({"error": f"Projedeki video bulunamadı: {media['path']}"}, 404)
                if media.get("path"):
                    data["media"] = {**media, **self._open_video(media["path"])}
                return self._json({"data": data, "name": f.stem})
            if u.path == "/api/demo":
                d = _BASE / "assets" / "demo"
                data = json.loads((d / "ornek.json").read_text(encoding="utf-8"))
                data["media"] = self._open_video(str(d / "ornek_yayin.mp4"))
                return self._json({"data": data})
            if u.path == "/api/project/pick":
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
                p = filedialog.askopenfilename(title="Proje aç", initialdir=str(projects_dir()),
                                               filetypes=[("Streamchisel projesi", "*.scproj")])
                root.destroy()
                return self._json({"path": p or None})
            if u.path == "/api/share":
                p = b.get("path", "")
                if not is_allowed(p):
                    return self._json({"error": "izin yok"}, 403)
                return self._json(share_file(str(Path(p).resolve())))
            if u.path == "/api/silence":
                return self._json({"job": start_job("silence", job_silence(
                    b["path"], float(b.get("threshold_db", -38)), float(b.get("min_silence", 0.8))))})
            if u.path == "/api/pick":
                kind = b.get("kind", "video")
                p = pick_file(kind)
                if not p:
                    return self._json({"path": None})
                if kind == "video":
                    return self._json(self._open_video(p))
                return self._json({"path": allow(p), "name": Path(p).name, "kind": kind})
            if u.path == "/api/open":
                return self._json(self._open_video(b["path"]))
            if u.path == "/api/download":
                url = (b.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    return self._json({"error": "Geçerli bir link girin."}, 400)
                return self._json({"job": start_job("download", job_download(url, b.get("quality", "best")))})
            if u.path == "/api/render":
                try:
                    wm = lic.begin_export()
                except lic.LicenseError as e:
                    return self._json({"error": str(e), "code": e.code}, 402)
                b["project"]["watermark"] = lic.settings().get("watermark", "Streamchisel") if wm else ""
                inner = job_render(b["project"])

                def counted(emit, inner=inner, wm=wm):
                    ok = False
                    try:
                        r = inner(emit); ok = True
                        return r
                    finally:
                        if wm:
                            lic.end_export(ok)
                return self._json({"job": start_job("render", counted,
                                                    label=str(b.get("label") or b["project"].get("output_name") or "Klip"))})
            if u.path in ("/api/reveal", "/api/play"):
                p = b.get("path", "")
                if not is_allowed(p):
                    return self._json({"error": "izin yok"}, 403)
                (reveal if u.path == "/api/reveal" else open_file)(p)
                return self._json({"ok": True})
            return self._json({"error": "yok"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def _open_video(self, path: str) -> dict:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError("Dosya bulunamadı.")
        info = {"path": allow(str(p)), "name": p.name, **probe(str(p))}
        remember_recent(info)
        return info

    def _upload(self) -> dict:
        name = Path(unquote(self.headers.get("X-Filename", "video.mp4"))).name
        name = "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "video.mp4"
        ext = Path(name).suffix.lower()
        kind = "video" if ext in VIDEO_EXT else "image" if ext in IMAGE_EXT else "audio" if ext in AUDIO_EXT else None
        if not kind:
            raise ValueError("Bu dosya türü desteklenmiyor.")
        n = int(self.headers.get("Content-Length") or 0)
        d = default_out_dir() / ("kaynaklar" if kind == "video" else "logolar" if kind == "image" else "sesler")
        d.mkdir(parents=True, exist_ok=True)
        dest = d / name
        i = 1
        while dest.exists():
            dest = d / f"{Path(name).stem} ({i}){Path(name).suffix}"
            i += 1
        left = n
        with open(dest, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(4 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            dest.unlink(missing_ok=True)
            raise IOError("Dosya yarıda kesildi.")
        if kind != "video":
            return {"path": allow(str(dest)), "name": dest.name, "kind": kind}
        return self._open_video(str(dest))

    def _static(self, f: Path):
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if f.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _media(self, path: str):
        """Video akışı; tarayıcının ileri-geri sarabilmesi için Range desteği var."""
        if not path or not is_allowed(path):
            return self._json({"error": "izin yok"}, 403)
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, z = rng[6:].split(",")[0].partition("-")
            if a:
                start = int(a)
                end = int(z) if z else size - 1
            else:  # son N bayt
                start = max(0, size - int(z))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        length = end - start + 1
        ctype = mimetypes.guess_type(path)[0] or "video/mp4"
        if path.lower().endswith(".svg"):
            ctype = "image/svg+xml"
        if path.lower().endswith((".mkv", ".ts", ".flv")):
            ctype = "video/mp4"  # tarayıcı denemesi için; açamazsa arayüz uyarır
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass  # kullanıcı sardı, tarayıcı isteği kesti


def free_port(preferred: int = 47321) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            if sys.platform != "win32":  # Linux/Mac: kapanan eski bağlantı portu bir süre tutmasın
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Boş port bulunamadı")


def edge_path() -> str | None:
    if sys.platform != "win32":
        return None
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(exe).exists():
            return exe
    return None


def open_window(url: str, own_profile: bool = False):
    """Edge'i 'uygulama penceresi' modunda aç (adres çubuğu yok); yoksa varsayılan tarayıcı.

    own_profile=True: ayrı bir Edge profiliyle açar ve süreci döndürür; pencere kapanınca
    süreç biter, böylece program da kapanabilir (Setup sürümü bunu kullanır)."""
    exe = edge_path()
    if exe:
        args = [exe, f"--app={url}", "--window-size=1440,900"]
        if own_profile:
            prof = app_dir() / "pencere"
            args += [f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
                     "--disable-features=Translate"]
        return subprocess.Popen(args)
    webbrowser.open(url)
    return None


def preload() -> None:
    """Ağır kütüphaneleri (numpy, OpenCV) arka plan işleri başlamadan, tek seferde yükler.

    Video açılınca kamera arama, ses dalgası ve en iyi anlar aynı anda başlar. Paketlenmiş
    sürümde bu kütüphaneler ilk kez aynı anda iki iş parçacığından yüklenirse çakışıyor
    ("cannot load module more than once per process"). Açılışta bir kez yüklemek bunu önler."""
    for mod in ("numpy", "cv2"):
        try:
            __import__(mod)
        except Exception:  # eksikse ilgili özellik kendi hatasını gösterir
            print(f"[ön yükleme] {mod} yüklenemedi:\n{traceback.format_exc()}", flush=True)


def start_server(port: int | None = None):
    """Sunucuyu arka planda başlatır; (sunucu, adres) döndürür."""
    preload()
    port = port or free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}/"


def main(open_ui: bool = True) -> None:
    preload()
    lic.refresh_in_background()  # lisans kontrolü ve güncelleme bilgisi (internet yoksa sessiz)
    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Streamchisel çalışıyor: {url}")
    print("Bu pencereyi kapatırsanız editör de kapanır.")
    if open_ui and os.environ.get("KLIPO_NO_UI") != "1":
        threading.Timer(0.6, open_window, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
