import threading
import time
from typing import Optional, Callable, Tuple, List

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class CameraManager:
    ARUCO_DICT = {
        "4x4": cv2.aruco.DICT_4X4_50 if CV2_AVAILABLE else None,
        "5x5": cv2.aruco.DICT_5X5_100 if CV2_AVAILABLE else None,
        "6x6": cv2.aruco.DICT_6X6_250 if CV2_AVAILABLE else None,
        "7x7": cv2.aruco.DICT_7X7_1000 if CV2_AVAILABLE else None,
    }

    def __init__(self, camera_index: int = 0, log_callback: Optional[Callable] = None):
        self._camera_index = camera_index
        self._log = log_callback or (lambda m: None)
        self._cap = None
        self._running = False
        self._frame = None
        self._frame_lock = threading.Lock()
        self._reader_thread = None
        self._aruco_dict_type = self.ARUCO_DICT.get("6x6")
        self._aruco_detector = None
        self._calibration_points = []
        self._camera_matrix = None
        self._dist_coeffs = None
        self._color_lower = None
        self._color_upper = None
        self._tracking_active = False
        self._tracked_position = None

    @property
    def available(self) -> bool:
        return CV2_AVAILABLE

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def is_tracking(self) -> bool:
        return self._tracking_active

    def open(self, camera_index: Optional[int] = None) -> bool:
        if not CV2_AVAILABLE:
            self._log("OpenCV no disponible. Instala: pip install opencv-python")
            return False
        if camera_index is not None:
            self._camera_index = camera_index
        try:
            self._cap = cv2.VideoCapture(self._camera_index)
            if not self._cap.isOpened():
                self._log(f"No se pudo abrir camara {self._camera_index}")
                self._cap = None
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._cap.set(cv2.CAP_PROP_FPS, 30)
            self._running = True
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            self._log(f"Camara {self._camera_index} abierta")
            return True
        except Exception as e:
            self._log(f"Error abriendo camara: {e}")
            return False

    def close(self):
        self._running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._frame = None
        self._tracking_active = False
        self._log("Camara cerrada")

    def _reader_loop(self):
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._frame_lock:
                    self._frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self) -> Optional[object]:
        with self._frame_lock:
            if self._frame is not None:
                return self._frame.copy()
        return None

    def get_frame_rgb(self) -> Optional[Tuple[object, object]]:
        frame = self.get_frame()
        if frame is None:
            return None, None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame, rgb

    def detect_aruco(self, marker_ids: Optional[List[int]] = None) -> Optional[List[dict]]:
        frame = self.get_frame()
        if frame is None:
            return None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if self._aruco_detector is None:
                if self._aruco_dict_type is None:
                    return None
                aruco_dict = cv2.aruco.getPredefinedDictionary(self._aruco_dict_type)
                parameters = cv2.aruco.DetectorParameters()
                self._aruco_detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
            corners, ids, rejected = self._aruco_detector.detectMarkers(gray)
            if ids is None:
                return []
            results = []
            for i, marker_id in enumerate(ids.flatten()):
                if marker_ids is not None and marker_id not in marker_ids:
                    continue
                corner_pts = corners[i][0]
                center_x = int(corner_pts[:, 0].mean())
                center_y = int(corner_pts[:, 1].mean())
                results.append({
                    "id": int(marker_id),
                    "corners": corner_pts.tolist(),
                    "center": (center_x, center_y),
                })
            return results
        except Exception as e:
            self._log(f"Error detectando ArUco: {e}")
            return None

    def calibrate_from_points(self, image_points: List[List[Tuple[float, float]]],
                              world_points: List[List[Tuple[float, float]]],
                              image_size: Tuple[int, int]) -> bool:
        if not CV2_AVAILABLE:
            return False
        try:
            obj_points = []
            img_points = []
            for img_pts, world_pts in zip(image_points, world_points):
                obj_points.append(np.array(world_pts, dtype=np.float32))
                img_points.append(np.array(img_pts, dtype=np.float32))
            ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
                obj_points, img_points, image_size, None, None
            )
            if ret:
                self._camera_matrix = camera_matrix
                self._dist_coeffs = dist_coeffs
                self._log(f"Calibracion exitosa (reproyeccion error: {ret:.4f})")
                return True
            return False
        except Exception as e:
            self._log(f"Error en calibracion: {e}")
            return False

    def estimate_pose(self, corners, marker_length: float = 0.025):
        if self._camera_matrix is None or self._dist_coeffs is None:
            return None
        try:
            obj_points = np.array([
                [-marker_length / 2,  marker_length / 2, 0],
                [ marker_length / 2,  marker_length / 2, 0],
                [ marker_length / 2, -marker_length / 2, 0],
                [-marker_length / 2, -marker_length / 2, 0],
            ], dtype=np.float32)
            img_points = np.array(corners, dtype=np.float32)
            success, rvec, tvec = cv2.solvePnP(
                obj_points, img_points, self._camera_matrix, self._dist_coeffs
            )
            if success:
                return {
                    "rvec": rvec.flatten().tolist(),
                    "tvec": tvec.flatten().tolist(),
                }
        except Exception:
            pass
        return None

    def start_color_tracking(self, hue_range: Tuple[int, int] = (0, 180),
                             sat_range: Tuple[int, int] = (100, 255),
                             val_range: Tuple[int, int] = (100, 255)):
        self._color_lower = np.array([hue_range[0], sat_range[0], val_range[0]])
        self._color_upper = np.array([hue_range[1], sat_range[1], val_range[1]])
        self._tracking_active = True
        self._log("Tracking de color activado")

    def stop_color_tracking(self):
        self._tracking_active = False
        self._tracked_position = None
        self._log("Tracking de color desactivado")

    def get_tracked_position(self) -> Optional[Tuple[int, int]]:
        if not self._tracking_active:
            return None
        frame = self.get_frame()
        if frame is None or self._color_lower is None:
            return None
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, self._color_lower, self._color_upper)
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                self._tracked_position = None
                return None
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) < 100:
                self._tracked_position = None
                return None
            M = cv2.moments(largest)
            if M["m00"] == 0:
                self._tracked_position = None
                return None
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            self._tracked_position = (cx, cy)
            return (cx, cy)
        except Exception:
            self._tracked_position = None
            return None

    def draw_tracking_overlay(self, frame) -> object:
        if frame is None or not CV2_AVAILABLE:
            return frame
        overlay = frame.copy()
        if self._tracking_active and self._tracked_position:
            cx, cy = self._tracked_position
            cv2.circle(overlay, (cx, cy), 20, (0, 255, 0), 2)
            cv2.circle(overlay, (cx, cy), 5, (0, 255, 0), -1)
            cv2.putText(overlay, f"({cx}, {cy})", (cx + 25, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return overlay

    def draw_aruco_overlay(self, frame, markers: Optional[List[dict]] = None) -> object:
        if frame is None or not CV2_AVAILABLE or markers is None:
            return frame
        overlay = frame.copy()
        for marker in markers:
            corners = np.array(marker["corners"], dtype=np.int32)
            cv2.polylines(overlay, [corners], True, (0, 255, 255), 2)
            cx, cy = marker["center"]
            cv2.putText(overlay, f"ID:{marker['id']}", (cx - 15, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            if self._camera_matrix is not None:
                pose = self.estimate_pose(marker["corners"])
                if pose:
                    tvec = pose["tvec"]
                    cv2.putText(overlay, f"Z:{tvec[2]:.3f}m", (cx - 15, cy + 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 255), 1)
        return overlay

    def get_frame_as_photo(self) -> Optional[object]:
        if not CV2_AVAILABLE:
            return None
        frame = self.get_frame()
        if frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def list_cameras(max_test: int = 5) -> List[int]:
        available = []
        if not CV2_AVAILABLE:
            return available
        for i in range(max_test):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        available.append(i)
                    cap.release()
            except Exception:
                pass
        return available
