import threading
import time
import math
from typing import List, Optional, Callable, Tuple, Dict

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class AutoCalibrator:
    CALIBRATION_STEPS = 5
    STEP_DELAY = 0.3
    MARKER_LENGTH = 0.025

    def __init__(self, robot_arm, camera_manager, log_callback=None):
        self._arm = robot_arm
        self._camera = camera_manager
        self._log = log_callback or (lambda m: None)
        self._running = False
        self._progress_callback = None
        self._result_callback = None
        self._thread = None
        self._calibration_data = {}
        self._servo_angles = {}
        self._marker_id = 0

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def set_result_callback(self, callback):
        self._result_callback = callback

    def _report_progress(self, stage, progress, detail=""):
        if self._progress_callback:
            try:
                self._progress_callback(stage, progress, detail)
            except Exception:
                pass

    def _report_result(self, result):
        if self._result_callback:
            try:
                self._result_callback(result)
            except Exception:
                pass

    def calibrate_servo_endpoints(self, servo_id, num_steps=None, marker_id=0):
        if num_steps is None:
            num_steps = self.CALIBRATION_STEPS
        if not self._camera.is_open:
            self._log("Camara no abierta para calibracion")
            return None
        self._marker_id = marker_id
        angles = []
        positions = []
        step_size = max(1, 180 // num_steps)
        angle_range = list(range(-90, 91, step_size))
        for i, angle in enumerate(angle_range):
            self._report_progress("endpoints", i / len(angle_range),
                                  f"Moviendo servo {servo_id} a {angle} deg")
            self._arm.move_all_ramped(
                self._build_angle_array(servo_id, angle),
                step_size=1, delay_ms=10
            )
            time.sleep(self.STEP_DELAY)
            markers = self._camera.detect_aruco(marker_ids=[marker_id])
            if markers:
                pos = markers[0]["center"]
                angles.append(angle)
                positions.append(pos)
                self._log(f"  Servo {servo_id} @ {angle}deg -> pixel ({pos[0]}, {pos[1]})")
            else:
                self._log(f"  Servo {servo_id} @ {angle}deg -> sin marker detectado")
        if len(angles) < 3:
            self._log(f"Insuficientes puntos para calibrar servo {servo_id}")
            return None
        center_angle = self._find_center_angle(angles, positions)
        result = {
            "servo_id": servo_id,
            "min_angle": min(angles),
            "max_angle": max(angles),
            "center_angle": center_angle,
            "sample_count": len(angles),
            "pixel_positions": list(zip(angles, positions)),
        }
        self._servo_angles[servo_id] = result
        self._report_progress("endpoints", 1.0,
                              f"Servo {servo_id}: centro en {center_angle} deg")
        return result

    def calibrate_all_servos(self, marker_id=0):
        self._running = True
        results = {}
        num_servos = self._arm.num_servos
        for servo_id in range(num_servos):
            if not self._running:
                self._log("Calibracion cancelada")
                return None
            self._report_progress("all_servos", servo_id / num_servos,
                                  f"Calibrando servo {servo_id + 1}/{num_servos}")
            result = self.calibrate_servo_endpoints(servo_id, marker_id=marker_id)
            if result:
                results[servo_id] = result
            else:
                self._log(f"Advertencia: no se pudo calibrar servo {servo_id}")
        self._running = False
        self._report_progress("all_servos", 1.0, "Calibracion completada")
        self._report_result({"type": "endpoints", "data": results})
        return results

    def calibrate_camera_intrinsics(self, checkerboard_size=(7, 6),
                                     square_size=0.025, num_images=10):
        if not self._camera.is_open or not CV2_AVAILABLE:
            self._log("Camara no disponible para calibracion de intrinsecos")
            return False
        self._log(f"Muestra el tablero de ajedrez ({checkerboard_size[0]}x{checkerboard_size[1]})")
        self._log("Mueve el tablero a diferentes posiciones y angulos")
        self._running = True
        obj_points = []
        img_points = []
        objp = np.zeros((checkerboard_size[0] * checkerboard_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:checkerboard_size[0], 0:checkerboard_size[1]].T.reshape(-1, 2)
        objp *= square_size
        collected = 0
        last_capture_time = 0
        while collected < num_images and self._running:
            frame = self._camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ret, corners = cv2.findChessboardCorners(gray, checkerboard_size, None)
            if ret:
                now = time.time()
                if now - last_capture_time < 1.5:
                    time.sleep(0.1)
                    continue
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                obj_points.append(objp)
                img_points.append(corners_refined)
                collected += 1
                last_capture_time = now
                self._report_progress("intrinsics", collected / num_images,
                                      f"Captura {collected}/{num_images}")
                self._log(f"Captura {collected}/{num_images} - tablero detectado")
            time.sleep(0.1)
        self._running = False
        if len(obj_points) < 3:
            self._log("Insuficientes capturas para calibracion de intrinsecos")
            return False
        h, w = gray.shape[:2]
        ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            obj_points, img_points, (w, h), None, None
        )
        if ret:
            self._camera._camera_matrix = camera_matrix
            self._camera._dist_coeffs = dist_coeffs
            self._report_progress("intrinsics", 1.0,
                                  f"Calibracion OK (error: {ret:.4f})")
            self._report_result({
                "type": "intrinsics",
                "reprojection_error": ret,
                "camera_matrix": camera_matrix.tolist(),
                "dist_coeffs": dist_coeffs.tolist(),
            })
            self._log(f"Calibracion de camara exitosa (error: {ret:.4f})")
            return True
        self._log("Calibracion de camara fallo")
        return False

    def measure_arm_angle(self, base_marker_id=0, tip_marker_id=1):
        markers = self._camera.detect_aruco(marker_ids=[base_marker_id, tip_marker_id])
        if not markers or len(markers) < 2:
            return None
        base_pos = None
        tip_pos = None
        for m in markers:
            if m["id"] == base_marker_id:
                base_pos = m["center"]
            elif m["id"] == tip_marker_id:
                tip_pos = m["center"]
        if base_pos is None or tip_pos is None:
            return None
        dx = tip_pos[0] - base_pos[0]
        dy = tip_pos[1] - base_pos[1]
        angle = math.degrees(math.atan2(dy, dx))
        return angle

    def track_end_effector_position(self):
        pos_2d = self._camera.get_tracked_position()
        if pos_2d is None:
            return None
        frame = self._camera.get_frame()
        if frame is None:
            return None
        h, w = frame.shape[:2]
        norm_x = (pos_2d[0] - w / 2) / (w / 2)
        norm_y = (pos_2d[1] - h / 2) / (h / 2)
        return (norm_x, norm_y, 0.0)

    def start_async_calibration(self, calibration_type="endpoints", **kwargs):
        if self._thread and self._thread.is_alive():
            self._log("Calibracion ya en progreso")
            return False
        self._running = True
        if calibration_type == "endpoints":
            target = lambda: self.calibrate_all_servos(**kwargs)
        elif calibration_type == "intrinsics":
            target = lambda: self.calibrate_camera_intrinsics(**kwargs)
        else:
            self._log(f"Tipo de calibracion desconocido: {calibration_type}")
            return False
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return True

    def cancel(self):
        self._running = False
        self._log("Calibracion cancelada")

    def _build_angle_array(self, target_servo, angle):
        angles = list(self._arm.current_angles)
        while len(angles) < self._arm.num_servos:
            angles.append(0)
        angles[target_servo] = max(-90, min(90, angle))
        return angles

    def _find_center_angle(self, angles, positions):
        if len(angles) < 2:
            return angles[0] if angles else 0
        if len(positions[0]) == 2:
            ys = [p[1] for p in positions]
            mid_y = (min(ys) + max(ys)) / 2
            best_idx = min(range(len(ys)), key=lambda i: abs(ys[i] - mid_y))
            return angles[best_idx]
        return angles[len(angles) // 2]

    def save_calibration(self, filepath):
        import json
        data = {
            "servo_calibrations": self._servo_angles,
            "timestamp": time.time(),
        }
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            self._log(f"Calibracion guardada: {filepath}")
            return True
        except Exception as e:
            self._log(f"Error guardando calibracion: {e}")
            return False

    def load_calibration(self, filepath):
        import json
        try:
            with open(filepath) as f:
                data = json.load(f)
            self._servo_angles = data.get("servo_calibrations", {})
            self._log(f"Calibracion cargada: {filepath}")
            return True
        except Exception as e:
            self._log(f"Error cargando calibracion: {e}")
            return False
