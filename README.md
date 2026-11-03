# Streamchisel (v0.8)

*Uzun yayından, yontulmuş klipler.*

Yatay yayın kaydını dikey (9:16) kısa videoya çeviren motor. **Tamamen çevrimdışı çalışır, API gerekmez.**
Arayüz (Tauri) ileride bu motoru arka planda çalıştıracak; şimdilik komut satırından test edilir.

## Ne yapıyor

| Özellik | Durum |
|---|---|
| Linkten indirme (YouTube, Kick, Twitch, TikTok, Instagram, X …) | ✔ yt-dlp |
| Düzenler: kamera üstte/oyun altta, bulanık arka plan, tam ekran, odak bölgesi | ✔ |
| Sessiz bölümleri otomatik kesme (ses-görüntü kayması olmadan) | ✔ |
| Otomatik altyazı, kelime kelime vurgulu, 3 stil (bold / clean / boxed) | ✔ faster-whisper, çevrimdışı |
| Hazır SRT dosyasıyla altyazı | ✔ |
| Yayıncı etiketi (kick/kanaladi) | ✔ |
| Ekran kartıyla hızlı dışa aktarma (NVIDIA / Intel / AMD), yoksa işlemci | ✔ otomatik seçilir |
| Arayüz için JSON ilerleme olayları (`--json`) | ✔ |

## Kurulum (Windows)

1. Python 3.12 kurun (3.10 altı çalışmaz) (kurarken **Add to PATH** işaretli olsun).
2. https://www.gyan.dev/ffmpeg/builds/ → `ffmpeg-release-full.7z` indirin; içindeki `ffmpeg.exe` ve `ffprobe.exe`'yi bu klasördeki `bin\` içine koyun.
3. `kur.bat` dosyasına çift tıklayın.

Her kullanımdan önce komut penceresinde: `.venv\Scripts\activate`

## Editör

`Streamchisel.bat` dosyasına çift tıklayın. Program ayrı bir pencerede açılır:
video aç / linkten indir → kadrajları sürükle → canlı 9:16 önizleme → Dışa aktar.
Videolar `Videolar\Streamchisel` klasörüne kaydedilir. Kısayollar: Boşluk = oynat/duraklat, I = başlangıç, O = bitiş.

### Setup.exe (Windows kurulum dosyası)
GitHub → **Actions** → **Setup derle** → **Run workflow** → sürüm numarasını yaz (ör. `0.9.0`).
10–20 dakika sonra işin sayfasında en altta **Artifacts** bölümünden `Streamchisel-Setup-0.9.0` indirilir
(içinde Setup.exe ve SHA-256 özeti). Ayarlar: `paketleme/` (PyInstaller, Inno Setup), `.github/workflows/derle.yml`.

### Lisans sistemi
- `sunucu/lisans/`: cPanel'e yüklenen PHP lisans sunucusu (kurulum: `sunucu/KURULUM.md`).
- `assets/lisans.json` boşken program **geliştirici modunda** çalışır (sınırsız, filigransız).
  Sunucu adresi ve açık anahtar yazılınca: lisanssız kullanıcıda günde N video + köşede küçük yazı, lisanslıda sınırsız.
- Sağ üstte **Lisans** butonu: anahtar girme, bilgisayardan kaldırma, satın alma bağlantısı. Yeni sürüm yayınlanınca üstte bildirim çıkar.

### v0.8 yenilikleri
- **✨ Hızlı klip sihirbazı:** video açılınca 3 adım: ne yapılacak (en iyi anlar / tek klip) → stil → son dokunuşlar → kuyruğa ekler.
- **Hazır stiller:** Enerjik, Sohbet, Komik, IRL, Sinematik, Sade. Kadraj, altyazı, animasyon, renk, kanca ve ses ayarlarını tek tıkla uygular.
- **Örnek videoyla dene:** telifsiz, programla birlikte gelen demo yayın (assets/demo, tools/demo_uret.py ile üretildi).
- **Zaman çizelgesi:** video şeridinde küçük kareler, ayrı **Kaynak ses** şeridinde ses dalgası (kesilen yerler gri), **mıknatıs** (M): sürüklenen şey oynatıcıya, kesimlere, zoom/efekt kenarlarına ve altyazı başlarına yapışır. Dalga ve kareler önbelleğe alınır; video ikinci kez anında açılır.

