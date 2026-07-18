import threading
import time
import math
from core.motion_controller import MotionController


class WiimoteController(MotionController):
    POLL_INTERVAL = 1.0 / 60.0
    ACCEL_REST_X = 512
    ACCEL_REST_Y = 512
    ACCEL_REST_Z = 512
    ACCEL_SCALE = 200.0
    IR_WIDTH = 1024
    IR_HEIGHT = 768
    DPAD_INTERVAL = 1.0 / 12.0
    DPAD_STEP = 3

    def __init__(self, log_callback=None):
        super().__init__(log_callback)
        self._wm = None
        self._orientation = (0.0, 0.0)
        self._ir_position = (0.0, 0.0)
        self._has_ir = False
        self._prev_buttons = {}
        self._last_dpad_time = 0.0
        self._accel_lock = threading.Lock()
        self._ir_lock = threading.Lock()
        self._latest_accel = (self.ACCEL_REST_X, self.ACCEL_REST_Y, self.ACCEL_REST_Z)
        self._latest_ir = []

    @property
    def available(self) -> bool:
        try:
            import wiimote as _wm_mod
            return True
        except ImportError:
            return False

    def start(self):
        pass

    def stop(self):
        self._enabled = False
        self._running = False
        if self._wm:
            try:
                self._wm.disconnect()
            except Exception:
                pass
            self._wm = None
        self._connected = False
        self._log("Controlador Wiimote detenido")

    def connect(self) -> bool:
        if not self.available:
            self._log("wiimote.py no instalado (pip install wiimote.py)")
            return False
        if self._connected:
            self._log("Wiimote ya conectado")
            return False

        import wiimote as wm_mod

        try:
            self._log("Buscando Wiimotes...")
            devices = wm_mod.find()
            if not devices:
                self._log("No se encontraron Wiimotes. Presiona 1+2 o SYNC.")
                return False

            btaddr, name = devices[0]
            self._log(f"Conectando a {btaddr} ({name})...")
            self._wm = wm_mod.connect(btaddr, name)
            self._connected = True

            self._wm.buttons.register_callback(self._on_buttons)
            self._wm.accelerometer.register_callback(self._on_accel)
            self._wm.ir.register_callback(self._on_ir)

            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()

            if self._on_connection_changed:
                self._on_connection_changed(True)
            self._log("Wiimote conectado correctamente")
            return True

        except Exception as e:
            self._log(f"Error conectando Wiimote: {e}")
            self._connected = False
            return False

    def disconnect(self):
        self.stop()

    def _on_buttons(self, changed_buttons):
        for name, pressed in changed_buttons:
            if pressed:
                if name == 'A':
                    self._put_button("home")
                elif name == 'B':
                    self._put_button("save_posture")
                elif name == 'One':
                    self._put_button("add_posture")
                elif name == 'Plus':
                    self._put_button("play")
                elif name == 'Minus':
                    self._put_button("stop")
                elif name == 'Home':
                    self.set_led(0.0, 1.0, 0.0)
                    self._log("Wiimote: LED verde activado")

            self._prev_buttons[name] = pressed

        now = time.time()
        if now - self._last_dpad_time < self.DPAD_INTERVAL:
            return
        for name, pressed in changed_buttons:
            if not pressed:
                continue
            if name == 'Up':
                self._put_delta(5, self.DPAD_STEP)
                self._last_dpad_time = now
            elif name == 'Down':
                self._put_delta(5, -self.DPAD_STEP)
                self._last_dpad_time = now
            elif name == 'Left':
                self._put_delta(2, -self.DPAD_STEP)
                self._last_dpad_time = now
            elif name == 'Right':
                self._put_delta(2, self.DPAD_STEP)
                self._last_dpad_time = now

    def _on_accel(self, values):
        with self._accel_lock:
            self._latest_accel = tuple(values)

    def _on_ir(self, ir_data):
        with self._ir_lock:
            self._latest_ir = list(ir_data) if ir_data else []

    def _poll_loop(self):
        while self._running and self._connected:
            try:
                with self._accel_lock:
                    raw = self._latest_accel
                with self._ir_lock:
                    ir_data = list(self._latest_ir)

                ax = (raw[0] - self.ACCEL_REST_X) / self.ACCEL_SCALE
                ay = (raw[1] - self.ACCEL_REST_Y) / self.ACCEL_SCALE
                az = (raw[2] - self.ACCEL_REST_Z) / self.ACCEL_SCALE

                az_clamped = max(0.01, abs(az))
                pitch = math.degrees(math.atan2(ax, math.sqrt(ay ** 2 + az_clamped ** 2)))
                roll = math.degrees(math.atan2(ay, math.sqrt(ax ** 2 + az_clamped ** 2)))

                pitch = max(-90.0, min(90.0, pitch))
                roll = max(-90.0, min(90.0, roll))
                self._orientation = (pitch, roll)

                if ir_data:
                    biggest = max(ir_data, key=lambda o: o.get('size', 0))
                    self._ir_position = (
                        biggest['x'] / self.IR_WIDTH,
                        biggest['y'] / self.IR_HEIGHT,
                    )
                    self._has_ir = True
                else:
                    self._has_ir = False

                if self._enabled:
                    self._update_target(pitch, roll)

            except Exception as e:
                self._log(f"Error Wiimote poll: {e}")

            time.sleep(self.POLL_INTERVAL)

    def _update_target(self, pitch, roll):
        target = [None] * 6
        target[0] = max(-90, min(90, round(roll * 2)))
        target[1] = max(-90, min(90, round(pitch * 2)))

        if self._has_ir:
            ir_x, ir_y = self._ir_position
            target[3] = max(-90, min(90, round((ir_x - 0.5) * 180)))
            target[4] = max(-90, min(90, round((ir_y - 0.5) * 180)))

        self._put_target(target)

    def get_orientation(self):
        return self._orientation

    def get_position(self):
        if self._has_ir:
            return (self._ir_position[0], self._ir_position[1], 0.0)
        return (0.5, 0.5, 0.0)

    def set_led(self, r, g, b):
        if not self._wm:
            return
        brightness = (r + g + b) / 3.0
        try:
            self._wm.leds[0] = brightness > 0.1
            self._wm.leds[1] = brightness > 0.35
            self._wm.leds[2] = brightness > 0.65
            self._wm.leds[3] = brightness > 0.9
        except Exception:
            pass

    def set_rumble(self, intensity):
        if not self._wm:
            return
        try:
            self._wm.rumbler.set_rumble(intensity > 0.5)
        except Exception:
            pass
