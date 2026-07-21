from __future__ import annotations
import math
import threading
import time
from typing import List, Dict, Optional, Callable
from utils.config_manager import get_servo_names
from utils.theme import SERVO_PINS


class RobotArm:
    MIN_ANGLE = -90
    MAX_ANGLE = 90
    HOME_ANGLE = 0
    GRIPPER_SERVO_ID = 5
    GRIPPER_MIN_ANGLE = -20
    GRIPPER_MAX_ANGLE = 45

    def __init__(self, transport, num_servos: int = 6, servo_pins: List[int] = None):
        self._transport = transport
        self._num_servos = num_servos
        pins = servo_pins or SERVO_PINS
        self._servo_pins = list(pins[:num_servos])
        self._current_angles: List[int] = [self.HOME_ANGLE] * self._num_servos
        self._servos: List[Dict] = []
        self._ramp_stop = threading.Event()
        self._ramp_thread: Optional[threading.Thread] = None
        self._ramp_lock = threading.Lock()
        self._ramp_active = False
        self._ramp_progress_callback: Optional[Callable[[List[int]], None]] = None
        names = get_servo_names(self._num_servos)
        for i in range(self._num_servos):
            servo_min = self.GRIPPER_MIN_ANGLE if i == self.GRIPPER_SERVO_ID else self.MIN_ANGLE
            servo_max = self.GRIPPER_MAX_ANGLE if i == self.GRIPPER_SERVO_ID else self.MAX_ANGLE
            self._servos.append({
                "id": i,
                "pin": self._servo_pins[i],
                "name": names[i],
                "min": servo_min,
                "max": servo_max,
            })

    @property
    def num_servos(self) -> int:
        return self._num_servos

    @property
    def servo_pins(self) -> List[int]:
        return list(self._servo_pins)

    @property
    def servos(self) -> List[Dict]:
        return list(self._servos)

    @property
    def current_angles(self) -> List[int]:
        return list(self._current_angles)

    @staticmethod
    def validate_angle(angle: int, servo_id: int = -1) -> int:
        angle = max(-90, min(90, int(angle)))
        if servo_id == RobotArm.GRIPPER_SERVO_ID:
            angle = max(RobotArm.GRIPPER_MIN_ANGLE, min(RobotArm.GRIPPER_MAX_ANGLE, angle))
        return angle

    DEFAULT_STEP_SIZE = 1
    DEFAULT_DELAY_MS = 10

    def move(self, servo_id: int, angle: int) -> bool:
        if servo_id < 0 or servo_id >= self._num_servos:
            return False
        angle = self.validate_angle(angle, servo_id)
        self._current_angles[servo_id] = angle
        return self._transport.send(servo_id, angle)

    def move_all(self, angles: List[int]) -> bool:
        targets = []
        n = min(len(angles), self._num_servos)
        for i in range(n):
            targets.append(self.validate_angle(angles[i], i))
        while len(targets) < self._num_servos:
            targets.append(self._current_angles[len(targets)])
        needs_move = any(self._current_angles[i] != targets[i] for i in range(self._num_servos))
        if needs_move:
            self.move_all_ramped(targets, step_size=self.DEFAULT_STEP_SIZE,
                                 delay_ms=self.DEFAULT_DELAY_MS)
        return True

    def move_all_immediate(self, angles: List[int]) -> bool:
        results = []
        n = min(len(angles), self._num_servos)
        for i in range(n):
            angle = self.validate_angle(angles[i], i)
            self._current_angles[i] = angle
            result = self._transport.send(i, angle)
            results.append(result)
        return all(results)

    def home(self) -> bool:
        return self.move_all([0] * self._num_servos)

    def get_angle(self, servo_id: int) -> int:
        if 0 <= servo_id < self._num_servos:
            return self._current_angles[servo_id]
        return 0

    def set_transport(self, transport):
        self._transport = transport

    def reconfigure(self, num_servos: int, servo_pins: List[int]):
        self._num_servos = num_servos
        self._servo_pins = list(servo_pins[:num_servos])
        self._current_angles = [self.HOME_ANGLE] * self._num_servos
        self._servos = []
        names = get_servo_names(self._num_servos)
        for i in range(self._num_servos):
            servo_min = self.GRIPPER_MIN_ANGLE if i == self.GRIPPER_SERVO_ID else self.MIN_ANGLE
            servo_max = self.GRIPPER_MAX_ANGLE if i == self.GRIPPER_SERVO_ID else self.MAX_ANGLE
            self._servos.append({
                "id": i,
                "pin": self._servo_pins[i],
                "name": names[i],
                "min": servo_min,
                "max": servo_max,
            })

    @property
    def is_ramping(self) -> bool:
        with self._ramp_lock:
            return self._ramp_active

    def set_ramp_progress_callback(self, callback: Optional[Callable[[List[int]], None]]):
        self._ramp_progress_callback = callback

    def cancel_ramp(self):
        self._ramp_stop.set()
        with self._ramp_lock:
            self._ramp_active = False

    def _wait_for_ramp_thread(self):
        with self._ramp_lock:
            if self._ramp_thread and self._ramp_thread.is_alive():
                self._ramp_stop.set()
                self._ramp_thread.join(timeout=1.0)
            self._ramp_stop.clear()
            self._ramp_active = True

    def _ramp_done(self):
        with self._ramp_lock:
            self._ramp_active = False
            self._ramp_thread = None

    def move_all_ramped(self, target_angles: List[int], step_size: int = 1,
                        delay_ms: int = 10, callback: Optional[Callable] = None):
        self.cancel_ramp()
        self._wait_for_ramp_thread()

        targets = []
        for i in range(min(len(target_angles), self._num_servos)):
            targets.append(self.validate_angle(target_angles[i], i))
        while len(targets) < self._num_servos:
            targets.append(self._current_angles[len(targets)])

        current = list(self._current_angles)
        needs_move = any(current[i] != targets[i] for i in range(self._num_servos))

        if not needs_move:
            self._ramp_done()
            return

        def _ramp_worker():
            try:
                steps_per_servo = []
                for i in range(self._num_servos):
                    diff = abs(targets[i] - current[i])
                    n = max(1, math.ceil(diff / step_size))
                    steps_per_servo.append(n)
                total_steps = max(steps_per_servo)
                delay = max(0.001, delay_ms / 1000.0)

                for step in range(1, total_steps + 1):
                    if self._ramp_stop.is_set():
                        return
                    frame = []
                    for i in range(self._num_servos):
                        if total_steps == 1:
                            angle = targets[i]
                        else:
                            t = step / total_steps
                            angle = round(current[i] + (targets[i] - current[i]) * t)
                        angle = self.validate_angle(angle, i)
                        frame.append(angle)
                    self.move_all_immediate(frame)
                    if self._ramp_progress_callback:
                        try:
                            self._ramp_progress_callback(frame)
                        except Exception:
                            pass
                    if step < total_steps:
                        time.sleep(delay)
            finally:
                self._ramp_done()
                if callback:
                    try:
                        callback()
                    except Exception:
                        pass

        self._ramp_thread = threading.Thread(target=_ramp_worker, daemon=True)
        self._ramp_thread.start()

    def move_ramped(self, servo_id: int, target_angle: int, step_size: int = 1,
                    delay_ms: int = 10, callback: Optional[Callable] = None):
        if servo_id < 0 or servo_id >= self._num_servos:
            return
        target_angle = self.validate_angle(target_angle, servo_id)
        angles = list(self._current_angles)
        angles[servo_id] = target_angle
        self.move_all_ramped(angles, step_size=step_size, delay_ms=delay_ms,
                             callback=callback)

    def home_ramped(self, step_size: int = 1, delay_ms: int = 10,
                    callback: Optional[Callable] = None):
        self.move_all_ramped([0] * self._num_servos, step_size=step_size,
                             delay_ms=delay_ms, callback=callback)

    def emergency_stop(self, callback: Optional[Callable] = None):
        self.cancel_ramp()
        self.move_all_immediate([0] * self._num_servos)
        if callback:
            try:
                callback()
            except Exception:
                pass