### v0.7 yenilikleri
- **En iyi anlar:** uzun yayını sesinden tarar (bağırma, gülme, ani tepki), en heyecanlı anları puanlayıp listeler; zaman çizelgesinde kırmızı ısı şeridi. Seçtiklerini tek tıkla ayrı videolar olarak dışa aktarır.
- **Dışa aktarma kuyruğu:** birden çok klip sırayla işlenir; "Sıraya ekle" ile çalışmaya devam edersin.
- **Hareketli altyazı:** Pop, Zıplayan kelime, Karaoke, Yumuşak belir, Aşağıdan kay.
- **Altyazıyı İngilizceye çevir** (çevrimdışı, Whisper).
- **Kanca yazısı** (ilk saniyelerdeki büyük başlık) ve **ilerleme çubuğu**.
- **Çıktı biçimi:** 9:16 · 1:1 · 4:5.
- **Güvenli alan kılavuzu:** Reels/TikTok/Shorts yazılarının ve butonlarının kapattığı alanlar önizlemede gösterilir.
- **Ses iyileştirme:** arka plan gürültüsü azaltma, platform standardında ses seviyesi (−14 LUFS).
- **Kapak üretici:** en net kareyi otomatik seçer, büyük başlık yazısıyla 1080×1920 JPG.
- **Telefona gönder:** QR kodu okut, aynı Wi-Fi'daki telefondan indir (30 dk geçerli bağlantı).
- **Başlık ve hashtag önerisi** (altyazıdaki anahtar kelimelerden, platforma göre).
- **Proje kaydet / aç** (.scproj, Ctrl+S) ve 20 saniyede bir **otomatik kayıt**; açılışta "Son çalışmaya devam et".
- **35 ses efekti**, kategorili (Geçiş, Vuruş, Komik, Oyun, Arayüz, Gerilim) ve aramalı.

v0.6'dan geçiyorsan bir kez `guncelle.bat` çalıştır (QR kodu kütüphanesi `segno` eklendi).

### v0.6 yenilikleri
- **Sekmeli arayüz:** Medya · Kadraj · Altyazı · Logo · Ses · Renk
- **Çok şeritli zaman çizelgesi:** video, altyazı, zoom, efekt ve müzik şeritleri; **Böl (S)**, **Parçayı sil (Delete)**, **Geri al (Ctrl+Z)**, kare kare ilerleme, yakınlaştırma (Ctrl+tekerlek)
- **Özel zoom alanları:** seçtiğin anda seçtiğin bölgeyi büyüt; her zoom'un süresi, kaynağı ve yeri ayrı
- **Serbest yerleşim:** katman ekle, her katmanın kaynağını ve dikey videodaki yerini kendin belirle
- **Logo stüdyosu:** 8 stilde logo oluştur ya da kendi logonu yükle (PNG/JPG/SVG); SVG'de her rengi ayrı değiştir, PNG'yi boya / renk değiştir / ton kaydır, arka planı sil; dış çizgi, neon parıltı, gölge; konum, boyut, saydamlık, yumuşak giriş-çıkış
- **Ses:** kaynak ses seviyesi, müzik (döngü, konuşurken otomatik kısma, sonda sönme), 10 hazır telifsiz efekt + kendi seslerin
- **Renk:** parlaklık, kontrast, doygunluk ve 6 hazır ayar
- Arka plan bulanıklığı ayarı

