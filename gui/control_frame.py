import customtkinter as ctk
from utils.config_manager import get_servo_names


class ControlFrame(ctk.CTkFrame):
    FINE_STEP = 10

    def __init__(self, master, robot_arm, **kwargs):
        super().__init__(master, **kwargs)
        self._arm = robot_arm
        self._sliders = []
        self._value_labels = []
        self._name_labels = []
        self._slider_rows = []
        self._dec_btns = []
        self._inc_btns = []
        self._enabled = False
        self._controller_active = False
        self._num_servos = 0
        self._build_ui()

    def _build_ui(self):
        self._title = ctk.CTkLabel(self, text="SERVOS", font=("Segoe UI", 12, "bold"))
        self._title.grid(row=0, column=0, columnspan=5, pady=(0, 10), sticky="w")
        self._rebuild_sliders()

    def _rebuild_sliders(self):
        for row in self._slider_rows:
            for w in row:
                w.destroy()
        self._sliders.clear()
        self._value_labels.clear()
        self._name_labels.clear()
        self._dec_btns.clear()
        self._inc_btns.clear()
        self._slider_rows.clear()

        num = self._arm.num_servos
        self._num_servos = num
        names = get_servo_names(num)
        colors = ["#ff6b6b", "#fcc419", "#51cf66", "#339af0", "#cc5de8", "#ff922b"]

        for i in range(num):
            row_widgets = []
            row = i + 1
            self.grid_rowconfigure(row, weight=0, pad=4)

            name_label = ctk.CTkLabel(
                self, text=names[i] if i < len(names) else f"Servo {i + 1}",
                font=("Segoe UI", 11),
                width=130, anchor="w",
            )
            name_label.grid(row=row, column=0, padx=(0, 2), pady=3, sticky="w")
            row_widgets.append(name_label)
            self._name_labels.append(name_label)

            value_label = ctk.CTkLabel(
                self, text="0", font=("Segoe UI", 12, "bold"),
                width=32, anchor="center",
            )
            value_label.grid(row=row, column=1, padx=(0, 2), pady=3)
            row_widgets.append(value_label)
            self._value_labels.append(value_label)

            dec_btn = ctk.CTkButton(
                self, text="−10", width=34, height=22,
                font=("Segoe UI", 9, "bold"),
                fg_color=("gray80", "gray25"), hover_color=("#e9ecef", "#495057"),
                text_color=("gray10", "gray90"),
                command=lambda idx=i: self._jog(idx, -self.FINE_STEP),
            )
            dec_btn.grid(row=row, column=2, padx=0, pady=3)
            row_widgets.append(dec_btn)
            self._dec_btns.append(dec_btn)

            inc_btn = ctk.CTkButton(
                self, text="+10", width=34, height=22,
                font=("Segoe UI", 9, "bold"),
                fg_color=("gray80", "gray25"), hover_color=("#e9ecef", "#495057"),
                text_color=("gray10", "gray90"),
                command=lambda idx=i: self._jog(idx, self.FINE_STEP),
            )
            inc_btn.grid(row=row, column=3, padx=(2, 0), pady=3)
            row_widgets.append(inc_btn)
            self._inc_btns.append(inc_btn)

            servo = self._arm.servos[i] if i < len(self._arm.servos) else None
            s_min = servo["min"] if servo else -90
            s_max = servo["max"] if servo else 90
            num_steps = s_max - s_min

            slider = ctk.CTkSlider(
                self, from_=s_min, to=s_max, number_of_steps=num_steps,
                command=lambda v, idx=i: self._on_slider_change(idx, v),
                progress_color=colors[i] if i < len(colors) else colors[-1],
                button_color=colors[i] if i < len(colors) else colors[-1],
                button_hover_color=colors[i] if i < len(colors) else colors[-1],
                height=18,
            )
            slider.set(0)
            slider.grid(row=row, column=4, padx=(2, 0), pady=3, sticky="ew")
            row_widgets.append(slider)
            self._sliders.append(slider)
            self._slider_rows.append(row_widgets)

        self.grid_columnconfigure(4, weight=1)
        self._configure_sliders_state()

    def _jog(self, idx, delta):
        if not self._enabled or self._controller_active:
            return
        current = int(round(self._sliders[idx].get()))
        servo = self._arm.servos[idx] if idx < len(self._arm.servos) else None
        s_min = servo["min"] if servo else -90
        s_max = servo["max"] if servo else 90
        new = max(s_min, min(s_max, current + delta))
        self._sliders[idx].set(new)
        self._value_labels[idx].configure(text=str(new))
        angles = self.get_angles()
        self._arm.move_all_ramped(angles, step_size=1, delay_ms=10)

    def _on_slider_change(self, idx, value):
        angle = int(round(value))
        self._value_labels[idx].configure(text=str(angle))
        if self._enabled and not self._controller_active:
            self._arm.cancel_ramp()
            angles = self.get_angles()
            self._arm.move_all_ramped(angles, step_size=1, delay_ms=10)

    def set_angle(self, idx, angle):
        if 0 <= idx < len(self._sliders):
            servo = self._arm.servos[idx] if idx < len(self._arm.servos) else None
            s_min = servo["min"] if servo else -90
            s_max = servo["max"] if servo else 90
            angle = max(s_min, min(s_max, int(round(angle))))
            self._sliders[idx].set(angle)
            self._value_labels[idx].configure(text=str(angle))

    def set_angles(self, angles):
        for i, a in enumerate(angles):
            if i < len(self._sliders):
                self.set_angle(i, a)

    def get_angles(self):
        return [int(round(s.get())) for s in self._sliders]

    def set_enabled(self, enabled):
        self._enabled = enabled
        self._configure_sliders_state()

    def set_angles_silent(self, angles):
        for i, a in enumerate(angles):
            if i < len(self._sliders):
                servo = self._arm.servos[i] if i < len(self._arm.servos) else None
                s_min = servo["min"] if servo else -90
                s_max = servo["max"] if servo else 90
                a = max(s_min, min(s_max, int(round(a))))
                self._sliders[i].set(a)
                self._value_labels[i].configure(text=str(a))

    def set_controller_active(self, active):
        self._controller_active = active

    def _configure_sliders_state(self):
        state = "normal" if self._enabled else "disabled"
        for s in self._sliders:
            s.configure(state=state)
        for b in self._dec_btns:
            b.configure(state=state)
        for b in self._inc_btns:
            b.configure(state=state)
        for lbl in self._value_labels:
            lbl.configure(text_color=("#212529", "#c1c2c5") if self._enabled else ("#adb5bd", "#5c5f66"))

    def refresh(self):
        self._rebuild_sliders()
