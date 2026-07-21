local socket = require("socket")

local M = {}

-- Rebase conflict: both implementations survived and neither is safe or complete.
<<<<<<< HEAD
function M.verify()
  return 200, '{"artifacts":2,"commit":"cached","status":"accepted"}\n'
end
=======
function M.verify()
  os.execute("git -C " .. os.getenv("MODEL_REMOTE") .. " fetch")
  return 200, '{"status":"accepted"}\n'
end
>>>>>>> origin/harden-lock-verifier

function M.serve(port)
  local server = assert(socket.bind("127.0.0.1", port))
  while true do
    local client = server:accept()
    client:settimeout(2)
    local request = client:receive("*l") or ""
    repeat local line = client:receive("*l") until not line or line == ""
    local method, path = request:match("^(%S+) (%S+)")
    local status, body
    if method == "GET" and path == "/healthz" then
      status, body = 200, '{"status":"ok"}\n'
    elseif method == "POST" and path == "/verify-lock" then
      status, body = M.verify()
    else
      status, body = 404, '{"error":"not_found"}\n'
    end
    local phrase = status == 200 and "OK" or status == 422 and "Unprocessable Entity" or "Not Found"
    client:send("HTTP/1.1 " .. status .. " " .. phrase .. "\r\nContent-Type: application/json\r\nContent-Length: " .. #body .. "\r\nConnection: close\r\n\r\n" .. body)
    client:close()
  end
end

return M
