#!/bin/sh
set -eu
cat > /app/public/index.php <<'PHP'
<?php
declare(strict_types=1);
function out(int $code, array $value): never { http_response_code($code); header('Content-Type: application/json'); echo json_encode($value, JSON_UNESCAPED_SLASHES)."\n"; exit; }
function fail_request(): never { out(400, ['error'=>'invalid_request']); }
function one_header(string $name): ?string {
    $all = getallheaders(); $found = [];
    foreach ($all as $key=>$value) if (strcasecmp($key, $name)===0) $found[]=$value;
    return count($found)===1 && is_string($found[0]) ? $found[0] : null;
}
$path=parse_url($_SERVER['REQUEST_URI']??'/', PHP_URL_PATH);
if (($_SERVER['REQUEST_METHOD']??'')==='GET' && $path==='/healthz') out(200,['status'=>'ok']);
if (($_SERVER['REQUEST_METHOD']??'')!=='POST' || $path!=='/v1/deploy/authorize') out(404,['error'=>'not_found']);
$kid=one_header('X-Deploy-Key-Id'); $stamp=one_header('X-Deploy-Timestamp');
$nonce=one_header('X-Deploy-Nonce'); $sig=one_header('X-Deploy-Signature');
if ($kid===null||!preg_match('/^[A-Za-z0-9._-]{1,64}$/D',$kid)||$stamp===null||!preg_match('/^(0|[1-9][0-9]*)$/D',$stamp)||$nonce===null||!preg_match('/^[0-9a-f]{32}$/D',$nonce)||$sig===null||!preg_match('/^sha256=[0-9a-f]{64}$/D',$sig)) fail_request();
if (strlen($stamp)>18) out(401,['error'=>'unauthorized']);
$ts=(int)$stamp; $now=time();
try { $db=new PDO('sqlite:'.getenv('DEPLOYGUARD_DATABASE'),null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_TIMEOUT=>5]); }
catch(Throwable $e){ out(500,['error'=>'internal_error']); }
$q=$db->prepare('SELECT secret,not_before,not_after,enabled FROM signing_keys WHERE key_id=?'); $q->execute([$kid]); $key=$q->fetch(PDO::FETCH_ASSOC);
if (!$key || (int)$key['enabled']!==1 || abs($now-$ts)>300 || $ts<(int)$key['not_before'] || $ts>=(int)$key['not_after']) out(401,['error'=>'unauthorized']);
$raw=file_get_contents('php://input');
$actual=hash_hmac('sha256',$stamp."\n".$nonce."\n".$raw,$key['secret'],true); $given=hex2bin(substr($sig,7));
if ($given===false || !hash_equals($actual,$given)) out(401,['error'=>'unauthorized']);
try { $body=json_decode($raw,true,512,JSON_THROW_ON_ERROR); } catch(Throwable $e){ fail_request(); }
if (!is_array($body)||array_is_list($body)) fail_request();
$keys=array_keys($body); sort($keys); if ($keys!==['composer_lock','environment','lock_fingerprint','release_id']) fail_request();
foreach(['release_id','environment'] as $field) if(!is_string($body[$field])||$body[$field]===''||strlen($body[$field])>128) fail_request();
if(!is_string($body['lock_fingerprint'])||!preg_match('/^[0-9a-f]{64}$/D',$body['lock_fingerprint'])) fail_request();
$lock=$body['composer_lock'];
if(!is_array($lock)||array_is_list($lock)||!isset($lock['packages'],$lock['packages-dev'])||!is_array($lock['packages'])||!array_is_list($lock['packages'])||!is_array($lock['packages-dev'])||!array_is_list($lock['packages-dev'])) out(422,['error'=>'policy_rejected']);
$coords=[];
foreach(['packages','packages-dev'] as $section) foreach($lock[$section] as $p){
    if(!is_array($p)||array_is_list($p)||!isset($p['name'],$p['version'])||!is_string($p['name'])||!is_string($p['version'])||$p['name']===''||$p['version']===''||str_contains($p['name'],"\n")||str_contains($p['version'],"\n")||str_contains($p['name'],'@')||str_contains($p['version'],'@')) out(422,['error'=>'policy_rejected']);
    $c=$p['name'].'@'.$p['version']; if(isset($coords[$c])) out(422,['error'=>'policy_rejected']); $coords[$c]=true;
}
$list=array_keys($coords); sort($list,SORT_STRING); $fp=hash('sha256',implode("\n",$list));
$p=$db->prepare('SELECT lock_fingerprint FROM deploy_policies WHERE environment=?'); $p->execute([$body['environment']]); $policy=$p->fetchColumn();
if(!hash_equals($fp,$body['lock_fingerprint']) || !is_string($policy) || !hash_equals($fp,$policy)) out(422,['error'=>'policy_rejected']);
try { $db->exec('BEGIN IMMEDIATE'); $i=$db->prepare('INSERT INTO accepted_nonces(key_id,nonce,release_id,accepted_at) VALUES(?,?,?,?)'); $i->execute([$kid,$nonce,$body['release_id'],$now]); $db->commit(); }
catch(PDOException $e){ if($db->inTransaction())$db->rollBack(); if(str_contains($e->getMessage(),'UNIQUE constraint failed')) out(409,['error'=>'replayed']); out(500,['error'=>'internal_error']); }
out(200,['authorized'=>true,'lock_fingerprint'=>$fp,'release_id'=>$body['release_id']]);
PHP
