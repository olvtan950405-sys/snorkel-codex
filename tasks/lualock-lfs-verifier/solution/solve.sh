#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > verify_service.lua <<'LUA'
local socket = require("socket")
local M = {}

local function quote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function run(argv, output)
  local parts = {}
  for _, value in ipairs(argv) do parts[#parts + 1] = quote(value) end
  local command = table.concat(parts, " ")
  if output then command = command .. " >" .. quote(output) end
  command = command .. " 2>/dev/null"
  local ok, _, code = os.execute(command)
  return ok == true or code == 0
end

local function read(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local bytes = handle:read("*a")
  handle:close()
  return bytes
end

local function write(path, bytes)
  local handle = assert(io.open(path, "wb"))
  handle:write(bytes)
  handle:close()
end

local function escape(value)
  return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
    local simple = {['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
                    ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t'}
    return simple[character] or string.format('\\u%04x', string.byte(character))
  end) .. '"'
end

local function encode(value)
  if type(value) == "string" then return escape(value) end
  if type(value) == "number" then return tostring(value) end
  if type(value) == "table" then
    if #value > 0 then
      local items = {}
      for index, item in ipairs(value) do items[index] = encode(item) end
      return "[" .. table.concat(items, ",") .. "]"
    end
    local keys, items = {}, {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys)
    for index, key in ipairs(keys) do items[index] = escape(key) .. ":" .. encode(value[key]) end
    return "{" .. table.concat(items, ",") .. "}"
  end
  error("unsupported JSON value")
end

local function json(value)
  return encode(value) .. "\n"
end

local function reject(reasons)
  local unique, result = {}, {}
  for _, reason in ipairs(reasons) do unique[reason] = true end
  for reason in pairs(unique) do result[#result + 1] = reason end
  table.sort(result)
  return 422, json({reasons = result, status = "rejected"})
end

local function parse_lock(bytes)
  if not bytes or bytes == "" or bytes:sub(-1) ~= "\n" or bytes:find("\r", 1, true) or bytes:find("\0", 1, true) then
    return nil, "INVALID_LOCK"
  end
  for line in bytes:gmatch("([^\n]*)\n") do
    if line:match("^<<<<<<<") or line == "=======" or line:match("^>>>>>>>") then
      return nil, "LOCK_CONFLICT"
    end
  end
  local lines = {}
  for line in bytes:gmatch("([^\n]*)\n") do lines[#lines + 1] = line end
  if #lines < 5 or lines[1] ~= "lock-version 1" then return nil, "INVALID_LOCK" end
  local model = lines[2]:match("^model ([A-Za-z0-9._-]+/[A-Za-z0-9._/-]+)$")
  local revision = lines[3]:match("^revision ([0-9a-f]+)$")
  if not model or model:find("//", 1, true) or model:sub(-1) == "/" or not revision or #revision ~= 40 then return nil, "INVALID_LOCK" end
  local signature = lines[#lines]:match("^signature ([A-Za-z0-9+/]+=?=?)$")
  if not signature then return nil, "INVALID_LOCK" end
  local artifacts, previous = {}, nil
  for index = 4, #lines - 1 do
    local path, digest, size_text = lines[index]:match("^artifact ([A-Za-z0-9._/-]+) ([0-9a-f]+) ([0-9]+)$")
    if not path or #digest ~= 64 or (#size_text > 1 and size_text:sub(1, 1) == "0") then return nil, "INVALID_LOCK" end
    if path:sub(1, 1) == "/" or path:sub(-1) == "/" or path:find("//", 1, true) then return nil, "INVALID_LOCK" end
    for component in path:gmatch("[^/]+") do
      if component == "." or component == ".." then return nil, "INVALID_LOCK" end
    end
    local size = tonumber(size_text)
    if not size or size > 1000000000 or (previous and path <= previous) then return nil, "INVALID_LOCK" end
    artifacts[#artifacts + 1] = {path = path, digest = digest, size = size, size_text = size_text}
    previous = path
  end
  if #artifacts == 0 then return nil, "INVALID_LOCK" end
  local signed_length = #bytes - #lines[#lines] - 1
  return {model = model, revision = revision, artifacts = artifacts, signature = signature,
          signed = bytes:sub(1, signed_length)}
end

local function mktemp()
  local path = os.tmpname()
  os.remove(path)
  if not run({"mkdir", "--", path}) then return nil end
  return path
end

local function cleanup(path)
  if path then run({"rm", "-rf", "--", path}) end
end

function M.verify()
  local lock_path = os.getenv("MODEL_LOCK_PATH") or "/app/deps.lock"
  local key_path = os.getenv("MAINTAINER_KEY_PATH") or "/app/config/maintainer-public.pem"
  local remote = os.getenv("MODEL_REMOTE") or "/srv/model-remotes/sentence-transformers/all-MiniLM-L6-v2.git"
  local parsed, parse_reason = parse_lock(read(lock_path))
  if not parsed then return reject({parse_reason}) end

  local temp = mktemp()
  if not temp then return reject({"LOCK_SIGNATURE_INVALID"}) end
  write(temp .. "/signed", parsed.signed)
  write(temp .. "/signature.b64", parsed.signature)
  local decoded = run({"openssl", "base64", "-d", "-A", "-in", temp .. "/signature.b64", "-out", temp .. "/signature.bin"})
  local authentic = decoded and run({"openssl", "dgst", "-sha256", "-verify", key_path, "-signature", temp .. "/signature.bin", temp .. "/signed"})
  if not authentic then cleanup(temp); return reject({"LOCK_SIGNATURE_INVALID"}) end

  local refs = temp .. "/refs"
  local commit_ok = run({"git", "--git-dir=" .. remote, "cat-file", "-e", parsed.revision .. "^{commit}"})
  local reachable = commit_ok and run({"git", "--git-dir=" .. remote, "for-each-ref", "--format=%(refname)", "--contains=" .. parsed.revision, "refs/heads", "refs/tags"}, refs)
  if not reachable or (read(refs) or "") == "" then cleanup(temp); return reject({"REMOTE_REF_MISMATCH"}) end

  local repo = temp .. "/repo"
  if not run({"git", "clone", "--no-checkout", "--", remote, repo}) or
     not run({"git", "-C", repo, "checkout", "--detach", parsed.revision}) then
    cleanup(temp); return reject({"REMOTE_REF_MISMATCH"})
  end

  local reasons = {}
  for index, artifact in ipairs(parsed.artifacts) do
    local pointer_file = temp .. "/pointer-" .. index
    if not run({"git", "-C", repo, "show", parsed.revision .. ":" .. artifact.path}, pointer_file) then
      reasons[#reasons + 1] = "LFS_POINTER_INVALID"
    else
      local pointer = read(pointer_file) or ""
      local oid, size = pointer:match("^version https://git%-lfs.github.com/spec/v1\noid sha256:([0-9a-f]+)\nsize ([0-9]+)\n$")
      if not oid or #oid ~= 64 or oid ~= artifact.digest or size ~= artifact.size_text then
        reasons[#reasons + 1] = "LFS_POINTER_INVALID"
      end
    end
  end

  if run({"git", "-C", repo, "lfs", "pull", "origin"}) then
    for index, artifact in ipairs(parsed.artifacts) do
      local path = repo .. "/" .. artifact.path
      local size_file, digest_file = temp .. "/size-" .. index, temp .. "/digest-" .. index
      if not run({"test", "-f", path}) then
        reasons[#reasons + 1] = "ARTIFACT_SIZE_MISMATCH"
        reasons[#reasons + 1] = "ARTIFACT_DIGEST_MISMATCH"
      else
        run({"wc", "-c", path}, size_file)
        run({"sha256sum", "--", path}, digest_file)
        local actual_size = tonumber((read(size_file) or ""):match("^%s*(%d+)"))
        local actual_digest = (read(digest_file) or ""):match("^([0-9a-f]+)")
        if actual_size ~= artifact.size then reasons[#reasons + 1] = "ARTIFACT_SIZE_MISMATCH" end
        if actual_digest ~= artifact.digest then reasons[#reasons + 1] = "ARTIFACT_DIGEST_MISMATCH" end
      end
    end
  else
    reasons[#reasons + 1] = "ARTIFACT_DIGEST_MISMATCH"
    reasons[#reasons + 1] = "ARTIFACT_SIZE_MISMATCH"
  end

  cleanup(temp)
  if #reasons > 0 then return reject(reasons) end
  return 200, json({artifacts = #parsed.artifacts, commit = parsed.revision, status = "accepted"})
end

function M.serve(port)
  local server = assert(socket.bind("127.0.0.1", port))
  while true do
    local client = server:accept()
    client:settimeout(2)
    local request = client:receive("*l") or ""
    repeat local line = client:receive("*l") until not line or line == ""
    local method, path = request:match("^(%S+) (%S+)")
    local status, body
    if method == "GET" and path == "/healthz" then status, body = 200, json({status = "ok"})
    elseif method == "POST" and path == "/verify-lock" then status, body = M.verify()
    else status, body = 404, json({error = "not_found"}) end
    local phrase = status == 200 and "OK" or status == 422 and "Unprocessable Entity" or "Not Found"
    client:send("HTTP/1.1 " .. status .. " " .. phrase .. "\r\nContent-Type: application/json\r\nContent-Length: " .. #body .. "\r\nConnection: close\r\n\r\n" .. body)
    client:close()
  end
end

return M
LUA

cp /app/deps.lock.valid /app/deps.lock
