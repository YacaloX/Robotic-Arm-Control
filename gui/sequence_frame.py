import customtkinter as ctk
from tkinter import messagebox, filedialog
from utils.theme import SERVO_NAMES


class SequenceFrame(ctk.CTkFrame):
    KEYFRAME_THRESHOLD = 3
    FORCE_SAVE_INTERVAL = 10

    def __init__(self, master, robot_arm, sequence_player, control_frame, log_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self._arm = robot_arm
        self._seq = sequence_player
        self._control = control_frame
        self._log = log_callback or (lambda m: None)
        self._current_angles = [0] * self._arm.num_servos
        self._recording = False
        self._recorded_frames = []
        self._recording_interval = 100
        self._record_timer_id = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self._create_posture_section()
        self._create_sequence_section()
        self._create_recording_section()

    def _create_posture_section(self):
        section = ctk.CTkFrame(self, fg_color="transparent")
        section.grid(row=0, column=0, pady=(0, 12), sticky="ew")
        section.grid_columnconfigure((0, 1, 2), weight=1)
        title = ctk.CTkLabel(section, text="POSTURAS", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=3, pady=(0, 6), sticky="w")
        self._home_btn = ctk.CTkButton(
            section, text="⌂  Home", command=self.home,
            font=("Segoe UI", 11), fg_color="#2f9e44", hover_color="#2b8a3e",
        )
        self._home_btn.grid(row=1, column=0, padx=(0, 3), pady=2, sticky="ew")
        self._save_posture_btn = ctk.CTkButton(
            section, text="💾  Guardar", command=self.save_posture,
            font=("Segoe UI", 11),
        )
        self._save_posture_btn.grid(row=1, column=1, padx=3, pady=2, sticky="ew")
        self._load_posture_btn = ctk.CTkButton(
            section, text="📂  Cargar", command=self.load_posture,
            font=("Segoe UI", 11),
        )
        self._load_posture_btn.grid(row=1, column=2, padx=(3, 0), pady=2, sticky="ew")

    def _create_sequence_section(self):
        section = ctk.CTkFrame(self, fg_color="transparent")
        section.grid(row=1, column=0, pady=0, sticky="ew")
        section.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(section, text="SECUENCIA", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=5, pady=(0, 6), sticky="w")
        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=1, column=0, columnspan=5, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self._add_btn = ctk.CTkButton(
            btn_frame, text="✚  Agregar", command=self.add_posture,
            font=("Segoe UI", 10), fg_color="#7950f2", hover_color="#6741d9",
        )
        self._add_btn.grid(row=0, column=0, padx=(0, 2), pady=2, sticky="ew")
        self._del_btn = ctk.CTkButton(
            btn_frame, text="✕  Eliminar", command=self._remove_posture,
            font=("Segoe UI", 10), fg_color="#e03131", hover_color="#c92a2a",
        )
        self._del_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        self._save_seq_btn = ctk.CTkButton(
            btn_frame, text="💾  Guardar", command=self.save_sequence,
            font=("Segoe UI", 10),
        )
        self._save_seq_btn.grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        self._load_seq_btn = ctk.CTkButton(
            btn_frame, text="📂  Cargar", command=self.load_sequence,
            font=("Segoe UI", 10),
        )
        self._load_seq_btn.grid(row=0, column=3, padx=2, pady=2, sticky="ew")
        self._clear_btn = ctk.CTkButton(
            btn_frame, text="🗑  Vaciar", command=self._clear_sequence,
            font=("Segoe UI", 10), fg_color="#e03131", hover_color="#c92a2a",
        )
        self._clear_btn.grid(row=0, column=4, padx=(2, 0), pady=2, sticky="ew")
        list_frame = ctk.CTkFrame(section, fg_color="transparent")
        list_frame.grid(row=2, column=0, columnspan=5, pady=(6, 4), sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self._listbox = ctk.CTkTextbox(list_frame, height=110, font=("Consolas", 10))
        self._listbox.grid(row=0, column=0, sticky="ew")
        self._listbox.configure(state="disabled")
        speed_frame = ctk.CTkFrame(section, fg_color="transparent")
        speed_frame.grid(row=3, column=0, columnspan=5, pady=(2, 4), sticky="ew")
        speed_frame.grid_columnconfigure(1, weight=1)
        speed_label = ctk.CTkLabel(speed_frame, text="Velocidad:", font=("Segoe UI", 10))
        speed_label.grid(row=0, column=0, padx=(0, 6), pady=2)
        self._speed_var = ctk.DoubleVar(value=1.0)
        self._speed_slider = ctk.CTkSlider(
            speed_frame, from_=0.5, to=5.0, number_of_steps=18,
            variable=self._speed_var,
        )
        self._speed_slider.grid(row=0, column=1, padx=(0, 6), pady=2, sticky="ew")
        self._speed_value = ctk.CTkLabel(speed_frame, text="1.0×", font=("Segoe UI", 10, "bold"), width=36)
        self._speed_value.grid(row=0, column=2, padx=0, pady=2)
        self._speed_slider.configure(command=self._on_speed_change)
        play_frame = ctk.CTkFrame(section, fg_color="transparent")
        play_frame.grid(row=4, column=0, columnspan=5, pady=(2, 0), sticky="ew")
        play_frame.grid_columnconfigure((0, 1), weight=1)
        self._play_btn = ctk.CTkButton(
            play_frame, text="▶  Reproducir", command=self.play,
            font=("Segoe UI", 11), fg_color="#2f9e44", hover_color="#2b8a3e",
        )
        self._play_btn.grid(row=0, column=0, padx=(0, 3), pady=2, sticky="ew")
        self._stop_btn = ctk.CTkButton(
            play_frame, text="■  Detener", command=self.stop,
            font=("Segoe UI", 11), fg_color="#e03131", hover_color="#c92a2a",
            state="disabled",
        )
        self._stop_btn.grid(row=0, column=1, padx=(3, 0), pady=2, sticky="ew")
        self._update_buttons_state()

    def _create_recording_section(self):
        section = ctk.CTkFrame(self, fg_color="transparent")
        section.grid(row=2, column=0, pady=(6, 0), sticky="ew")
        section.grid_columnconfigure(2, weight=1)
        title = ctk.CTkLabel(section, text="GRABACIÓN", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=4, pady=(0, 4), sticky="w")
        self._record_btn = ctk.CTkButton(
            section, text="🔴  Grabar", command=self._toggle_recording,
            font=("Segoe UI", 11), fg_color="#e03131", hover_color="#c92a2a",
            width=90,
        )
        self._record_btn.grid(row=1, column=0, padx=(0, 4), pady=2)
        int_label = ctk.CTkLabel(section, text="Int:", font=("Segoe UI", 10))
        int_label.grid(row=1, column=1, padx=(0, 2), pady=2)
        self._int_var = ctk.IntVar(value=100)
        self._int_slider = ctk.CTkSlider(
            section, from_=50, to=500, number_of_steps=18,
            variable=self._int_var,
            width=80,
        )
        self._int_slider.grid(row=1, column=2, padx=(0, 2), pady=2, sticky="ew")
        self._int_label = ctk.CTkLabel(section, text="100ms", font=("Segoe UI", 10, "bold"), width=40)
        self._int_label.grid(row=1, column=3, padx=0, pady=2)
        self._int_slider.configure(command=self._on_interval_change)

    def _on_interval_change(self, value):
        ms = int(round(value / 50) * 50)
        ms = max(50, min(500, ms))
        self._int_label.configure(text=f"{ms}ms")
        self._recording_interval = ms

    def _on_speed_change(self, value):
        self._speed_value.configure(text=f"{value:.1f}×")

    def home(self):
        self._arm.home_ramped(step_size=1, delay_ms=10,
                              callback=lambda: self._control.set_angles([0] * self._arm.num_servos))

    def save_posture(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Guardar postura",
        )
        if path:
            angles = self._control.get_angles()
            self._seq.save_posture(angles, path)

    def load_posture(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Cargar postura",
        )
        if path:
            angles = self._seq.load_posture(path)
            if angles:
                self._arm.move_all(angles)
                self._control.set_angles(angles)

    def add_posture(self):
        angles = self._control.get_angles()
        idx = self._seq.add_posture(angles)
        self._refresh_listbox()
        self._update_buttons_state()

    def _remove_posture(self):
        selection = self._get_selected_index()
        if selection is not None:
            if self._seq.remove_posture(selection):
                self._refresh_listbox()
                self._update_buttons_state()

    def save_sequence(self):
        if self._seq.posture_count == 0:
            messagebox.showwarning("Secuencia vacía", "No hay posturas para guardar")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Guardar secuencia",
        )
        if path:
            self._seq.save(path)

    def load_sequence(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Cargar secuencia",
        )
        if path:
            if self._seq.load(path):
                self._refresh_listbox()
                self._update_buttons_state()

    def _clear_sequence(self):
        if self._seq.posture_count > 0:
            if messagebox.askyesno("Vaciar secuencia", "¿Eliminar todas las posturas?"):
                self._seq.clear()
                self._refresh_listbox()
                self._update_buttons_state()

    def play(self):
        self._seq.play(speed=self._speed_var.get())
        self._play_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._check_playback()

    def _check_playback(self):
        if self._seq.is_playing:
            self.after(100, self._check_playback)
        else:
            self._play_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")

    def stop(self):
        self._seq.stop()

    def _get_selected_index(self):
        try:
            content = self._listbox.get("1.0", "end-1c").strip()
            if not content:
                return None
            sel = self._listbox.tag_ranges("sel")
            if sel:
                line = self._listbox.index(sel[0]).split(".")[0]
            else:
                line = self._listbox.index("insert").split(".")[0]
            return int(line) - 1
        except (ValueError, IndexError):
            return None

    def _refresh_listbox(self):
        self._listbox.configure(state="normal")
        self._listbox.delete("1.0", "end")
        for i, p in enumerate(self._seq.postures):
            angles_str = " ".join(f"{a:3d}" for a in p["angles"])
            self._listbox.insert("end", f"{i+1:2d}. {p['name']:<20s} [{angles_str}]\n")
        self._listbox.configure(state="disabled")

    def _update_buttons_state(self):
        has_postures = self._seq.posture_count > 0
        state = "normal" if has_postures else "disabled"
        self._del_btn.configure(state=state)
        self._save_seq_btn.configure(state=state)
        self._play_btn.configure(state=state if not self._seq.is_playing else "disabled")

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for btn in [self._home_btn, self._save_posture_btn, self._load_posture_btn,
                     self._add_btn]:
            btn.configure(state=state)
        if enabled:
            self._update_buttons_state()
            stop_state = "normal" if self._seq.is_playing else "disabled"
            self._stop_btn.configure(state=stop_state)
        else:
            self._del_btn.configure(state=state)
            self._save_seq_btn.configure(state=state)
            self._load_seq_btn.configure(state=state)
            self._clear_btn.configure(state=state)
            self._play_btn.configure(state=state)
            self._stop_btn.configure(state="disabled")
        if not enabled and self._recording:
            self._stop_recording()

    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self._recorded_frames = []
        self._record_btn.configure(text="⏺ Grabando...")
        self._int_slider.configure(state="disabled")
        self._log("Grabación iniciada")
        self._record_timer()

    def _record_timer(self):
        if not self._recording:
            return
        angles = self._control.get_angles()
        self._recorded_frames.append(angles)
        self._record_timer_id = self.after(self._recording_interval, self._record_timer)

    def _stop_recording(self):
        self._recording = False
        if self._record_timer_id:
            self.after_cancel(self._record_timer_id)
            self._record_timer_id = None
        self._record_btn.configure(text="🔴  Grabar")
        self._int_slider.configure(state="normal")
        self._process_recorded_frames()

    def _process_recorded_frames(self):
        frames = self._recorded_frames
        if len(frames) < 2:
            self._log("Grabación: muy pocos frames (mínimo 2)")
            return
        num = self._arm.num_servos
        keyframes = [frames[0]]
        last_saved = frames[0]
        frames_since_save = 0
        for angles in frames[1:]:
            frames_since_save += 1
            change = max(abs(angles[i] - last_saved[i]) for i in range(num))
            force_save = frames_since_save >= self.FORCE_SAVE_INTERVAL
            if change >= self.KEYFRAME_THRESHOLD or force_save:
                keyframes.append(angles)
                last_saved = angles
                frames_since_save = 0
        if len(keyframes) < 2:
            keyframes.append(frames[-1])
        for i, angles in enumerate(keyframes):
            self._seq.add_posture(angles, f"Frame {i+1}")
        self._refresh_listbox()
        self._update_buttons_state()
        saved = len(frames)
        compressed = len(keyframes)
        ratio = (1 - compressed / saved) * 100 if saved > 0 else 0
        self._log(f"Grabación: {saved} frames → {compressed} keyframes ({ratio:.0f}% compresión)")
