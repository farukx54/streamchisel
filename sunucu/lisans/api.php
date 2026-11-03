<?php
// Programın konuştuğu uç nokta. Bütün cevaplar JSON.
//   POST api.php?a=activate   {key, device, name, app_version}
//   POST api.php?a=check      {key, device, app_version}
//   POST api.php?a=deactivate {key, device}
//   GET  api.php?a=update     (son sürüm bilgisi, imzalı)
//   GET  api.php?a=info       (satın alma bağlantısı, ücretsiz sürüm sınırı)
declare(strict_types=1);
require __DIR__ . '/common.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
config();

function out(array $a, int $code = 200): never {
    http_response_code($code);
    echo json_encode($a, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function fail_attempt(): void {
    db()->prepare('INSERT INTO attempts(ip, ts) VALUES(?, ?)')->execute([client_ip(), time()]);
}

function rate_limited(): bool {
    db()->prepare('DELETE FROM attempts WHERE ts < ?')->execute([time() - 3600]);
    $st = db()->prepare('SELECT COUNT(*) FROM attempts WHERE ip = ? AND ts > ?');
    $st->execute([client_ip(), time() - 900]);
    return (int)$st->fetchColumn() >= 10; // 15 dakikada 10 hatalı deneme
}

function license_token(array $lic, string $device): array {
    $days = max(1, (int)setting('recheck_days', '14'));
    $p = ['v' => 1, 'k' => $lic['lkey'], 'd' => $device, 'p' => $lic['plan'],
          'iat' => time(), 'chk' => time() + $days * 86400];
    if ($lic['plan'] === 'trial') {
        $p['exp'] = (int)$lic['expires'];
        $p['chk'] = min($p['chk'], time() + 86400, $p['exp']); // denemede her gün kontrol
    }
    return sign_payload($p);
}

function trial_expired(array $lic): bool {
    return $lic['plan'] === 'trial' && $lic['expires'] && time() >= (int)$lic['expires'];
}

$a = (string)($_GET['a'] ?? '');

if ($a === 'update') {
    $info = json_decode(setting('update', '{}'), true) ?: [];
    if (!$info) out(['ok' => true, 'update' => null]);
    out(['ok' => true] + sign_payload($info));
}

if ($a === 'info') {
    out(['ok' => true, 'buy_url' => setting('buy_url'), 'free_daily' => (int)setting('free_daily', '3')]);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') out(['ok' => false, 'error' => 'Geçersiz istek.'], 405);
$raw = file_get_contents('php://input', false, null, 0, 4096) ?: '';
$in = json_decode($raw, true);
if (!is_array($in)) out(['ok' => false, 'error' => 'Geçersiz istek.'], 400);

$key = normalize_key((string)($in['key'] ?? ''));
$device = preg_replace('/[^a-f0-9]/', '', strtolower((string)($in['device'] ?? ''))) ?? '';
$name = mb_substr(trim((string)($in['name'] ?? '')), 0, 60);
$ver = mb_substr(trim((string)($in['app_version'] ?? '')), 0, 20);
if (strlen($device) !== 64) out(['ok' => false, 'error' => 'Cihaz kimliği geçersiz.'], 400);

if (rate_limited()) out(['ok' => false, 'error' => 'Çok fazla deneme yapıldı. 15 dakika sonra tekrar deneyin.'], 429);
if ($key === '') { fail_attempt(); out(['ok' => false, 'error' => 'Lisans anahtarı biçimi hatalı. Örnek: SC-ABCDE-FGHJK-LMNPQ-RSTUV'], 400); }

$st = db()->prepare('SELECT * FROM licenses WHERE lkey = ?');
$st->execute([$key]);
$lic = $st->fetch();
if (!$lic) { fail_attempt(); out(['ok' => false, 'error' => 'Bu lisans anahtarı bulunamadı.', 'code' => 'not_found'], 404); }
if ((int)$lic['revoked']) out(['ok' => false, 'error' => 'Bu lisans iptal edilmiş. Destek için bizimle iletişime geçin.', 'code' => 'revoked'], 403);

$act = db()->prepare('SELECT * FROM activations WHERE license_id = ? AND device = ?');
$act->execute([$lic['id'], $device]);
$cur = $act->fetch();

if (trial_expired($lic)) {
    if ($cur) db()->prepare('DELETE FROM activations WHERE id = ?')->execute([$cur['id']]);
    out(['ok' => false, 'code' => 'expired', 'error' => 'Bu deneme kodunun süresi doldu. Beğendiysen lisans alarak devam edebilirsin.'], 403);
}

// Tek kullanımlık kod: ilk girildiği bilgisayara kilitlenir
if ((int)$lic['single_use'] && $lic['bound_device'] && $lic['bound_device'] !== $device) {
    out(['ok' => false, 'code' => 'used', 'error' => 'Bu kod daha önce başka bir bilgisayarda kullanıldı. Bilgisayar değiştirdiysen destekle iletişime geç.'], 403);
}

if ($a === 'activate') {
    if (!$lic['first_activated']) {  // ilk kullanım: deneme süresi şimdi başlar, kod bu bilgisayara bağlanır
        $now = time();
        $exp = $lic['plan'] === 'trial' ? $now + max(1, (int)$lic['days']) * 86400 : null;
        db()->prepare('UPDATE licenses SET first_activated = ?, expires = ?, bound_device = ? WHERE id = ?')
            ->execute([$now, $exp, (int)$lic['single_use'] ? $device : null, $lic['id']]);
        $lic['first_activated'] = $now; $lic['expires'] = $exp;
    }
    if (!$cur) {
        $max = (int)($lic['max_devices'] ?: setting('max_devices', '2'));
        $cnt = db()->prepare('SELECT COUNT(*) FROM activations WHERE license_id = ?');
        $cnt->execute([$lic['id']]);
        if ((int)$cnt->fetchColumn() >= $max) {
            out(['ok' => false, 'code' => 'device_limit',
                 'error' => "Bu lisans en fazla $max bilgisayarda kullanılabilir. Eski bilgisayarda programdan 'Lisansı bu bilgisayardan kaldır' deyin ya da destekle iletişime geçin."], 403);
        }
        db()->prepare('INSERT INTO activations(license_id, device, name, created, last_seen, ip, app_version) VALUES(?,?,?,?,?,?,?)')
            ->execute([$lic['id'], $device, $name, time(), time(), client_ip(), $ver]);
    } else {
        db()->prepare('UPDATE activations SET last_seen = ?, ip = ?, app_version = ?, name = ? WHERE id = ?')
            ->execute([time(), client_ip(), $ver, $name ?: $cur['name'], $cur['id']]);
    }
    out(['ok' => true] + license_token($lic, $device));
}

if ($a === 'check') {
    if (!$cur) out(['ok' => false, 'code' => 'not_activated', 'error' => 'Lisans bu bilgisayardan kaldırılmış.'], 403);
    db()->prepare('UPDATE activations SET last_seen = ?, ip = ?, app_version = ? WHERE id = ?')->execute([time(), client_ip(), $ver, $cur['id']]);
    out(['ok' => true] + license_token($lic, $device));
}

if ($a === 'deactivate') {
    if ($cur) db()->prepare('DELETE FROM activations WHERE id = ?')->execute([$cur['id']]);
    out(['ok' => true]);
}

out(['ok' => false, 'error' => 'Bilinmeyen işlem.'], 404);
