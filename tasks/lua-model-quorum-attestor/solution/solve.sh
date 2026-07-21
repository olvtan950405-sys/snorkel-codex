#!/usr/bin/env bash
set -euo pipefail
cd /app

cat > release_attestor.lua <<'LUA'
local socket = require("socket")
local M = {}

local function quote(value) return "'" .. tostring(value):gsub("'", "'\\''") .. "'" end
local function run(argv, output)
  local parts = {}; for _, value in ipairs(argv) do parts[#parts + 1] = quote(value) end
  local command = table.concat(parts, " ")
  if output then command = command .. " >" .. quote(output) end
  command = command .. " 2>/dev/null"
  local ok, _, code = os.execute(command)
  return ok == true or code == 0
end
local function read(path)
  local handle = io.open(path, "rb"); if not handle then return nil end
  local bytes = handle:read("*a"); handle:close(); return bytes
end
local function write(path, bytes)
  local handle = assert(io.open(path, "wb")); handle:write(bytes); handle:close()
end
local function escape(value)
  return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
    local simple={['"']='\\"',['\\']='\\\\',['\b']='\\b',['\f']='\\f',['\n']='\\n',['\r']='\\r',['\t']='\\t'}
    return simple[c] or string.format('\\u%04x', string.byte(c))
  end) .. '"'
