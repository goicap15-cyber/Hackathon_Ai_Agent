import sys, json, urllib.request
msg  = sys.argv[1]
role = sys.argv[2] if len(sys.argv) > 2 else "rm"
data = json.dumps({"message": msg, "role": role}).encode()
req  = urllib.request.Request("http://localhost:8000/api/chat", data=data,
                              headers={"Content-Type": "application/json"})
d = json.load(urllib.request.urlopen(req, timeout=120))
print("=== ROLE:", role, "| tool_called:", d.get("tool_called"), "===")
print("RESP:\n", d["response"])
print("\nTRACE:")
for t in d["trace_logs"]:
    print("  -", t)
