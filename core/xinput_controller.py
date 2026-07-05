import ctypes
import threading
import time
from queue import Queue, Empty, Full

ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167

XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE = 7849
XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE = 8689

BUTTON_ACTIONS = {
    XINPUT_GAMEPAD_A: "home",
    XINPUT_GAMEPAD_B: "save_posture",
    XINPUT_GAMEPAD_Y: "add_posture",
    XINPUT_GAMEPAD_START: "play",
    XINPUT_GAMEPAD_BACK: "stop",
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_uint16),
        ("bLeftTrigger", ctypes.c_uint8),
        ("bRightTrigger", ctypes.c_uint8),
        ("sThumbLX", ctypes.c_int16),
        ("sThumbLY", ctypes.c_int16),
        ("sThumbRX", ctypes.c_int16),
        ("sThumbRY", ctypes.c_int16),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_uint32),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


class XInputController:
    POLL_INTERVAL = 1.0 / 60.0
    DPAD_INTERVAL = 1.0 / 12.0
    DPAD_STEP = 3

    def __init__(self, log_callback=None):
        self._xinput = self._load_dll()
        self._log = log_callback or (lambda m: None)

        self._enabled = False
        self._running = False
        self._connected = False
        self._thread = None

        self._target_queue = Queue(maxsize=1)
        self._delta_queue = Queue(maxsize=10)
        self._button_queue = Queue(maxsize=10)
        self._prev_buttons = 0

        self._last_dpad_time = 0.0
        self._last_stick_values = [0.0] * 4
        self._prev_connected = False

        self._on_connection_changed = None

    def set_connection_callback(self, callback):
        self._on_connection_changed = callback

    @property
    def is_connected(self):
        return self._connected

    @property
    def enabled(self):
        return self._enabled

    @property
    def available(self):
        return self._xinput is not None

    def _load_dll(self):
        if not hasattr(ctypes, "WinDLL"):
            return None
        for dll in ["xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"]:
            try:
                return ctypes.WinDLL(dll)
            except OSError:
                continue
        return None

    def start(self):
        if self._running or not self._xinput:
            if not self._xinput:
                self._log("XInput no disponible en este sistema")
            return
        self._enabled = True
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._log("Controlador XInput iniciado")

    def stop(self):
        self._enabled = False
        self._running = False
        self._thread = None
        self._connected = False
        self._log("Controlador XInput detenido")

    def set_enabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self._log("Control por mando activado")
        else:
            self._log("Control por mando desactivado")

    def _poll_loop(self):
        state = XINPUT_STATE()
        while self._running:
            try:
                result = self._xinput.XInputGetState(0, ctypes.byref(state))
                connected = result == ERROR_SUCCESS

                if connected != self._prev_connected:
                    self._connected = connected
                    self._prev_connected = connected
                    if self._on_connection_changed:
                        self._on_connection_changed(connected)
                    if connected:
                        self._log("Mando Xbox conectado")
                    else:
                        self._log("Mando Xbox desconectado")

                if connected and self._enabled:
                    self._process_state(state.Gamepad)

            except Exception as e:
                self._log(f"Error en controlador: {e}")

            time.sleep(self.POLL_INTERVAL)

    def _process_state(self, gamepad):
        now = time.time()

        buttons = gamepad.wButtons
        changed = buttons ^ self._prev_buttons

        if changed:
            pressed = buttons & changed
            self._handle_buttons(pressed)
            self._prev_buttons = buttons

        target = [None] * 4
        lx = self._normalize_stick(gamepad.sThumbLX, XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE, 32767)
        ly = self._normalize_stick(gamepad.sThumbLY, XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE, 32767)
        rx = self._normalize_stick(gamepad.sThumbRX, XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE, 32767)
        ry = self._normalize_stick(gamepad.sThumbRY, XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE, 32767)

        stick_values = [lx, ly, rx, ry]

        for i in range(4):
            if abs(stick_values[i]) > 0.05:
                target[i] = stick_values[i]
                self._last_stick_values[i] = stick_values[i]
            elif abs(self._last_stick_values[i]) > 0.01:
                self._last_stick_values[i] *= 0.9
                if abs(self._last_stick_values[i]) < 0.01:
                    self._last_stick_values[i] = 0.0
                target[i] = self._last_stick_values[i]

        target_angles = [None] * 6
        if target[0] is not None:
            target_angles[0] = round(target[0] * 90)
        if target[1] is not None:
            target_angles[1] = round(-target[1] * 90)
        if target[2] is not None:
            target_angles[3] = round(target[2] * 90)
        if target[3] is not None:
            target_angles[4] = round(-target[3] * 90)

        if now - self._last_dpad_time >= self.DPAD_INTERVAL:
            dpad_left = buttons & XINPUT_GAMEPAD_DPAD_LEFT
            dpad_right = buttons & XINPUT_GAMEPAD_DPAD_RIGHT
            dpad_up = buttons & XINPUT_GAMEPAD_DPAD_UP
            dpad_down = buttons & XINPUT_GAMEPAD_DPAD_DOWN

            if dpad_left:
                self._put_delta(2, -self.DPAD_STEP)
            elif dpad_right:
                self._put_delta(2, self.DPAD_STEP)
            if dpad_up:
                self._put_delta(5, self.DPAD_STEP)
            elif dpad_down:
                self._put_delta(5, -self.DPAD_STEP)

            if dpad_left or dpad_right or dpad_up or dpad_down:
                self._last_dpad_time = now

        has_stick_target = any(v is not None for v in target_angles[:2] + target_angles[3:5])
        if has_stick_target:
            try:
                self._target_queue.get_nowait()
            except Empty:
                pass
            try:
                self._target_queue.put_nowait(target_angles)
            except Full:
                pass

    def _handle_buttons(self, pressed_mask):
        for flag, action in BUTTON_ACTIONS.items():
            if pressed_mask & flag:
                try:
                    self._button_queue.put_nowait(action)
                except Full:
                    pass

    @staticmethod
    def _normalize_stick(value, deadzone, max_val):
        if abs(value) < deadzone:
            return 0.0
        if value > 0:
            return (value - deadzone) / (max_val - deadzone)
        else:
            return (value + deadzone) / (max_val - deadzone)

    def _put_delta(self, index, value):
        try:
            self._delta_queue.put_nowait((index, value))
        except Full:
            try:
                self._delta_queue.get_nowait()
                self._delta_queue.put_nowait((index, value))
            except (Empty, Full):
                pass

    def read_target(self):
        try:
            return self._target_queue.get_nowait()
        except Empty:
            return None

    def read_delta(self):
        try:
            return self._delta_queue.get_nowait()
        except Empty:
            return None

    def read_button(self):
        try:
            return self._button_queue.get_nowait()
        except Empty:
            return None
