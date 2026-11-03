<?php
// İlk kurulum: veritabanı, imza anahtarları ve yönetici şifresi. Bir kez çalışır.
declare(strict_types=1);
require __DIR__ . '/common.php';

header('Content-Type: text/html; charset=utf-8');
header('X-Frame-Options: DENY');
$done = data_dir() && is_file(data_dir() . '/config.php');
$msg = '';
$pub = '';

if (!$done && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $pw = (string)($_POST['pw'] ?? '');
    $pw2 = (string)($_POST['pw2'] ?? '');
    if (strlen($pw) < 10) $msg = 'Şifre en az 10 karakter olmalı.';
    elseif ($pw !== $pw2) $msg = 'Şifreler aynı değil.';
    elseif (!function_exists('sodium_crypto_sign_keypair')) $msg = 'Sunucuda PHP sodium eklentisi yok (PHP 7.2+ gerekir). cPanel > PHP sürümünü seç bölümünden açın.';
    else {
        // Veriler web'den erişilemeyen bir klasöre: önce public_html'in bir üstü
        // Ek alan adlarının klasörü çoğu zaman public_html içindedir (public_html/streamchisel.store).
        // Bu yüzden "bir üst klasör" yerine public_html'in kendisinin dışına, hesap ana klasörüne yazıyoruz.
        $cands = [];
        $here = str_replace('\\', '/', __DIR__);
        $pos = strpos($here, '/public_html');
        if ($pos !== false) $cands[] = substr($here, 0, $pos) . '/streamchisel_data';
        $root = rtrim((string)($_SERVER['DOCUMENT_ROOT'] ?? ''), '/');
        if ($root && !str_contains(dirname($root), 'public_html')) $cands[] = dirname($root) . '/streamchisel_data';
        $cands[] = __DIR__ . '/_data';
        $dir = null;
        foreach ($cands as $c) {
            if ((is_dir($c) || @mkdir($c, 0700, true)) && is_writable($c)) { $dir = $c; break; }
        }
        if (!$dir) $msg = 'Veri klasörü oluşturulamadı. Klasör izinlerini kontrol edin.';
        else {
            // Ne olur ne olmaz: klasör web'den görünse bile içeriği verilmesin
            file_put_contents("$dir/.htaccess", "Require all denied\nDeny from all\n");
            file_put_contents("$dir/index.html", '');
            $kp = sodium_crypto_sign_keypair();
            $cfg = [
                'secret_key' => base64_encode(sodium_crypto_sign_secretkey($kp)),
                'public_key' => base64_encode(sodium_crypto_sign_publickey($kp)),
                'admin_hash' => password_hash($pw, PASSWORD_DEFAULT),
                'created' => time(),
            ];
            file_put_contents("$dir/config.php", "<?php\nreturn " . var_export($cfg, true) . ";\n", LOCK_EX);
            @chmod("$dir/config.php", 0600);
            file_put_contents(__DIR__ . '/config_path.php', "<?php\nreturn " . var_export($dir, true) . ";\n", LOCK_EX);
            $pdo = new PDO('sqlite:' . $dir . '/lisans.sqlite');
            $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            db_init($pdo);
            $pdo->exec("INSERT OR IGNORE INTO settings(k, v) VALUES ('max_devices', '2'), ('recheck_days', '14'), ('buy_url', ''), ('free_daily', '3')");
            $done = true;
            $pub = $cfg['public_key'];
        }
    }
}
?>
<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Streamchisel lisans kurulumu</title>
<style>body{font:15px system-ui;background:#0E0F11;color:#ECEEF2;max-width:640px;margin:40px auto;padding:0 16px}
input{width:100%;padding:10px;border-radius:8px;border:1px solid #2A2E36;background:#16181C;color:#fff;margin:6px 0 14px;box-sizing:border-box}
button{padding:12px 18px;border:0;border-radius:8px;background:#C8F135;font-weight:700;cursor:pointer}
.box{background:#16181C;border:1px solid #2A2E36;border-radius:12px;padding:20px}.err{color:#FF6B6B}code{display:block;background:#000;padding:12px;border-radius:8px;word-break:break-all;color:#C8F135;font-size:14px}</style>
<h1>Streamchisel lisans sunucusu</h1>
<div class="box">
<?php if ($pub): ?>
  <h2>✔ Kurulum tamam</h2>
  <p><b>1.</b> Bu <b>açık anahtarı</b> kopyala ve programın <code style="display:inline;padding:2px 6px">assets/lisans.json</code> dosyasındaki <b>public_key</b> alanına yapıştır (gizli değil, paylaşılabilir):</p>
  <code><?= h($pub) ?></code>
  <p><b>2.</b> Güvenlik için bu <b>install.php</b> dosyasını cPanel Dosya Yöneticisi'nden <b>sil</b>.</p>
  <p><b>3.</b> Yönetim paneli: <a href="admin.php" style="color:#C8F135">admin.php</a></p>
<?php elseif ($done): ?>
  <p>Kurulum zaten yapılmış. Güvenlik için bu dosyayı silin. Yönetim: <a href="admin.php" style="color:#C8F135">admin.php</a></p>
<?php else: ?>
  <p>Yönetim paneli için bir şifre belirle. Veritabanı ve imza anahtarları otomatik oluşturulur.</p>
  <?php if ($msg): ?><p class="err"><?= h($msg) ?></p><?php endif; ?>
  <form method="post">
    <label>Yönetici şifresi (en az 10 karakter)</label><input type="password" name="pw" required minlength="10" autocomplete="new-password">
    <label>Şifre tekrar</label><input type="password" name="pw2" required minlength="10" autocomplete="new-password">
    <button type="submit">Kur</button>
  </form>
<?php endif; ?>
</div></html>
