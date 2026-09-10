import json
from datetime import datetime

class GroundTruthLog:
    """Records every change the injection module makes. For the use later for scoring script"""

    def __init__(self):
        self.changes = []

    def record(self, pattern, change_type, target_id, details=None):
        self.changes.append({
            "pattern": pattern,
            "change_type": change_type,   # Pattern definition, e.g. "duplicated_object_id"
            "target_id": target_id,
            "details": details or {},
        })

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.changes, f, indent=2)