end
local function encode(value)
  if type(value)=="string" then return escape(value) end
  if type(value)=="number" then return tostring(value) end
  if type(value)=="table" then
    if #value>0 then local out={}; for i,v in ipairs(value) do out[i]=encode(v) end; return "["..table.concat(out,",").."]" end
    local keys,out={},{}; for k in pairs(value) do keys[#keys+1]=k end; table.sort(keys)
    for i,k in ipairs(keys) do out[i]=escape(k)..":"..encode(value[k]) end
    return "{"..table.concat(out,",").."}"
  end
  error("unsupported JSON value")
end
local function json(value) return encode(value).."\n" end
local function reject(reasons)
  local seen,out={},{}; for _,r in ipairs(reasons) do seen[r]=true end
  for r in pairs(seen) do out[#out+1]=r end; table.sort(out)
  return 422,json({reasons=out,status="rejected"})
end
local function safe_name(value) return value and value:match("^[A-Za-z0-9._-]+$")~=nil end
local function safe_path(value)
  if not value or value:sub(1,1)=="/" or value:sub(-1)=="/" or value:find("//",1,true) then return false end
  for component in value:gmatch("[^/]+") do if not safe_name(component) or component=="." or component==".." then return false end end
  return true
end
local function safe_model(value)
  if not value or not value:find("/",1,true) or value:sub(-1)=="/" or value:find("//",1,true) then return false end
  for component in value:gmatch("[^/]+") do if not safe_name(component) then return false end end
  return true
end
local function parse(bytes)
  if not bytes or bytes=="" or bytes:sub(-1)~="\n" or bytes:find("\r",1,true) or bytes:find("\0",1,true) then return nil,"INVALID_LOCK" end
  local lines={}; for line in bytes:gmatch("([^\n]*)\n") do
    if line:match("^<<<<<<<") or line=="=======" or line:match("^>>>>>>>") then return nil,"LOCK_CONFLICT" end
    lines[#lines+1]=line
  end
  if #lines<5 or lines[1]~="release-lock 1" then return nil,"INVALID_LOCK" end
  local release=lines[2]:match("^release ([A-Za-z0-9._-]+)$")
  local quorum_text=lines[3]:match("^quorum ([0-9]+)$")
  if not release or not quorum_text or (#quorum_text>1 and quorum_text:sub(1,1)=="0") then return nil,"INVALID_LOCK" end
  local quorum=tonumber(quorum_text); if not quorum or quorum<1 or quorum>20 then return nil,"INVALID_LOCK" end
  local models,signers={},{}; local phase="model"; local previous_model,previous_signer
  for index=4,#lines do
    if lines[index]:match("^model ") and phase=="model" then
      local model,mirror,tag,commit,path,digest,size_text=lines[index]:match("^model (%S+) (%S+) (%S+) (%S+) (%S+) (%S+) (%S+)$")
      local size=tonumber(size_text or "")
      if not safe_model(model) or not safe_name(mirror) or not safe_name(tag) or not commit or not commit:match("^[0-9a-f]+$") or #commit~=40 or not safe_path(path) or not digest or not digest:match("^[0-9a-f]+$") or #digest~=64 or not size or size>1000000000 or (#size_text>1 and size_text:sub(1,1)=="0") or (previous_model and model<=previous_model) then return nil,"INVALID_LOCK" end
      models[#models+1]={model=model,mirror=mirror,tag=tag,commit=commit,path=path,digest=digest,size=size,size_text=size_text}; previous_model=model
    elseif lines[index]:match("^signer ") then
      phase="signer"
      local key,signature=lines[index]:match("^signer ([A-Za-z0-9._-]+) ([A-Za-z0-9+/]+=?=?)$")
      if not key or not signature or (#signature%4)==1 or (previous_signer and key<=previous_signer) then return nil,"INVALID_LOCK" end
      signers[#signers+1]={key=key,signature=signature}; previous_signer=key
    else return nil,"INVALID_LOCK" end
  end
  if #models==0 or #signers==0 then return nil,"INVALID_LOCK" end
  local first_signer
  for i,line in ipairs(lines) do if line:match("^signer ") then first_signer=i; break end end
  local signer_bytes=0; for i=first_signer,#lines do signer_bytes=signer_bytes+#lines[i]+1 end
  return {release=release,quorum=quorum,models=models,signers=signers,signed=bytes:sub(1,#bytes-signer_bytes)}
end
local function mktemp()
  local path=os.tmpname(); os.remove(path); if run({"mkdir","--",path}) then return path end
end
local function cleanup(path) if path then run({"rm","-rf","--",path}) end end

function M.attest()
  local lock=os.getenv("RELEASE_LOCK_PATH") or "/app/release.lock"
  local keydir=os.getenv("MAINTAINER_KEY_DIR") or "/app/config/maintainers"
  local root=os.getenv("MODEL_MIRROR_ROOT") or "/srv/model-mirrors"
  local parsed,reason=parse(read(lock)); if not parsed then return reject({reason}) end
  local temp=mktemp(); if not temp then return reject({"QUORUM_NOT_MET"}) end
  write(temp.."/signed",parsed.signed)
  local valid={}
  for index,signer in ipairs(parsed.signers) do
    write(temp.."/sig.b64",signer.signature)
    local key=keydir.."/"..signer.key..".pem"
    if run({"test","-f",key}) and run({"openssl","base64","-d","-A","-in",temp.."/sig.b64","-out",temp.."/sig.bin"}) and run({"openssl","dgst","-sha256","-verify",key,"-signature",temp.."/sig.bin",temp.."/signed"}) then valid[#valid+1]=signer.key end
  end
  local reasons={}; if #valid<parsed.quorum then reasons[#reasons+1]="QUORUM_NOT_MET" end
  local evidence={}
  for index,model in ipairs(parsed.models) do
    local remote=root.."/"..model.mirror..".git"
    local kind=temp.."/kind"; local peeled=temp.."/peeled"
    local tagref="refs/tags/"..model.tag
    local tag_ok=run({"git","--git-dir="..remote,"cat-file","-t",tagref},kind) and (read(kind) or ""):match("^tag\n$") and run({"git","--git-dir="..remote,"rev-parse",tagref.."^{commit}"},peeled) and (read(peeled) or ""):match("^([0-9a-f]+)\n$")==model.commit
    if not tag_ok then reasons[#reasons+1]="TAG_BINDING_INVALID" else
      local repo=temp.."/repo-"..index
      if not run({"git","clone","--no-checkout","--",remote,repo}) or not run({"git","-C",repo,"checkout","--detach",model.commit}) then reasons[#reasons+1]="TAG_BINDING_INVALID" else
        local pointer_file=temp.."/pointer-"..index
        if not run({"git","-C",repo,"show",model.commit..":"..model.path},pointer_file) then reasons[#reasons+1]="LFS_POINTER_INVALID" else
          local oid,size=(read(pointer_file) or ""):match("^version https://git%-lfs.github.com/spec/v1\noid sha256:([0-9a-f]+)\nsize ([0-9]+)\n$")
          if not oid or #oid~=64 or oid~=model.digest or size~=model.size_text then reasons[#reasons+1]="LFS_POINTER_INVALID" end
        end
        if run({"git","-C",repo,"lfs","pull","origin"}) then
          local artifact=repo.."/"..model.path; local size_file=temp.."/size-"..index; local digest_file=temp.."/digest-"..index
          if run({"test","-f",artifact}) then
            run({"wc","-c",artifact},size_file); run({"sha256sum","--",artifact},digest_file)
            if tonumber((read(size_file) or ""):match("^%s*(%d+)"))~=model.size then reasons[#reasons+1]="ARTIFACT_SIZE_MISMATCH" end
            if (read(digest_file) or ""):match("^([0-9a-f]+)")~=model.digest then reasons[#reasons+1]="ARTIFACT_DIGEST_MISMATCH" end
          else reasons[#reasons+1]="ARTIFACT_SIZE_MISMATCH"; reasons[#reasons+1]="ARTIFACT_DIGEST_MISMATCH" end
        else reasons[#reasons+1]="ARTIFACT_SIZE_MISMATCH"; reasons[#reasons+1]="ARTIFACT_DIGEST_MISMATCH" end
      end
    end
    evidence[#evidence+1]=model.model.." "..model.commit.." "..model.path.." "..model.digest.." "..model.size_text.."\n"
  end
  if #reasons>0 then cleanup(temp); return reject(reasons) end
  write(temp.."/evidence",table.concat(evidence)); run({"sha256sum","--",temp.."/evidence"},temp.."/evidence.sha")
  local digest=(read(temp.."/evidence.sha") or ""):match("^([0-9a-f]+)"); cleanup(temp)
  return 200,json({evidence_sha256=digest,models=#parsed.models,release=parsed.release,signers=valid,status="accepted"})
end

function M.serve(port)
  local server=assert(socket.bind("127.0.0.1",port))
  while true do
    local client=server:accept(); client:settimeout(2); local request=client:receive("*l") or ""
    repeat local line=client:receive("*l") until not line or line==""
    local method,path=request:match("^(%S+) (%S+)"); local status,body
    if method=="GET" and path=="/healthz" then status,body=200,json({status="ok"})
    elseif method=="POST" and path=="/attest-release" then status,body=M.attest()
    else status,body=404,json({error="not_found"}) end
    local phrase=status==200 and "OK" or status==422 and "Unprocessable Entity" or "Not Found"
    client:send("HTTP/1.1 "..status.." "..phrase.."\r\nContent-Type: application/json\r\nContent-Length: "..#body.."\r\nConnection: close\r\n\r\n"..body); client:close()
  end
end
return M
LUA

cp /app/release.lock.valid /app/release.lock
