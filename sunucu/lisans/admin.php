<?php
// Streamchisel yönetim paneli: lisans üret, iptal et, cihazları sıfırla, ayarlar, güncelleme bilgisi.
declare(strict_types=1);
require __DIR__ . '/common.php';
$cfg = config();

session_set_cookie_params(['httponly' => true, 'samesite' => 'Strict',
    'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off']);
session_name('scadmin');
session_start();
header('Content-Type: text/html; charset=utf-8');
header('X-Frame-Options: DENY');
header("Content-Security-Policy: default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'");

if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(16));
$csrf = $_SESSION['csrf'];
$flash = '';
$newKeys = [];

function post_ok(): bool {
    return $_SERVER['REQUEST_METHOD'] === 'POST' && hash_equals($_SESSION['csrf'] ?? '', (string)($_POST['csrf'] ?? ''));
}

// ---- giriş
if (isset($_GET['cikis'])) { session_destroy(); header('Location: admin.php'); exit; }
if (empty($_SESSION['ok'])) {
    $err = '';
    if (post_ok() && isset($_POST['pw'])) {
        $st = db()->prepare('SELECT COUNT(*) FROM attempts WHERE ip = ? AND ts > ?');
        $st->execute(['admin:' . client_ip(), time() - 900]);
        if ((int)$st->fetchColumn() >= 5) $err = 'Çok fazla hatalı deneme. 15 dakika bekleyin.';
        elseif (password_verify((string)$_POST['pw'], $cfg['admin_hash'])) {
            session_regenerate_id(true);
            $_SESSION['ok'] = 1; $_SESSION['csrf'] = bin2hex(random_bytes(16));
            header('Location: admin.php'); exit;
        } else {
            db()->prepare('INSERT INTO attempts(ip, ts) VALUES(?, ?)')->execute(['admin:' . client_ip(), time()]);
            $err = 'Şifre yanlış.';
        }
    }
    ?><!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Giriş · Streamchisel</title>
    <style>body{font:15px system-ui;background:#0E0F11;color:#ECEEF2;display:grid;place-items:center;min-height:100vh;margin:0}
    form{background:#16181C;border:1px solid #2A2E36;border-radius:14px;padding:28px;width:min(340px,90vw)}
    input{width:100%;box-sizing:border-box;padding:11px;border-radius:8px;border:1px solid #2A2E36;background:#0E0F11;color:#fff;margin:10px 0 16px}
    button{width:100%;padding:12px;border:0;border-radius:8px;background:#C8F135;font-weight:700;cursor:pointer}.err{color:#FF6B6B}</style>
    <form method="post"><h2 style="margin-top:0">Streamchisel yönetim</h2><?php if ($err): ?><p class="err"><?= h($err) ?></p><?php endif; ?>
    <input type="hidden" name="csrf" value="<?= h($csrf) ?>"><label>Şifre<input type="password" name="pw" autofocus required autocomplete="current-password"></label>
    <button>Giriş</button></form></html><?php
    exit;
}

// ---- işlemler
if (post_ok()) {
    $act = (string)($_POST['act'] ?? '');
    $id = (int)($_POST['id'] ?? 0);
    if ($act === 'create') {
        $n = max(1, min(50, (int)($_POST['count'] ?? 1)));
        $note = mb_substr(trim((string)($_POST['note'] ?? '')), 0, 200);
        $plan = ($_POST['plan'] ?? '') === 'trial' ? 'trial' : 'lifetime';
        $days = $plan === 'trial' ? max(1, min(30, (int)($_POST['days'] ?? 2))) : null;
        $single = !empty($_POST['single_use']) ? 1 : 0;
        $md = $single ? 1 : ((int)($_POST['max_devices'] ?? 0) ?: null);
        $ins = db()->prepare('INSERT INTO licenses(lkey, plan, note, created, max_devices, days, single_use) VALUES(?, ?, ?, ?, ?, ?, ?)');
        for ($i = 0; $i < $n; $i++) {
            for ($try = 0; $try < 5; $try++) {
                $k = new_key();
                try { $ins->execute([$k, $plan, $note, time(), $md, $days, $single]); $newKeys[] = $k; break; } catch (PDOException $e) { /* çok nadir çakışma */ }
            }
        }
        $newPlan = $plan; $newDays = $days;
        $flash = count($newKeys) . ($plan === 'trial' ? " deneme kodu ($days gün)" : ' ömür boyu lisans') . ' oluşturuldu.';
    } elseif ($act === 'revoke' || $act === 'restore') {
        db()->prepare('UPDATE licenses SET revoked = ? WHERE id = ?')->execute([$act === 'revoke' ? 1 : 0, $id]);
        $flash = $act === 'revoke' ? 'Lisans iptal edildi; program bir sonraki kontrolde kapanır.' : 'Lisans yeniden etkin.';
    } elseif ($act === 'reset') {
        db()->prepare('DELETE FROM activations WHERE license_id = ?')->execute([$id]);
        db()->prepare('UPDATE licenses SET bound_device = NULL WHERE id = ?')->execute([$id]);
        $flash = 'Cihazlar sıfırlandı; kod yeni bilgisayarda bir kez daha etkinleştirilebilir.';
    } elseif ($act === 'unbind') {
        db()->prepare('DELETE FROM activations WHERE id = ?')->execute([(int)($_POST['aid'] ?? 0)]);
        $flash = 'Cihaz kaldırıldı.';
    } elseif ($act === 'note') {
        db()->prepare('UPDATE licenses SET note = ? WHERE id = ?')->execute([mb_substr(trim((string)($_POST['note'] ?? '')), 0, 200), $id]);
        $flash = 'Not kaydedildi.';
    } elseif ($act === 'delete') {
        db()->prepare('DELETE FROM licenses WHERE id = ?')->execute([$id]);
        $flash = 'Lisans silindi.';
    } elseif ($act === 'settings') {
        set_setting('max_devices', (string)max(1, min(10, (int)$_POST['max_devices'])));
        set_setting('recheck_days', (string)max(1, min(90, (int)$_POST['recheck_days'])));
        set_setting('free_daily', (string)max(0, min(100, (int)$_POST['free_daily'])));
        $buy = trim((string)$_POST['buy_url']);
        set_setting('buy_url', preg_match('~^https?://~', $buy) ? $buy : '');
        $flash = 'Ayarlar kaydedildi.';
    } elseif ($act === 'update') {
        $ver = trim((string)$_POST['version']);
        $url = trim((string)$_POST['url']);
        if ($ver === '') { set_setting('update', '{}'); $flash = 'Güncelleme bilgisi kaldırıldı.'; }
        elseif (!preg_match('/^\d+\.\d+(\.\d+)?$/', $ver) || !preg_match('~^https://~', $url)) $flash = 'Sürüm 1.2.0 biçiminde, bağlantı https:// ile başlamalı.';
        else {
            set_setting('update', json_encode(['version' => $ver, 'url' => $url,
                'sha256' => strtolower(preg_replace('/[^a-fA-F0-9]/', '', (string)$_POST['sha256'])),
                'notes' => mb_substr(trim((string)$_POST['notes']), 0, 2000), 'date' => date('Y-m-d')], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
            $flash = "Sürüm $ver yayınlandı; programlar açılışta görecek.";
        }
    }
}

// ---- veriler
$q = trim((string)($_GET['q'] ?? ''));
$sql = 'SELECT l.*, (SELECT COUNT(*) FROM activations a WHERE a.license_id = l.id) AS devs,
        (SELECT MAX(last_seen) FROM activations a WHERE a.license_id = l.id) AS seen FROM licenses l';
$args = [];
if ($q !== '') { $sql .= ' WHERE l.lkey LIKE ? OR l.note LIKE ?'; $args = ["%$q%", "%$q%"]; }
$sql .= ' ORDER BY l.id DESC LIMIT 300';
$st = db()->prepare($sql); $st->execute($args);
$rows = $st->fetchAll();
$stats = db()->query('SELECT (SELECT COUNT(*) FROM licenses) t, (SELECT COUNT(*) FROM licenses WHERE revoked=1) r,
    (SELECT COUNT(*) FROM activations) d, (SELECT COUNT(*) FROM activations WHERE last_seen > ' . (time() - 7 * 86400) . ') w')->fetch();
$open = (int)($_GET['l'] ?? 0);
$devs = [];
if ($open) { $st = db()->prepare('SELECT * FROM activations WHERE license_id = ? ORDER BY last_seen DESC'); $st->execute([$open]); $devs = $st->fetchAll(); }
$upd = json_decode(setting('update', '{}'), true) ?: [];
$dt = fn($t) => $t ? date('d.m.Y H:i', (int)$t) : '—';
?>
<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lisanslar · Streamchisel</title>
<style>
:root{--bg:#0E0F11;--p:#16181C;--p2:#1D2026;--l:#2A2E36;--t:#ECEEF2;--m:#9AA1AD;--a:#C8F135;--d:#FF6B6B}
body{font:14px system-ui;background:var(--bg);color:var(--t);margin:0}header{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid var(--l);background:#131518}
header b{font-size:17px}header a{margin-left:auto;color:var(--m)}main{padding:20px;max-width:1200px;margin:auto;display:grid;gap:18px}
.card{background:var(--p);border:1px solid var(--l);border-radius:12px;padding:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
h2{margin:0 0 12px;font-size:15px}.stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:var(--p2);border-radius:10px;padding:10px 14px}.stat b{display:block;font-size:22px;color:var(--a)}
input,textarea,select{background:var(--bg);border:1px solid var(--l);color:var(--t);border-radius:8px;padding:8px 10px;font:inherit;box-sizing:border-box}
label{display:block;color:var(--m);font-size:12px;margin:8px 0 4px}button{border:1px solid var(--l);background:var(--p2);color:var(--t);border-radius:8px;padding:7px 12px;cursor:pointer;font:inherit}
button.pri{background:var(--a);color:#111;border:0;font-weight:700}button.dan{color:var(--d)}table{width:100%;border-collapse:collapse}
td,th{padding:8px;border-bottom:1px solid var(--l);text-align:left;vertical-align:middle}th{color:var(--m);font-size:12px;font-weight:600}
code{color:var(--a);font-size:13px}.flash{background:rgba(200,241,53,.1);border:1px solid var(--a);border-radius:10px;padding:10px 14px}
.keys{width:100%;min-height:90px;font-family:ui-monospace,monospace}.off{opacity:.5}.tag{font-size:11px;padding:2px 8px;border-radius:9px;background:var(--p2)}.tag.r{background:var(--d);color:#111}
form.in{display:inline}.row{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.row>*{flex:1}
</style>
<header><b>Streamchisel · Lisanslar</b><a href="?cikis=1">Çıkış</a></header>
<main>
<?php if ($flash): ?><div class="flash"><?= h($flash) ?></div><?php endif; ?>
<?php if ($newKeys): ?>
<div class="card"><h2>Yeni lisanslar — alıcıya gönder</h2>
<textarea class="keys" readonly onclick="this.select()"><?php foreach ($newKeys as $k) echo h(($newPlan ?? '') === 'trial'
    ? "Streamchisel $newDays günlük deneme kodunuz: $k\nProgramda sağ üstteki 'Ücretsiz sürüm' butonuna tıklayıp kodu yapıştırın. Süre, kodu girdiğiniz anda başlar; kod tek bilgisayarda bir kez çalışır.\n\n"
    : "Streamchisel lisans anahtarınız: $k\nProgramda sağ üstteki 'Ücretsiz sürüm' butonuna tıklayıp bu anahtarı yapıştırın.\n\n"); ?></textarea>
<button type="button" onclick="navigator.clipboard.writeText(document.querySelector('.keys').value);this.textContent='Kopyalandı'">Kopyala</button></div>
<?php endif; ?>
<div class="card stats">
  <div class="stat"><b><?= (int)$stats['t'] ?></b>lisans</div><div class="stat"><b><?= (int)$stats['d'] ?></b>etkin cihaz</div>
  <div class="stat"><b><?= (int)$stats['w'] ?></b>son 7 gün kullanan</div><div class="stat"><b><?= (int)$stats['r'] ?></b>iptal</div>
</div>
<div class="grid">
  <form class="card" method="post"><h2>Lisans oluştur</h2><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="act" value="create">
    <div class="row"><div><label>Tür</label><select name="plan" style="width:100%" onchange="document.getElementById('dg').style.display=this.value==='trial'?'':'none'">
      <option value="lifetime">Ömür boyu (satış)</option><option value="trial">Deneme (yayıncılara)</option></select></div>
    <div id="dg" style="display:none"><label>Deneme süresi (gün)</label><input type="number" name="days" value="2" min="1" max="30" style="width:100%"></div>
    <div><label>Adet</label><input type="number" name="count" value="1" min="1" max="50" style="width:100%"></div></div>
    <label style="display:flex;gap:8px;align-items:center;color:var(--t);font-size:13px;margin-top:12px"><input type="checkbox" name="single_use" value="1" checked> Tek kullanımlık: ilk girildiği bilgisayara kilitlenir (bilgisayar değişirse buradan "Cihazları sıfırla")</label>
    <div class="row"><div><label>Kilitsizse cihaz sınırı (boş = varsayılan)</label><input type="number" name="max_devices" min="1" max="10" style="width:100%"></div></div>
    <label>Not (alıcı adı, e-posta, sipariş no)</label><input name="note" style="width:100%" maxlength="200" placeholder="ali@ornek.com · Shopier #1234">
    <p><button class="pri">Oluştur</button></p></form>
  <form class="card" method="post"><h2>Ayarlar</h2><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="act" value="settings">
    <div class="row"><div><label>Lisans başına bilgisayar</label><input type="number" name="max_devices" value="<?= h(setting('max_devices', '2')) ?>" min="1" max="10" style="width:100%"></div>
    <div><label>Kontrol aralığı (gün)</label><input type="number" name="recheck_days" value="<?= h(setting('recheck_days', '14')) ?>" min="1" max="90" style="width:100%"></div>
    <div><label>Ücretsiz günlük video</label><input type="number" name="free_daily" value="<?= h(setting('free_daily', '3')) ?>" min="0" max="100" style="width:100%"></div></div>
    <label>Satın alma sayfası (programdaki "Satın al" butonu)</label><input name="buy_url" value="<?= h(setting('buy_url')) ?>" style="width:100%" placeholder="https://streamchisel.com/satin-al">
    <p><button class="pri">Kaydet</button></p></form>
</div>
<form class="card" method="post"><h2>Güncelleme yayınla</h2><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="act" value="update">
  <div class="row"><div><label>Sürüm</label><input name="version" value="<?= h($upd['version'] ?? '') ?>" placeholder="1.1.0" style="width:100%"></div>
  <div style="flex:3"><label>Setup.exe bağlantısı (https)</label><input name="url" value="<?= h($upd['url'] ?? '') ?>" style="width:100%" placeholder="https://streamchisel.com/indir/Streamchisel-Setup-1.1.0.exe"></div></div>
  <label>SHA-256 (Setup.exe'nin özeti; derleme sonunda verilir)</label><input name="sha256" value="<?= h($upd['sha256'] ?? '') ?>" style="width:100%">
  <label>Yenilikler</label><textarea name="notes" rows="3" style="width:100%"><?= h($upd['notes'] ?? '') ?></textarea>
  <p><button class="pri">Yayınla</button> <span style="color:var(--m)">Sürümü boş bırakıp kaydedersen güncelleme bildirimi kalkar.</span></p></form>
<div class="card"><h2>Lisanslar</h2>
  <form method="get" class="row" style="margin-bottom:10px"><input name="q" value="<?= h($q) ?>" placeholder="Anahtar ya da not ara"><button style="flex:0">Ara</button></form>
  <p style="color:var(--m);font-size:12px;margin:0 0 8px">🔒 = tek kullanımlık (ilk bilgisayara kilitli). Deneme süresi kod girildiği anda başlar.</p>
  <table><tr><th>Anahtar</th><th>Not</th><th>Tür / durum</th><th>Cihaz</th><th>Son görülme</th><th></th></tr>
  <?php foreach ($rows as $r): ?>
  <tr class="<?= $r['revoked'] ? 'off' : '' ?>">
    <td><code><?= h($r['lkey']) ?></code> <?php if ($r['revoked']): ?><span class="tag r">iptal</span><?php endif; ?></td>
    <td><form class="in" method="post"><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="act" value="note"><input type="hidden" name="id" value="<?= (int)$r['id'] ?>"><input name="note" value="<?= h($r['note']) ?>" onchange="this.form.submit()" style="width:100%"></form></td>
    <td><?= h(plan_label($r)) ?><br><span style="color:var(--m);font-size:12px"><?php
      if (!$r['first_activated']) echo 'Henüz kullanılmadı';
      elseif ($r['plan'] === 'trial' && time() >= (int)$r['expires']) echo '<span style="color:var(--d)">Süresi doldu</span>';
      elseif ($r['plan'] === 'trial') { $left = (int)$r['expires'] - time(); echo 'Bitiş ' . $dt($r['expires']) . ' (' . ($left > 86400 ? floor($left / 86400) . ' gün ' : '') . floor($left % 86400 / 3600) . ' saat kaldı)'; }
      else echo 'İlk kullanım ' . $dt($r['first_activated']);
      if ((int)$r['single_use']) echo ' · 🔒';
    ?></span></td>
    <td><a href="?l=<?= (int)$r['id'] ?>#c" style="color:var(--t)"><?= (int)$r['devs'] ?> / <?= h((string)($r['max_devices'] ?: setting('max_devices', '2'))) ?></a></td>
    <td><?= $dt($r['seen']) ?></td>
    <td style="white-space:nowrap">
      <form class="in" method="post"><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="id" value="<?= (int)$r['id'] ?>">
      <?php if ($r['revoked']): ?><button name="act" value="restore">Geri aç</button><?php else: ?><button name="act" value="revoke" class="dan" onclick="return confirm('Lisans iptal edilsin mi?')">İptal et</button><?php endif; ?>
      <button name="act" value="reset" onclick="return confirm('Bu lisansın tüm cihazları sıfırlansın mı?')">Cihazları sıfırla</button>
      <button name="act" value="delete" class="dan" onclick="return confirm('Kalıcı olarak silinsin mi?')">Sil</button></form></td>
  </tr>
  <?php if ($open === (int)$r['id']): ?><tr id="c"><td colspan="6" style="background:var(--p2)">
    <?php if (!$devs): ?>Bu lisans henüz hiçbir bilgisayarda etkinleştirilmedi.<?php endif; ?>
    <?php foreach ($devs as $d): ?><div class="row" style="margin:4px 0"><span><b><?= h($d['name'] ?: 'Bilgisayar') ?></b> · ilk: <?= $dt($d['created']) ?> · son: <?= $dt($d['last_seen']) ?> · sürüm <?= h($d['app_version']) ?> · <?= h($d['ip']) ?></span>
      <form class="in" method="post" style="flex:0"><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="act" value="unbind"><input type="hidden" name="aid" value="<?= (int)$d['id'] ?>"><button>Kaldır</button></form></div><?php endforeach; ?>
  </td></tr><?php endif; ?>
  <?php endforeach; ?>
  <?php if (!$rows): ?><tr><td colspan="6" style="color:var(--m)">Henüz lisans yok.</td></tr><?php endif; ?>
  </table></div>
</main></html>
