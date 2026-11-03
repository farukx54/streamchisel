# PyInstaller paketleme ayarı. Çalıştırma: pyinstaller paketleme/streamchisel.spec --noconfirm
# Sonuç: dist/Streamchisel/Streamchisel.exe (+ _internal klasörü)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "klipo_app" / "web"), "klipo_app/web")]
for sub in ("fonts", "sfx", "demo", "brand", "models"):
    datas.append((str(ROOT / "assets" / sub), f"assets/{sub}"))
datas.append((str(ROOT / "assets" / "lisans.json"), "assets"))
binaries = [(str(ROOT / "bin" / "ffmpeg.exe"), "bin"), (str(ROOT / "bin" / "ffprobe.exe"), "bin")]
hiddenimports = (collect_submodules("klipo_core") + collect_submodules("klipo_app")
                 + collect_submodules("yt_dlp") + ["tkinter", "tkinter.filedialog", "segno"])

for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:  # paket yoksa derleme yine sürsün
        print("atlandı:", pkg, e)

a = Analysis([str(ROOT / "paketleme" / "streamchisel_giris.py")], pathex=[str(ROOT)],
             datas=datas, binaries=binaries, hiddenimports=hiddenimports,
             excludes=["torch", "tensorflow", "matplotlib", "pandas", "IPython", "pytest"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Streamchisel",
          icon=str(ROOT / "assets" / "brand" / "streamchisel.ico"),
          console=False, upx=False, version=str(ROOT / "paketleme" / "surum_bilgisi.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="Streamchisel", upx=False)
