DARK = {
    "bg": "#1a1b1e",
    "bg_secondary": "#25262b",
    "bg_tertiary": "#2c2e33",
    "fg": "#c1c2c5",
    "fg_dim": "#909296",
    "accent": "#4c9aff",
    "accent_hover": "#3a8af0",
    "success": "#51cf66",
    "danger": "#ff6b6b",
    "warning": "#fcc419",
    "border": "#373a40",
    "slider_fg": "#4c9aff",
    "slider_bg": "#373a40",
    "entry_bg": "#2c2e33",
    "hover": "#373a40",
    "led_off": "#495057",
    "card_bg": "#25262b",
}

LIGHT = {
    "bg": "#f8f9fa",
    "bg_secondary": "#ffffff",
    "bg_tertiary": "#f1f3f5",
    "fg": "#212529",
    "fg_dim": "#868e96",
    "accent": "#1971c2",
    "accent_hover": "#1864ab",
    "success": "#2f9e44",
    "danger": "#e03131",
    "warning": "#f08c00",
    "border": "#dee2e6",
    "slider_fg": "#1971c2",
    "slider_bg": "#dee2e6",
    "entry_bg": "#ffffff",
    "hover": "#e9ecef",
    "led_off": "#adb5bd",
    "card_bg": "#ffffff",
}

THEME = {
    "os": "dark",
    "name": "dark",
    "colors": DARK,
}

ICONS = {
    "connected": "\U0001f7e2",
    "disconnected": "\U0001f534",
    "home": "\u2302",
    "save": "\U0001f4be",
    "load": "\U0001f4c2",
    "add": "\u271a",
    "delete": "\u2715",
    "play": "\u25b6",
    "stop": "\u25a0",
    "log": "\U0001f4cb",
    "settings": "\u2699",
}

# Estas variables se actualizan dinámicamente desde config_manager
SERVO_NAMES = [
    "Base",
    "Hombro",
    "Codo",
    "Rotación muñeca",
    "Inclinación muñeca",
    "Pinza",
]

SERVO_PINS = [13, 12, 14, 27, 25, 26]
