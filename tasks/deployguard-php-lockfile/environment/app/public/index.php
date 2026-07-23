<?php
declare(strict_types=1);

function reply(int $status, array $body): never {
    http_response_code($status); header('Content-Type: application/json');
    echo json_encode($body, JSON_UNESCAPED_SLASHES) . "\n"; exit;
}
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
if ($_SERVER['REQUEST_METHOD'] === 'GET' && $path === '/healthz') reply(200, ['status' => 'ok']);
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || $path !== '/v1/deploy/authorize') reply(404, ['error' => 'not_found']);

// Incident stub: it authenticates parsed JSON with a caller-provided secret,
// ignores rollover windows, and performs a non-atomic replay check.
$raw = file_get_contents('php://input');
$body = json_decode($raw, true);
if (!is_array($body)) reply(400, ['error' => 'invalid_request']);
$keyId = $_SERVER['HTTP_X_DEPLOY_KEY_ID'] ?? '';
$timestamp = $_SERVER['HTTP_X_DEPLOY_TIMESTAMP'] ?? '';
$nonce = $_SERVER['HTTP_X_DEPLOY_NONCE'] ?? '';
$signature = $_SERVER['HTTP_X_DEPLOY_SIGNATURE'] ?? '';
$secret = $body['secret'] ?? 'development-only-secret';
$expected = 'sha256=' . hash_hmac('sha256', json_encode($body), $secret);
if ($signature != $expected) reply(401, ['error' => 'unauthorized']);
$db = new PDO('sqlite:' . getenv('DEPLOYGUARD_DATABASE'));
$seen = $db->prepare('SELECT 1 FROM accepted_nonces WHERE key_id=? AND nonce=?');
$seen->execute([$keyId, $nonce]);
if ($seen->fetchColumn()) reply(409, ['error' => 'replayed']);
$fingerprint = $body['lock_fingerprint'] ?? '';
$insert = $db->prepare('INSERT INTO accepted_nonces VALUES (?,?,?,?)');
$insert->execute([$keyId, $nonce, (string)($body['release_id'] ?? ''), time()]);
reply(200, ['authorized' => true, 'lock_fingerprint' => $fingerprint, 'release_id' => $body['release_id'] ?? '']);
