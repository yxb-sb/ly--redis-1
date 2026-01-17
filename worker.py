import redis
import json
import sys
import os
import socket
import time

SETTINGS_FILE = "after_settings"
ALGO_QUEUE_KEY = "algorithms_queue"
RESULTS_QUEUE = "results"
CODE_KEY = "dist_code_source"

def main():
    if not os.path.exists(SETTINGS_FILE): sys.exit("No settings file")
    with open(SETTINGS_FILE) as f: lines = [l.strip() for l in f]
    host, port = lines[0], int(lines[1])
    
    try:
        r = redis.Redis(host=host, port=port, socket_timeout=5)
        r.ping()
    except Exception as e: sys.exit(f"Conn error: {e}")

    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    print(f"Worker [{worker_id}] connected.")

    code = r.get(CODE_KEY)
    if not code: sys.exit("No code")
    context = {}
    exec(code.decode('utf-8'), context)
    registry = context.get("TASK_REGISTRY", {})

    print("Fetching task...")
    item = r.blpop(ALGO_QUEUE_KEY, timeout=3)
    if not item:
        print("Queue empty. Exiting.")
        sys.exit(0)

    _, raw = item
    payload = {"worker": worker_id, "status": "error"}
    try:
        conf = json.loads(raw)
        name = conf.get("task_name")
        func = registry.get(name)
        if func:
            print(f"Running: {name}")
            res = func(conf.get("params", {}), r)
            payload.update({"status": "success", "result": res, "task": name})
        else: payload["error"] = f"Unknown {name}"
    except Exception as e: payload["error"] = str(e)

    r.rpush(RESULTS_QUEUE, json.dumps(payload))
    print("Done.")

if __name__ == "__main__": main()