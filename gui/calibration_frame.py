import customtkinter as ctk
from gui.camera_frame import CameraPreviewFrame


class CalibrationFrame(ctk.CTkFrame):
    def __init__(self, master, camera_manager, auto_calibrator, log_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self._camera = camera_manager
        self._calibrator = auto_calibrator
        self._log = log_callback or (lambda m: None)
        self._calibrating = False
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            self, text="CAMARA Y CALIBRACION",
            font=("Segoe UI", 12, "bold"),
        )
        title.grid(row=0, column=0, columnspan=3, pady=(0, 8), sticky="w")

        cam_frame = ctk.CTkFrame(self, fg_color="transparent")
        cam_frame.grid(row=1, column=0, columnspan=3, pady=(0, 6), sticky="ew")
        cam_frame.grid_columnconfigure(1, weight=1)

        cam_label = ctk.CTkLabel(cam_frame, text="Camara:", font=("Segoe UI", 10))
        cam_label.grid(row=0, column=0, padx=(0, 4))

        self._cam_var = ctk.StringVar(value="0")
        self._cam_menu = ctk.CTkOptionMenu(
            cam_frame, variable=self._cam_var,
            values=["0", "1", "2", "3"],
            width=50, font=("Segoe UI", 10),
        )
        self._cam_menu.grid(row=0, column=1, padx=(0, 4))

        self._cam_open_btn = ctk.CTkButton(
            cam_frame, text="Abrir", width=60, height=24,
            font=("Segoe UI", 10),
            fg_color="#51cf66", hover_color="#40c057",
            command=self._on_open_camera,
        )
        self._cam_open_btn.grid(row=0, column=2, padx=(0, 2))

        self._cam_close_btn = ctk.CTkButton(
            cam_frame, text="Cerrar", width=60, height=24,
            font=("Segoe UI", 10),
            fg_color="#868e96",
            state="disabled",
            command=self._on_close_camera,
        )
        self._cam_close_btn.grid(row=0, column=3)

        self._cam_status = ctk.CTkLabel(
            cam_frame, text="Cerrada",
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
        )
        self._cam_status.grid(row=0, column=4, padx=(6, 0))

        self._preview = CameraPreviewFrame(self, self._camera, height=200)
        self._preview.grid(row=2, column=0, columnspan=3, pady=(0, 6), sticky="ew")

        cal_frame = ctk.CTkFrame(self, fg_color="transparent")
        cal_frame.grid(row=3, column=0, columnspan=3, pady=(0, 6), sticky="ew")
        cal_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._cal_intrinsics_btn = ctk.CTkButton(
            cal_frame, text="Cal. Intrinsecos",
            font=("Segoe UI", 10),
            fg_color="#7950f2", hover_color="#6741d9",
            state="disabled",
            command=self._on_calibrate_intrinsics,
        )
        self._cal_intrinsics_btn.grid(row=0, column=0, padx=(0, 2), pady=2, sticky="ew")

        self._cal_endpoints_btn = ctk.CTkButton(
            cal_frame, text="Cal. Servos",
            font=("Segoe UI", 10),
            fg_color="#339af0", hover_color="#228be6",
            state="disabled",
            command=self._on_calibrate_endpoints,
        )
        self._cal_endpoints_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self._cancel_cal_btn = ctk.CTkButton(
            cal_frame, text="Cancelar",
            font=("Segoe UI", 10),
            fg_color="#e03131", hover_color="#c92a2a",
            state="disabled",
            command=self._on_cancel_calibration,
        )
        self._cancel_cal_btn.grid(row=0, column=2, padx=(2, 0), pady=2, sticky="ew")

        track_frame = ctk.CTkFrame(self, fg_color="transparent")
        track_frame.grid(row=4, column=0, columnspan=3, pady=(0, 4), sticky="ew")
        track_frame.grid_columnconfigure(1, weight=1)

        track_label = ctk.CTkLabel(track_frame, text="Tracking:", font=("Segoe UI", 10))
        track_label.grid(row=0, column=0, padx=(0, 4))

        self._track_btn = ctk.CTkButton(
            track_frame, text="Iniciar", width=60, height=24,
            font=("Segoe UI", 10),
            fg_color="#fcc419", hover_color="#fab005",
            text_color="#212529",
            state="disabled",
            command=self._on_toggle_tracking,
        )
        self._track_btn.grid(row=0, column=1, padx=(0, 4))

        self._track_pos_label = ctk.CTkLabel(
            track_frame, text="",
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
        )
        self._track_pos_label.grid(row=0, column=2, sticky="w")

        self._progress_label = ctk.CTkLabel(
            self, text="",
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
        )
        self._progress_label.grid(row=5, column=0, columnspan=3, pady=(2, 0), sticky="w")

        self._progress_bar = ctk.CTkProgressBar(self, height=6)
        self._progress_bar.grid(row=6, column=0, columnspan=3, pady=(2, 0), sticky="ew")
        self._progress_bar.set(0)

    def _on_open_camera(self):
        idx = int(self._cam_var.get())
        if self._camera.open(idx):
            self._cam_open_btn.configure(state="disabled")
            self._cam_close_btn.configure(state="normal")
            self._cam_status.configure(text="Abierta", text_color="#51cf66")
            self._cal_intrinsics_btn.configure(state="normal")
            self._cal_endpoints_btn.configure(state="normal")
            self._track_btn.configure(state="normal")
            self._preview.start()
        else:
            self._cam_status.configure(text="Error", text_color="#e03131")

    def _on_close_camera(self):
        self._preview.stop()
        self._camera.close()
        self._cam_open_btn.configure(state="normal")
        self._cam_close_btn.configure(state="disabled")
        self._cam_status.configure(text="Cerrada", text_color=("#868e96", "#909296"))
        self._cal_intrinsics_btn.configure(state="disabled")
        self._cal_endpoints_btn.configure(state="disabled")
        self._track_btn.configure(state="disabled")
        self._track_btn.configure(text="Iniciar")
        self._track_pos_label.configure(text="")

    def _on_calibrate_intrinsics(self):
        self._set_calibrating(True)
        self._calibrator.set_progress_callback(self._on_cal_progress)
        self._calibrator.set_result_callback(self._on_cal_result)
        self._calibrator.start_async_calibration("intrinsics")

    def _on_calibrate_endpoints(self):
        self._set_calibrating(True)
        self._calibrator.set_progress_callback(self._on_cal_progress)
        self._calibrator.set_result_callback(self._on_cal_result)
        self._calibrator.start_async_calibration("endpoints")

    def _on_cancel_calibration(self):
        self._calibrator.cancel()
        self._set_calibrating(False)

    def _on_toggle_tracking(self):
        if self._camera.is_tracking:
            self._camera.stop_color_tracking()
            self._track_btn.configure(text="Iniciar")
            self._track_pos_label.configure(text="")
            self._preview.set_tracking(False)
        else:
            self._camera.start_color_tracking()
            self._track_btn.configure(text="Detener", fg_color="#e03131")
            self._preview.set_tracking(True)
            self._poll_tracking()

    def _poll_tracking(self):
        if not self._camera.is_tracking:
            return
        pos = self._camera.get_tracked_position()
        if pos:
            self._track_pos_label.configure(text=f"({pos[0]}, {pos[1]})", text_color="#51cf66")
        else:
            self._track_pos_label.configure(text="Sin target", text_color=("#868e96", "#909296"))
        self.after(100, self._poll_tracking)

    def _set_calibrating(self, calibrating):
        self._calibrating = calibrating
        state = "disabled" if calibrating else "normal"
        self._cal_intrinsics_btn.configure(state=state)
        self._cal_endpoints_btn.configure(state=state)
        self._cancel_cal_btn.configure(state="normal" if calibrating else "disabled")

    def _on_cal_progress(self, stage, progress, detail):
        self.after(0, lambda: self._update_progress(stage, progress, detail))

    def _update_progress(self, stage, progress, detail):
        self._progress_bar.set(progress)
        self._progress_label.configure(text=detail)

    def _on_cal_result(self, result):
        self.after(0, lambda: self._handle_cal_result(result))

    def _handle_cal_result(self, result):
        self._set_calibrating(False)
        self._progress_bar.set(1.0)
        cal_type = result.get("type", "")
        if cal_type == "intrinsics":
            err = result.get("reprojection_error", 0)
            self._progress_label.configure(
                text=f"Intrinsecos OK (error: {err:.4f})", text_color="#51cf66"
            )
        elif cal_type == "endpoints":
            data = result.get("data", {})
            self._progress_label.configure(
                text=f"Servos calibrados: {len(data)}/{self._calibrator._arm.num_servos}",
                text_color="#51cf66",
            )

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        if not enabled:
            self._cam_open_btn.configure(state="disabled")
        else:
            if self._camera.is_open:
                self._cam_close_btn.configure(state="normal")
                self._cal_intrinsics_btn.configure(state="normal" if not self._calibrating else "disabled")
                self._cal_endpoints_btn.configure(state="normal" if not self._calibrating else "disabled")
                self._track_btn.configure(state="normal")
            else:
                self._cam_open_btn.configure(state="normal")
