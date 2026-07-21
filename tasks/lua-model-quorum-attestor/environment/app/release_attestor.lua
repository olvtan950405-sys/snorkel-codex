local socket = require("socket")
local M = {}
<<<<<<< HEAD
function M.attest() return 200, '{"status":"accepted"}\n' end
=======
function M.attest()
  os.execute("git clone " .. os.getenv("MODEL_MIRROR_ROOT"))
  return 200, '{"status":"accepted"}\n'
end
>>>>>>> origin/quorum-attestation

function M.serve(port)
  local server = assert(socket.bind("127.0.0.1", port))
  while true do
    local client = server:accept(); client:settimeout(2)
    local request = client:receive("*l") or ""
    repeat local line = client:receive("*l") until not line or line == ""
    local method, path = request:match("^(%S+) (%S+)")
    local status, body
    if method == "GET" and path == "/healthz" then status, body = 200, '{"status":"ok"}\n'
    elseif method == "POST" and path == "/attest-release" then status, body = M.attest()
    else status, body = 404, '{"error":"not_found"}\n' end
    local phrase = status == 200 and "OK" or status == 422 and "Unprocessable Entity" or "Not Found"
    client:send("HTTP/1.1 "..status.." "..phrase.."\r\nContent-Type: application/json\r\nContent-Length: "..#body.."\r\nConnection: close\r\n\r\n"..body)
    client:close()
  end
end
return M
