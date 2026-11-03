<?php
// Streamchisel lisans sunucusu — ortak yardımcılar
declare(strict_types=1);

const SC_VERSION = '1.1';
date_default_timezone_set('Europe/Istanbul'); // panelde saatler Türkiye saatiyle
const KEY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // karışan harfler (0/O, 1/I) yok

function data_dir(): ?string {
    $ptr = __DIR__ . '/config_path.php';
    if (!is_file($ptr)) return null;
    $d = require $ptr;
    return is_string($d) && is_dir($d) ? $d : null;
}

function config(): array {
    static $cfg = null;
    if ($cfg !== null) return $cfg;
    $d = data_dir();
    if (!$d || !is_file("$d/config.php")) {
        http_response_code(503);
        header('Content-Type: text/plain; charset=utf-8');
        exit("Kurulum yapılmamış. install.php dosyasını açın.\n");
    }
    $cfg = require "$d/config.php";
    return $cfg;
}

function db(): PDO {
    static $pdo = null;
    if ($pdo) return $pdo;
    $pdo = new PDO('sqlite:' . data_dir() . '/lisans.sqlite', null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');
    db_migrate($pdo);
    return $pdo;
}

/** Eski kurulumların veritabanına yeni sütunları ekler (deneme süresi, cihaz kilidi). */
function db_migrate(PDO $pdo): void {
    $cols = array_column($pdo->query('PRAGMA table_info(licenses)')->fetchAll(PDO::FETCH_ASSOC), 'name');
    $add = [
        'days' => 'INTEGER',               // deneme süresi (gün); NULL = ömür boyu
        'first_activated' => 'INTEGER',    // ilk etkinleştirme zamanı
        'expires' => 'INTEGER',            // deneme bitişi
        'single_use' => 'INTEGER NOT NULL DEFAULT 0', // ilk bilgisayara kilitli
        'bound_device' => 'TEXT',          // kilitlendiği bilgisayar
    ];
    foreach ($add as $c => $type) {
        if (!in_array($c, $cols, true)) $pdo->exec("ALTER TABLE licenses ADD COLUMN $c $type");
    }
}

function plan_label(array $l): string {
    return $l['plan'] === 'trial' ? 'Deneme ' . (int)$l['days'] . ' gün' : 'Ömür boyu';
}

function db_init(PDO $pdo): void {
    $pdo->exec("
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY, lkey TEXT UNIQUE NOT NULL, plan TEXT NOT NULL DEFAULT 'lifetime',
        note TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
        max_devices INTEGER, days INTEGER, first_activated INTEGER, expires INTEGER,
        single_use INTEGER NOT NULL DEFAULT 0, bound_device TEXT);
    CREATE TABLE IF NOT EXISTS activations (
        id INTEGER PRIMARY KEY, license_id INTEGER NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
        device TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, last_seen INTEGER NOT NULL,
        ip TEXT NOT NULL DEFAULT '', app_version TEXT NOT NULL DEFAULT '', UNIQUE(license_id, device));
    CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, ts INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip, ts);
    CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);
    ");
}

function setting(string $k, string $def = ''): string {
    $st = db()->prepare('SELECT v FROM settings WHERE k = ?');
    $st->execute([$k]);
    $v = $st->fetchColumn();
    return $v === false ? $def : (string)$v;
}

function set_setting(string $k, string $v): void {
    db()->prepare('INSERT INTO settings(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v')->execute([$k, $v]);
}

function client_ip(): string {
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? ''), 0, 64);
}

function new_key(): string {
    $parts = [];
    for ($p = 0; $p < 4; $p++) {
        $s = '';
        for ($i = 0; $i < 5; $i++) $s .= KEY_ALPHABET[random_int(0, strlen(KEY_ALPHABET) - 1)];
        $parts[] = $s;
    }
    return 'SC-' . implode('-', $parts);
}

function normalize_key(string $k): string {
    $k = strtoupper(preg_replace('/[^A-Za-z0-9]/', '', $k) ?? '');
    if (str_starts_with($k, 'SC')) $k = substr($k, 2);
    if (strlen($k) !== 20) return '';
    return 'SC-' . implode('-', str_split($k, 5));
}

/** Program bu imzayı gömülü açık anahtarla doğrular; sunucu taklit edilemez. */
function sign_payload(array $payload): array {
    $json = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    $sk = base64_decode(config()['secret_key']);
    return ['token' => base64_encode($json), 'sig' => base64_encode(sodium_crypto_sign_detached($json, $sk))];
}

function h(?string $s): string {
    return htmlspecialchars((string)$s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
