import customtkinter as ctk

try:
    import cv2
    from PIL import Image, ImageTk
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class CameraPreviewFrame(ctk.CTkFrame):
    def __init__(self, master, camera_manager, width=320, height=200, **kwargs):
        super().__init__(master, **kwargs)
        self._camera = camera_manager
        self._width = width
        self._height = height
        self._running = False
        self._tracking = False
        self._label = ctk.CTkLabel(self, text="Sin camara", font=("Segoe UI", 10))
        self._label.pack(expand=True, fill="both")
        self._update_job = None

    def start(self):
        if not CV2_AVAILABLE:
            self._label.configure(text="OpenCV no disponible")
            return
        self._running = True
        self._update_frame()

    def stop(self):
        self._running = False
        if self._update_job:
            self.after_cancel(self._update_job)
            self._update_job = None

    def set_tracking(self, tracking):
        self._tracking = tracking

    def _update_frame(self):
        if not self._running:
            return
        frame = self._camera.get_frame()
        if frame is not None:
            try:
                display = frame
                if self._tracking:
                    display = self._camera.draw_tracking_overlay(display)
                rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img = img.resize((self._width, self._height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._label.configure(image=photo, text="")
                self._label._photo = photo
            except Exception:
                pass
        self._update_job = self.after(33, self._update_frame)
