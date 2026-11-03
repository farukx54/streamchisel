"""Lisans: etkinleştirme, imza doğrulama, ücretsiz sürüm sınırı ve güncelleme kontrolü.

Sunucu (sunucu/lisans) lisans bilgisini Ed25519 ile imzalar; program gömülü açık anahtarla
doğrular. İmzayı sadece sunucudaki gizli anahtar üretebildiği için sahte lisans dosyası yazılamaz.
Lisans bu bilgisayarın kimliğine bağlıdır; dosyayı başka bilgisayara kopyalamak işe yaramaz.

assets/lisans.json içinde sunucu adresi ve açık anahtar boşsa program "geliştirici modunda"
çalışır (sınırsız, filigransız). Satış sürümünde bu iki alan doldurulur.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import platform
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from klipo_core import __version__

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
GRACE_DAYS = 30  # kontrol tarihi geçip internete hiç çıkılamazsa tanınan ek süre

_lock = threading.Lock()
_pending_free = {"n": 0}  # kuyrukta bekleyen ücretsiz dışa aktarmalar
_update_cache: dict = {}


def _app_dir() -> Path:
    d = Path.home() / ".streamchisel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings() -> dict:
    cfg = {"server": "", "public_key": "", "buy_url": "", "free_daily": 3,
           "watermark": "Streamchisel ile yapıldı"}
    try:
        cfg.update(json.loads((ROOT / "assets" / "lisans.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    try:  # sunucudan gelen son ayarlar (satın alma bağlantısı, günlük hak)
        cfg.update(json.loads((_app_dir() / "lisans_ayar.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def configured() -> bool:
    c = settings()
    return bool(servers() and c.get("public_key"))


# --------------------------------------------------------------------------- cihaz kimliği

def _raw_machine_id() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            pass
    for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = Path(f).read_text().strip()
            if v:
                return v
        except OSError:
            pass
    import uuid
    return f"{uuid.getnode():x}"


def device_id() -> str:
    return hashlib.sha256(("streamchisel|" + _raw_machine_id()).encode("utf-8")).hexdigest()


def device_name() -> str:
    return (platform.node() or "Bilgisayar")[:60]


# --------------------------------------------------------------------------- imza

def _verify(token_b64: str, sig_b64: str) -> dict | None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(settings()["public_key"]))
        raw = base64.b64decode(token_b64)
        pub.verify(base64.b64decode(sig_b64), raw)
        return json.loads(raw)
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return None


def _lic_file() -> Path:
    return _app_dir() / "lisans.json"


def _load() -> dict | None:
    try:
        d = json.loads(_lic_file().read_text(encoding="utf-8"))
    except Exception:
        return None
    p = _verify(d.get("token", ""), d.get("sig", ""))
    if not p or p.get("d") != device_id():
        return None
    return p


def _save(token: str, sig: str) -> None:
    f = _lic_file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"token": token, "sig": sig}), encoding="utf-8")
    tmp.replace(f)


# --------------------------------------------------------------------------- sunucu

class LicenseError(Exception):
    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code


def servers() -> list[str]:
    """Sunucu adresleri (tek adres ya da liste). Alan adı değişince eski ve yeni birlikte yazılır;
    biri çalışmazsa sıradaki denenir."""
    v = settings().get("server") or []
    return [u.rstrip("/") for u in ([v] if isinstance(v, str) else v) if str(u).startswith("http")]


def _call(action: str, body: dict | None = None, timeout: float = 10) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for base in servers():
        req = urllib.request.Request(base + f"/api.php?a={action}", data=data,
                                     method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": f"Streamchisel/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 502, 503, 504) and e.headers.get("Content-Type", "").find("json") < 0:
                continue  # bu adreste sunucu yok / bakımda: sıradakini dene
            try:
                j = json.loads(e.read().decode("utf-8"))
            except Exception:
                raise LicenseError(f"Lisans sunucusu hata verdi ({e.code}).", "server") from None
            raise LicenseError(j.get("error") or "Lisans sunucusu hata verdi.", j.get("code", "")) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    raise LicenseError("Lisans sunucusuna bağlanılamadı. İnternet bağlantını kontrol et.", "network")


def activate(key: str) -> dict:
    if not configured():
        raise LicenseError("Bu sürümde lisans sistemi kapalı (geliştirici modu).")
    r = _call("activate", {"key": key.strip(), "device": device_id(), "name": device_name(),
                           "app_version": __version__})
    p = _verify(r.get("token", ""), r.get("sig", ""))
    if not p or p.get("d") != device_id():
        raise LicenseError("Sunucudan gelen lisans doğrulanamadı. Programın güncel olduğundan emin ol.")
    _save(r["token"], r["sig"])
    if not p.get("exp"):
        (_app_dir() / "deneme_bitti.json").unlink(missing_ok=True)
    return status()


def deactivate() -> dict:
    p = _load()
    if p:
        _call("deactivate", {"key": p["k"], "device": device_id()})
    _lic_file().unlink(missing_ok=True)
    return status()


def refresh(force: bool = False) -> None:
    """Kontrol günü geldiyse sunucuya sor. İnternet yoksa sessizce sonraya bırakır."""
    if not configured():
        return
    p = _load()
    if p and (force or time.time() >= p.get("chk", 0)):
        try:
            r = _call("check", {"key": p["k"], "device": device_id(), "app_version": __version__})
            q = _verify(r.get("token", ""), r.get("sig", ""))
            if q and q.get("d") == device_id():
                _save(r["token"], r["sig"])
        except LicenseError as e:
            if e.code in ("revoked", "not_activated", "not_found", "expired", "used"):
                if e.code == "expired":
                    _mark_trial_over()
                _lic_file().unlink(missing_ok=True)
    try:
        info = _call("info", timeout=6)
        keep = {k: info[k] for k in ("buy_url", "free_daily") if k in info}
        if keep:
            (_app_dir() / "lisans_ayar.json").write_text(json.dumps(keep), encoding="utf-8")
    except Exception:
        pass


def refresh_in_background() -> None:
    threading.Thread(target=lambda: (refresh(), check_update()), daemon=True).start()


# --------------------------------------------------------------------------- ücretsiz sürüm sınırı

def _usage_file() -> Path:
    return _app_dir() / "kullanim.json"


def _mac(day: str, n: int) -> str:
    return hmac.new(device_id().encode(), f"{day}|{n}".encode(), hashlib.sha256).hexdigest()[:16]


def _today() -> str:
    return _dt.date.today().isoformat()


def used_today() -> int:
    try:
        u = json.loads(_usage_file().read_text(encoding="utf-8"))
    except Exception:
        return 0
    if u.get("day") != _today():
        return 0
    n = int(u.get("n", 0))
    return n if hmac.compare_digest(u.get("m", ""), _mac(u["day"], n)) else 10 ** 6  # elle değiştirilmiş


def _consume() -> None:
    n = min(used_today(), 10 ** 6) + 1
    day = _today()
    _usage_file().write_text(json.dumps({"day": day, "n": n, "m": _mac(day, n)}), encoding="utf-8")


def _clock_file() -> Path:
    return _app_dir() / "saat.json"


def _clock_rolled_back() -> bool:
    """Bilgisayarın saati geri alınmış mı? (deneme süresini uzatmaya karşı)
    Görülen en ileri zamanı imzalı saklar; saat ondan 1 saatten fazla gerideyse True."""
    now = int(time.time())
    seen = 0
    try:
        d = json.loads(_clock_file().read_text(encoding="utf-8"))
        if hmac.compare_digest(d.get("m", ""), _mac("saat", int(d["t"]))):
            seen = int(d["t"])
    except Exception:
        pass
    if now > seen:
        try:
            _clock_file().write_text(json.dumps({"t": now, "m": _mac("saat", now)}), encoding="utf-8")
        except OSError:
            pass
        return False
    return now < seen - 3600


def _mark_trial_over() -> None:
    try:
        (_app_dir() / "deneme_bitti.json").write_text(json.dumps({"t": int(time.time())}), encoding="utf-8")
    except OSError:
        pass


def status() -> dict:
    cfg = settings()
    if not configured():
        return {"mode": "dev", "licensed": True, "watermark": False}
    p = _load()
    now = time.time()
    if p and p.get("exp"):  # deneme kodu
        if now >= p["exp"] or _clock_rolled_back():
            _mark_trial_over()
            return {"mode": "expired", "licensed": False, "watermark": True, "buy_url": cfg.get("buy_url", ""),
                    "message": "Deneme süren doldu. Beğendiysen lisans alarak sınırsız ve yazısız kullanmaya devam edebilirsin.",
                    **_free_info(cfg)}
        k = p["k"]
        return {"mode": "trial", "licensed": True, "watermark": False, "plan": "trial", "expires": int(p["exp"]),
                "left_seconds": int(p["exp"] - now), "key": k[:8] + "-•••••-•••••-" + k[-5:]}
    if p and now > p.get("chk", 0) + GRACE_DAYS * 86400:
        return {"mode": "offline", "licensed": False, "watermark": True, "buy_url": cfg.get("buy_url", ""),
                "message": "Lisansın uzun süredir doğrulanamadı. Programı internete bağlıyken bir kez aç.",
                **_free_info(cfg)}
    if p:
        k = p["k"]
        return {"mode": "licensed", "licensed": True, "watermark": False, "plan": p.get("p", "lifetime"),
                "key": k[:8] + "-•••••-•••••-" + k[-5:]}
    st = {"mode": "free", "licensed": False, "watermark": True, "buy_url": cfg.get("buy_url", ""), **_free_info(cfg)}
    if (_app_dir() / "deneme_bitti.json").exists():
        st["message"] = "Deneme süren doldu. Beğendiysen lisans alarak sınırsız ve yazısız kullanmaya devam edebilirsin."
    return st


def _free_info(cfg: dict) -> dict:
    lim = int(cfg.get("free_daily", 3))
    used = min(used_today(), lim)
    return {"free_daily": lim, "used_today": used, "left_today": max(0, lim - used - _pending_free["n"])}


def begin_export() -> bool:
    """Dışa aktarma kuyruğa girerken çağrılır. True = filigran eklenmeli. Hak yoksa hata verir."""
    st = status()
    if st["licensed"]:
        return False
    with _lock:
        if st["left_today"] <= 0:
            raise LicenseError(f"Ücretsiz sürümde günde {st['free_daily']} video oluşturabilirsin; bugünkü hakkın doldu. "
                               "Sınırsız ve filigransız kullanım için lisans al.", "free_limit")
        _pending_free["n"] += 1
    return True


def end_export(success: bool) -> None:
    with _lock:
        _pending_free["n"] = max(0, _pending_free["n"] - 1)
        if success:
            _consume()


# --------------------------------------------------------------------------- güncelleme

def _ver(s: str) -> tuple:
    try:
        return tuple(int(x) for x in s.split("."))
    except ValueError:
        return (0,)


def check_update() -> dict | None:
    if not configured():
        return None
    try:
        r = _call("update", timeout=6)
    except LicenseError:
        return None
    if not r.get("token"):
        _update_cache.clear()
        return None
    info = _verify(r["token"], r.get("sig", ""))
    if info and _ver(info.get("version", "0")) > _ver(__version__) and str(info.get("url", "")).startswith("https://"):
        _update_cache.clear(); _update_cache.update(info)
        return info
    _update_cache.clear()
    return None


def cached_update() -> dict | None:
    return dict(_update_cache) or None