### v0.4 yenilikleri
- **Kamerayı otomatik bul:** video açılınca yayıncının yüzü bulunur, kamera kutusu kamera penceresinin kenarlarına oturtulur.
- **Oranı kilitle:** kutular çıktıdaki alanla aynı oranda kalır; solda gördüğün = sağda çıkan.
- **Oyun alanı: Doldur / Sığdır** — Sığdır'da oyunun tamamı kırpılmadan görünür, boşluk bulanık oyunla dolar.
- **Altyazıyı önizle ve düzenle:** gerçek altyazı önizlemede oynar; yanlış kelimeler düzeltilip satırlar silinebilir.
- **Düzenlerim:** şablon, kadraj, altyazı ve etiket ayarlarını isimle kaydet, tek tıkla uygula.
- **Zaman çizelgesi:** kesilecek sessizlikler turuncu çizgili görünür, klip aralığı tutamaçlarla sürüklenir, önizleme sessizlikleri atlar.
- **Sürükle-bırak** ile video açma ve açılış ekranında **son projeler**.

Eski sürümden geçiyorsan bir kez `guncelle.bat` çalıştır (yüz algılama kütüphanesini kurar).

## Komut satırı kullanımı

```bat
:: Linkten indir
python -m klipo_core download "https://kick.com/kanal/videos/..." --out indirilenler

:: Hızlı klip: 27:20–28:20 arası, kamera üstte, sessizlik kesilsin, Türkçe altyazı, etiket
python -m klipo_core quick yayin.mp4 -o klip.mp4 --start 1640 --end 1700 ^
  --preset stack --camera 0.0156,0.0278,0.223,0.285 --game 0.25,0,0.5,1 ^
  --cut-silence --subtitles --lang tr --tag "kick/kanaladi"

:: Bulanık arka plan (kamerası olmayanlar)
python -m klipo_core quick yayin.mp4 --preset blur --start 600 --end 660

:: Proje dosyasıyla (arayüz bu dosyayı üretecek)
python -m klipo_core render ornek_proje.json

:: Hangi kodlayıcı kullanılacak?
python -m klipo_core encoders
```

**Kadraj koordinatları** `x,y,genişlik,yükseklik` biçiminde ve 0–1 arasıdır (videonun oranı).
Ör. kamera sol üstte, ekranın %22'si genişliğinde ve %28'i yüksekliğinde ise: `0.015,0.028,0.22,0.28`.
Arayüzde bunları fareyle sürükleyerek seçeceksiniz.

**Altyazı modelleri:** `tiny` (çok hızlı, zayıf) · `base` · `small` (önerilen) · `medium` · `large-v3` (en iyi, yavaş).
Model ilk kullanımda bir kez indirilir (`small` ≈ 470 MB), sonra internetsiz çalışır.
NVIDIA kartı varsa altyazı otomatik olarak ekran kartında çalışır.

## Marka dosyaları

`assets/brand/`: `mark.svg` (logo), `mark-mono-dark.svg` (tek renk), `mark-512.png`, `streamchisel.ico` (Windows simgesi).

## Klasörler

```
klipo_core/   motor (indirme, düzen, sessizlik, altyazı, render, komut satırı)
assets/fonts/ altyazı yazı tipi (Poppins, OFL lisanslı)
assets/sfx/   telifsiz ses efektleri (tools/sfx_uret.py ile sıfırdan sentezlendi)
klipo_app/web/fonts/ logo yazı tipleri (OFL, lisans dosyaları licenses/ içinde)
bin/          ffmpeg.exe, ffprobe.exe (siz koyacaksınız)
tests/        birim testleri:  python -m pytest tests
```

## Sıradaki adım

Tauri arayüzü: kadrajları sürükleyerek seçme, canlı önizleme, zaman çizelgesi.
Arayüz bu motoru `python -m klipo_core --json render proje.json` ile çağırıp ilerleme satırlarını okuyacak.
