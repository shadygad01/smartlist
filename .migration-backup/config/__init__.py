"""Config package — JSON files and scanner_config.py."""
import json, os

_DIR = os.path.dirname(__file__)

def load_weights(path=None):
    p = path or os.path.join(_DIR, "weights.json")
    with open(p) as f:
        return json.load(f)

def load_thresholds(path=None):
    p = path or os.path.join(_DIR, "thresholds.json")
    with open(p) as f:
        return json.load(f)

def load_gates(path=None):
    p = path or os.path.join(_DIR, "gates_config.json")
    with open(p) as f:
        return json.load(f)
