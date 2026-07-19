import threading
import math
from core.motion_controller import MotionController


class PSMoveController(MotionController):
    POLL_INTERVAL = 1.0 / 60.0
    ACCEL_SCALE = 4.0
    TRIGGER_THRESHOLD = 0.1
    GRIPPER_SERVO_ID = 5
    GRIPPER_MIN_ANGLE = -20
    GRIPPER_MAX_ANGLE = 45

    def __init__(self, log_callback=None):
        super().__init__(log_callback)
        self._api = None
        self._api_thread = None
        self._controller = None
        self._orientation = (0.0, 0.0)
        self._position = (0.0, 0.0, 0.0)
        self._trigger_value = 0.0
        self._move_held = False
        self._poll_thread = None
        self._psmoveapi = None

    @property
    def available(self) -> bool:
        try:
            import psmoveapi as _pm
            self._psmoveapi = _pm
            return True
        except ImportError:
            return self._try_load_psmoveapi()

    def _try_load_psmoveapi(self) -> bool:
        import sys
        import os

        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "psmoveapi", "bindings", "python"),
            os.path.join(home, "psmoveapi", "build"),
        ]

        binding_dir = os.path.join(home, "psmoveapi", "bindings", "python")
        if binding_dir not in sys.path and os.path.isfile(os.path.join(binding_dir, "psmoveapi.py")):
            sys.path.insert(0, binding_dir)

        lib_path = os.path.join(home, "psmoveapi", "build")
        if not os.environ.get("PSMOVEAPI_LIBRARY_PATH") and os.path.isfile(os.path.join(lib_path, "libpsmoveapi.so")):
            os.environ["PSMOVEAPI_LIBRARY_PATH"] = lib_path

        try:
            import importlib
            if "psmoveapi" in sys.modules:
                del sys.modules["psmoveapi"]
            import psmoveapi as _pm
            self._psmoveapi = _pm
            return True
        except ImportError:
            return False

    def start(self):
        pass

    def stop(self):
        self._enabled = False
        self._running = False
        if self._api:
            self._api.quit = True
            self._api = None
        self._connected = False
        self._controller = None
        self._log("Controlador PSMove detenido")

    def connect(self) -> bool:
        if not self.available:
            self._log("psmoveapi no disponible. Ver README para instalación.")
            return False
        if self._connected:
            self._log("PSMove ya conectado")
            return False

        import psmoveapi

        self._running = True

        outer = self

        class PSMoveHandler(psmoveapi.PSMoveAPI):
            def __init__(self):
                super().__init__()
                self.quit = False

            def on_connect(self, controller):
                outer._controller = controller
                outer._connected = True
                conn_type = "Bluetooth" if controller.bluetooth else "USB"
                outer._log(f"PSMove conectado ({conn_type}): {controller.serial}")
                if controller.bluetooth:
                    controller.color = psmoveapi.RGB(0.0, 0.5, 1.0)
                if outer._on_connection_changed:
                    outer._on_connection_changed(True)

            def on_update(self, controller):
                if not outer._enabled:
                    return

                try:
                    accel = controller.accelerometer
                    ax = accel.x / outer.ACCEL_SCALE
                    ay = accel.y / outer.ACCEL_SCALE
                    az = accel.z / outer.ACCEL_SCALE

                    az_clamped = max(0.01, abs(az))
                    pitch = math.degrees(math.atan2(ax, math.sqrt(ay ** 2 + az_clamped ** 2)))
                    roll = math.degrees(math.atan2(ay, math.sqrt(ax ** 2 + az_clamped ** 2)))
                    pitch = max(-90.0, min(90.0, pitch))
                    roll = max(-90.0, min(90.0, roll))
                    outer._orientation = (pitch, roll)
                except Exception:
                    pass

                try:
                    outer._trigger_value = controller.trigger
                except Exception:
                    pass

                try:
                    outer._move_held = controller.now_pressed(psmoveapi.Button.MOVE)
                except Exception:
                    pass

                try:
                    btn = psmoveapi.Button
                    if controller.now_pressed(btn.TRIANGLE):
                        outer._put_button("home")
                    elif controller.now_pressed(btn.CIRCLE):
                        outer._put_button("save_posture")
                    elif controller.now_pressed(btn.CROSS):
                        outer._put_button("add_posture")
                    elif controller.now_pressed(btn.START):
                        outer._put_button("play")
                    elif controller.now_pressed(btn.SELECT):
                        outer._put_button("stop")
                except Exception:
                    pass

                if outer._enabled:
                    outer._update_target()

            def on_disconnect(self, controller):
                outer._connected = False
                outer._controller = None
                outer._log("PSMove desconectado")
                if outer._on_connection_changed:
                    outer._on_connection_changed(False)

        try:
            self._log("Iniciando psmoveapi...")
            self._api = PSMoveHandler()
            self._api_thread = threading.Thread(target=self._run_api, daemon=True)
            self._api_thread.start()
            return True
        except Exception as e:
            self._log(f"Error iniciando PSMove: {e}")
            return False

    def _run_api(self):
        try:
            while self._running and self._api and not self._api.quit:
                self._api.update()
        except Exception as e:
            self._log(f"Error PSMove API: {e}")

    def _update_target(self):
        pitch, roll = self._orientation
        trigger = self._trigger_value

        target = [None] * 6
        target[0] = max(-90, min(90, round(roll * 2)))

        if self._move_held:
            target[4] = max(-90, min(90, round(pitch * 2)))
        else:
            target[1] = max(-90, min(90, round(pitch * 2)))

        gripper_range = self.GRIPPER_MAX_ANGLE - self.GRIPPER_MIN_ANGLE
        target[5] = max(self.GRIPPER_MIN_ANGLE, min(self.GRIPPER_MAX_ANGLE,
                        round(self.GRIPPER_MIN_ANGLE + trigger * gripper_range)))

        self._put_target(target)

    def disconnect(self):
        self.stop()

    def get_orientation(self):
        return self._orientation

    def get_position(self):
        return self._position

    def set_led(self, r, g, b):
        if not self._controller or not self._psmoveapi:
            return
        try:
            self._controller.color = self._psmoveapi.RGB(r, g, b)
        except Exception:
            pass

    def set_rumble(self, intensity):
        if not self._controller:
            return
        try:
            self._controller.rumble = max(0.0, min(1.0, intensity))
        except Exception:
            pass
