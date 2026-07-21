from __future__ import annotations
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Callable


class SequencePlayer:
    STEPS_BASE = 20
    SMOOTH_STEP_SIZE = 1
    SMOOTH_DELAY_MS = 10

    def __init__(self, robot_arm, log_callback: Optional[Callable] = None):
        self._arm = robot_arm
        self._log: Callable = log_callback or (lambda m: None)
        self._postures: List[Dict] = []
        self._stop_event = threading.Event()
        self._playing: bool = False
        self._lock = threading.Lock()

    @property
    def postures(self) -> List[Dict]:
        return list(self._postures)

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    @property
    def posture_count(self) -> int:
        return len(self._postures)

    def add_posture(self, angles: List[int], name: Optional[str] = None) -> int:
        if not name:
            name = f"Postura {len(self._postures) + 1}"
        self._postures.append({
            "name": name,
            "angles": [int(a) for a in angles],
        })
        self._log(f"Postura agregada: {name}")
        return len(self._postures) - 1

    def remove_posture(self, index: int) -> bool:
        if 0 <= index < len(self._postures):
            name = self._postures[index]["name"]
            del self._postures[index]
            self._log(f"Postura eliminada: {name}")
            return True
        return False

    def clear(self) -> None:
        self._postures.clear()
        self._log("Secuencia limpiada")

    def load(self, filepath: str) -> bool:
        path = Path(filepath)
        if not path.exists():
            self._log(f"Archivo no encontrado: {filepath}")
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._postures = data
            elif isinstance(data, dict) and "postures" in data:
                self._postures = data["postures"]
            else:
                self._log("Formato de archivo inválido")
                return False
            self._log(f"Secuencia cargada: {path.name} ({len(self._postures)} posturas)")
            return True
        except (json.JSONDecodeError, OSError) as e:
            self._log(f"Error al cargar: {e}")
            return False

    def save(self, filepath: str) -> bool:
        path = Path(filepath)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"postures": self._postures}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._log(f"Secuencia guardada: {path.name}")
            return True
        except OSError as e:
            self._log(f"Error al guardar: {e}")
            return False

    def save_posture(self, angles: List[int], filepath: str) -> bool:
        path = Path(filepath)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "name": "Postura guardada",
                "angles": [int(a) for a in angles],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._log(f"Postura guardada: {path.name}")
            return True
        except OSError as e:
            self._log(f"Error al guardar: {e}")
            return False

    def load_posture(self, filepath: str) -> Optional[List[int]]:
        path = Path(filepath)
        if not path.exists():
            self._log(f"Archivo no encontrado: {filepath}")
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "angles" in data:
                angles = data["angles"]
            elif isinstance(data, list):
                angles = data
            else:
                self._log("Formato de postura inválido")
                return None
            num = self._arm.num_servos
            if len(angles) != num:
                self._log(f"La postura debe tener {num} ángulos")
                return None
            self._log(f"Postura cargada: {path.name}")
            return [int(a) for a in angles]
        except (json.JSONDecodeError, OSError, ValueError) as e:
            self._log(f"Error al cargar postura: {e}")
            return None

    @staticmethod
    def _interpolate(start: List[int], end: List[int], steps: int) -> List[List[int]]:
        if steps < 1:
            steps = 1
        result = []
        for i in range(steps + 1):
            t = i / steps
            frame = []
            for s, e in zip(start, end):
                frame.append(round(s + (e - s) * t))
            result.append(frame)
        return result

    def play(self, speed: float = 1.0, servo_steps: Optional[int] = None) -> None:
        with self._lock:
            if self._playing:
                self._log("Ya está reproduciendo")
                return
            if len(self._postures) < 2:
                self._log("Se necesitan al menos 2 posturas para reproducir")
                return
            self._stop_event.clear()
            self._playing = True
        steps = servo_steps or self.STEPS_BASE
        delay = max(0.01, (1.0 / (steps * speed)) * 0.5)
        thread = threading.Thread(
            target=self._playback_loop,
            args=(steps, delay),
            daemon=True,
        )
        thread.start()

    def _playback_loop(self, steps: int, delay: float) -> None:
        self._log("Reproduciendo secuencia...")
        try:
            current = list(self._arm.current_angles)
            all_frames = []
            for posture in self._postures:
                target = posture["angles"]
                frames = self._interpolate(current, target, steps)
                all_frames.extend(frames)
                current = target
            for frame in all_frames:
                if self._stop_event.is_set():
                    self._log("Reproducción detenida")
                    return
                self._arm.move_all_ramped(frame, step_size=self.SMOOTH_STEP_SIZE,
                                          delay_ms=self.SMOOTH_DELAY_MS)
                time.sleep(delay)
            self._log("Reproducción finalizada")
        finally:
            with self._lock:
                self._playing = False

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._playing = False
        self._log("Deteniendo reproducción...")
