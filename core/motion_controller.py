from abc import ABC, abstractmethod
from queue import Queue, Empty, Full
import threading
import time


class MotionController(ABC):
    POLL_INTERVAL = 1.0 / 60.0

    def __init__(self, log_callback=None):
        self._log = log_callback or (lambda m: None)
        self._enabled = False
        self._running = False
        self._connected = False
        self._thread = None

        self._target_queue = Queue(maxsize=1)
        self._delta_queue = Queue(maxsize=10)
        self._button_queue = Queue(maxsize=10)

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
    @abstractmethod
    def available(self) -> bool:
        ...

    def set_enabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self._log("Control por movimiento activado")
        else:
            self._log("Control por movimiento desactivado")

    @abstractmethod
    def start(self):
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def get_orientation(self) -> tuple:
        ...

    @abstractmethod
    def get_position(self) -> tuple:
        ...

    @abstractmethod
    def set_led(self, r: float, g: float, b: float):
        ...

    @abstractmethod
    def set_rumble(self, intensity: float):
        ...

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

    def _put_button(self, action):
        try:
            self._button_queue.put_nowait(action)
        except Full:
            pass

    def _put_target(self, target):
        try:
            self._target_queue.put_nowait(target)
        except Full:
            try:
                self._target_queue.get_nowait()
                self._target_queue.put_nowait(target)
            except (Empty, Full):
                pass

    def _put_delta(self, index, value):
        try:
            self._delta_queue.put_nowait((index, value))
        except Full:
            try:
                self._delta_queue.get_nowait()
                self._delta_queue.put_nowait((index, value))
            except (Empty, Full):
                pass
