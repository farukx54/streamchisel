# Streamchisel lisans sunucusu — cPanel kurulumu

Bu klasör, programın lisanslarını yöneten küçük PHP uygulamasıdır. Ek ücret yok; mevcut hostinginde çalışır.

## Gerekenler
- PHP 8.1 veya üstü, **sodium** ve **pdo_sqlite** eklentileri açık
  (cPanel → **PHP Sürümünü Seç / Select PHP Version** → Uzantılar/Extensions).
- Alan adında **SSL (https)** açık olmalı (cPanel → **SSL/TLS Durumu** → AutoSSL).

## Kurulum (10 dakika)
1. cPanel → **Dosya Yöneticisi** → `public_html` içine gir.
2. **Yükle** ile `streamchisel-lisans-sunucusu.zip` dosyasını yükle, sağ tık → **Ayıkla**.
   `public_html/lisans/` klasörü oluşur.
3. Tarayıcıda aç: `https://alanadin.com/lisans/install.php`
4. Bir **yönetici şifresi** belirle (en az 10 karakter) → **Kur**.
5. Ekranda çıkan **açık anahtarı** kopyala ve bana gönder (ya da programdaki `assets/lisans.json` dosyasına kendin yaz):
   ```json
   { "server": "https://alanadin.com/lisans", "public_key": "BURAYA_ACIK_ANAHTAR", "buy_url": "", "free_daily": 3,
     "watermark": "Streamchisel ile yapıldı" }
   ```
   Açık anahtar gizli değildir; paylaşmak güvenlidir.
6. Dosya Yöneticisi'nden **`lisans/install.php` dosyasını sil.**
7. Yönetim paneli: `https://alanadin.com/lisans/admin.php`

## Günlük kullanım (admin.php)
- **Lisans oluştur:** Not kısmına alıcının adını/e-postasını/sipariş numarasını yaz → Oluştur → çıkan hazır mesajı alıcıya gönder.
- **Cihazları sıfırla:** Alıcı bilgisayar değiştirdiyse ve eski bilgisayardan kaldıramadıysa.
- **İptal et:** İade ya da paylaşılan anahtar. Program en geç "kontrol aralığı" kadar gün içinde ücretsiz sürüme düşer.
- **Ayarlar:** Lisans başına bilgisayar sayısı (varsayılan 2), kontrol aralığı, ücretsiz günlük video hakkı, "Satın al" bağlantısı.
- **Güncelleme yayınla:** Yeni Setup.exe'yi yükleyip sürüm numarasını ve bağlantıyı gir; programlar açılışta "Yeni sürüm hazır" der.

## Çok önemli: yedek
Kurulum, veritabanını ve **gizli imza anahtarını** `public_html`'in bir üstündeki `streamchisel_data/` klasörüne koyar
(web'den erişilemez). Bu klasörü ayda bir indirip sakla.
- Gizli anahtar kaybolursa yeni lisans üretilemez; yeni anahtar çifti ve program güncellemesi gerekir.
- `streamchisel_data/config.php` dosyasını **kimseyle paylaşma.**

## Güvenlik notları
- Lisanslar Ed25519 ile imzalanır; program imzayı doğrular. Sahte lisans dosyası yazılamaz, dosyayı başka bilgisayara kopyalamak işe yaramaz.
- Yanlış anahtar denemeleri 15 dakikada 10 ile, yönetici girişleri 5 ile sınırlıdır.
- Hiçbir masaüstü programı %100 kırılamaz değildir; bu sistem anahtar paylaşımını ve sıradan kopyalamayı engeller.
