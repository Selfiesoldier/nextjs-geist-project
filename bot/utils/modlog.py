import json
import os
from datetime import datetime
from threading import Lock

MODLOG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'modlog.json')
file_lock = Lock()

def log_action(action, by, target, reason="", duration=None):
    log_entry = {
        "action": action,
        "by": by,
        "target": target,
        "reason": reason,
        "duration": duration,
        "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    with file_lock:
        try:
            with open(MODLOG_FILE, 'r') as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []
        logs.append(log_entry)
        with open(MODLOG_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
