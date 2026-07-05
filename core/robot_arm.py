from __future__ import annotations
from typing import List, Dict, Optional
from utils.config_manager import get_servo_names
from utils.theme import SERVO_PINS


class RobotArm:
    MIN_ANGLE = -90
    MAX_ANGLE = 90
    HOME_ANGLE = 0

    def __init__(self, transport, num_servos: int = 6, servo_pins: List[int] = None):
        self._transport = transport
        self._num_servos = num_servos
        pins = servo_pins or SERVO_PINS
        self._servo_pins = list(pins[:num_servos])
        self._current_angles: List[int] = [self.HOME_ANGLE] * self._num_servos
        self._servos: List[Dict] = []
        names = get_servo_names(self._num_servos)
        for i in range(self._num_servos):
            self._servos.append({
                "id": i,
                "pin": self._servo_pins[i],
                "name": names[i],
                "min": self.MIN_ANGLE,
                "max": self.MAX_ANGLE,
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
    def validate_angle(angle: int) -> int:
        return max(-90, min(90, int(angle)))

    def move(self, servo_id: int, angle: int) -> bool:
        if servo_id < 0 or servo_id >= self._num_servos:
            return False
        angle = self.validate_angle(angle)
        self._current_angles[servo_id] = angle
        return self._transport.send(servo_id, angle)

    def move_all(self, angles: List[int]) -> bool:
        results = []
        n = min(len(angles), self._num_servos)
        for i in range(n):
            angle = self.validate_angle(angles[i])
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
            self._servos.append({
                "id": i,
                "pin": self._servo_pins[i],
                "name": names[i],
                "min": self.MIN_ANGLE,
                "max": self.MAX_ANGLE,
            })
