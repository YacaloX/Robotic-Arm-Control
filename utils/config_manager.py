import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "robotic_arm"
CONFIG_FILE = CONFIG_DIR / "robot_config.json"

DEFAULT_PIN_POOL = [13, 12, 14, 27, 25, 26, 33, 32, 22, 23]

SERVO_NAME_TEMPLATES = [
    "Base",
    "Hombro",
    "Codo",
    "Rotación muñeca",
    "Inclinación muñeca",
    "Rotación mano",
]

DEFAULT_CONFIG = {
    "dof": 6,
    "pins": [13, 12, 14, 27, 25, 26],
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def get_servo_names(dof):
    return list(SERVO_NAME_TEMPLATES[:dof])


def get_pin_pool():
    return list(DEFAULT_PIN_POOL)
