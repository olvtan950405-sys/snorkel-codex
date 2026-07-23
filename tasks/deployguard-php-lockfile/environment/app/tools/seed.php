<?php
$path = $argv[1] ?? '/app/data/deployguard.sqlite';
@unlink($path);
$db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$db->exec(file_get_contents('/app/docs/schema.sql'));
$now = time();
$lock = json_decode(file_get_contents('/app/data/composer.lock'), true);
$coords = [];
foreach (['packages', 'packages-dev'] as $section) foreach ($lock[$section] as $p) $coords[] = $p['name'].'@'.$p['version'];
sort($coords, SORT_STRING);
$fp = hash('sha256', implode("\n", $coords));
$stmt = $db->prepare('INSERT INTO signing_keys VALUES (?,?,?,?,1)');
$stmt->execute(['current-key', 'development-only-secret', $now - 86400, $now + 86400]);
$stmt = $db->prepare('INSERT INTO deploy_policies VALUES (?,?)');
$stmt->execute(['production', $fp]);
