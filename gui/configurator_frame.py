import customtkinter as ctk
from utils.config_manager import load_config, save_config, get_servo_names, get_pin_pool


class ConfiguratorFrame(ctk.CTkToplevel):
    def __init__(self, master, transport, robot_arm, on_apply=None, **kwargs):
        super().__init__(master, **kwargs)
        self._transport = transport
        self._arm = robot_arm
        self._on_apply = on_apply
        self._config = load_config()
        self._pin_pool = get_pin_pool()
        self._pin_vars = []
        self._result = None

        self.title("Configuración del Brazo Robótico")
        self.geometry("520x520")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._build_ui()
        self._load_config_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        dof_frame = ctk.CTkFrame(self, fg_color="transparent")
        dof_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        dof_frame.grid_columnconfigure(1, weight=1)

        dof_label = ctk.CTkLabel(
            dof_frame, text="Grados de Libertad (DOF):",
            font=("Segoe UI", 13, "bold"),
        )
        dof_label.grid(row=0, column=0, padx=(0, 12), pady=4, sticky="w")

        self._dof_var = ctk.IntVar(value=6)
        self._dof_slider = ctk.CTkSlider(
            dof_frame, from_=3, to=6, number_of_steps=3,
            variable=self._dof_var,
            command=self._on_dof_change,
            height=20,
        )
        self._dof_slider.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="ew")

        self._dof_value_label = ctk.CTkLabel(
            dof_frame, text="6 DOF", font=("Segoe UI", 13, "bold"),
            width=60,
        )
        self._dof_value_label.grid(row=0, column=2, padx=0, pady=4)

        board_frame = ctk.CTkFrame(self, fg_color="transparent")
        board_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        board_frame.grid_columnconfigure(1, weight=1)

        board_label = ctk.CTkLabel(
            board_frame, text="Placa detectada:",
            font=("Segoe UI", 11),
        )
        board_label.grid(row=0, column=0, padx=(0, 8), pady=2, sticky="w")

        self._board_status = ctk.CTkLabel(
            board_frame, text="No conectada",
            font=("Segoe UI", 11, "bold"),
            text_color=("#868e96", "#909296"),
        )
        self._board_status.grid(row=0, column=1, padx=0, pady=2, sticky="w")

        pins_header = ctk.CTkLabel(
            self, text="Asignación de Pines PWM:",
            font=("Segoe UI", 12, "bold"),
        )
        pins_header.grid(row=2, column=0, padx=16, pady=(8, 4), sticky="w")

        self._pins_container = ctk.CTkScrollableFrame(self, height=200)
        self._pins_container.grid(row=3, column=0, padx=16, pady=(0, 12), sticky="nsew")
        self._pins_container.grid_columnconfigure(2, weight=1)

        self._build_pin_rows()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._cancel_btn = ctk.CTkButton(
            btn_frame, text="Cancelar", command=self._on_cancel,
            font=("Segoe UI", 11), fg_color="#e03131", hover_color="#c92a2a",
        )
        self._cancel_btn.grid(row=0, column=0, padx=(0, 4), pady=4, sticky="ew")

        self._test_btn = ctk.CTkButton(
            btn_frame, text="Test Servos", command=self._test_servos,
            font=("Segoe UI", 11), fg_color="#fcc419", hover_color="#fab005",
            text_color="#212529",
        )
        self._test_btn.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        self._apply_btn = ctk.CTkButton(
            btn_frame, text="Aplicar", command=self._apply_config,
            font=("Segoe UI", 11), fg_color="#2f9e44", hover_color="#2b8a3e",
        )
        self._apply_btn.grid(row=0, column=2, padx=(4, 0), pady=4, sticky="ew")

    def _build_pin_rows(self):
        for w in self._pins_container.winfo_children():
            w.destroy()
        self._pin_vars.clear()

        dof = self._dof_var.get()
        names = get_servo_names(dof)
        colors = ["#ff6b6b", "#fcc419", "#51cf66", "#339af0", "#cc5de8", "#ff922b"]

        for i in range(dof):
            row_frame = ctk.CTkFrame(self._pins_container, fg_color="transparent")
            row_frame.grid(row=i, column=0, padx=4, pady=3, sticky="ew")
            row_frame.grid_columnconfigure(2, weight=1)

            idx_label = ctk.CTkLabel(
                row_frame, text=f"S{i + 1}:",
                font=("Segoe UI", 11, "bold"),
                width=24, text_color=colors[i],
            )
            idx_label.grid(row=0, column=0, padx=(0, 4), pady=2)

            name_label = ctk.CTkLabel(
                row_frame, text=names[i],
                font=("Segoe UI", 11),
                width=140, anchor="w",
            )
            name_label.grid(row=0, column=1, padx=(0, 8), pady=2, sticky="w")

            pin_var = ctk.StringVar(value=str(self._pin_pool[i] if i < len(self._pin_pool) else self._pin_pool[0]))
            pin_menu = ctk.CTkOptionMenu(
                row_frame, variable=pin_var,
                values=[str(p) for p in self._pin_pool],
                width=80, font=("Segoe UI", 11),
            )
            pin_menu.grid(row=0, column=2, padx=0, pady=2, sticky="w")
            self._pin_vars.append(pin_var)

    def _on_dof_change(self, value):
        dof = int(round(value))
        self._dof_value_label.configure(text=f"{dof} DOF")
        self._build_pin_rows()

    def _load_config_ui(self):
        dof = self._config.get("dof", 6)
        self._dof_var.set(dof)
        self._dof_slider.set(dof)
        self._dof_value_label.configure(text=f"{dof} DOF")

        saved_pins = self._config.get("pins", [])
        for i, var in enumerate(self._pin_vars):
            if i < len(saved_pins):
                var.set(str(saved_pins[i]))

        if self._transport is not None and self._transport.is_connected:
            self._board_status.configure(
                text=f"ESP32 DevKit v1 ({self._transport.port})",
                text_color="#51cf66",
            )
            self._test_btn.configure(state="normal")
        else:
            self._board_status.configure(text="No conectada")

    def _test_servos(self):
        if self._transport is None or not self._transport.is_connected:
            return
        dof = self._dof_var.get()
        pins = [int(v.get()) for v in self._pin_vars[:dof]]
        self._test_btn.configure(state="disabled", text="Probando...")

        self._transport.send_config(dof, pins)

        def _sweep_servo(servo_idx):
            if servo_idx >= dof:
                self._test_btn.configure(state="normal", text="Test Servos")
                return
            current = [0] * dof
            for target_angle in [-90, 0, 90, 0]:
                current[servo_idx] = target_angle
                angles = list(current)
                self._arm.move_all_ramped(angles, step_size=1, delay_ms=10)
                import time as _t
                _t.sleep(max(0.02, (abs(target_angle) + 1) * 0.02 + 0.2))
            self.after(100, lambda: _sweep_servo(servo_idx + 1))

        _sweep_servo(0)

    def _apply_config(self):
        dof = self._dof_var.get()
        pins = [int(v.get()) for v in self._pin_vars[:dof]]

        config = {"dof": dof, "pins": pins}
        save_config(config)

        if self._transport is not None and self._transport.is_connected:
            self._transport.send_config(dof, pins)
            self._arm.reconfigure(dof, pins)

        if self._on_apply:
            self._on_apply(dof, pins)

        self.destroy()

    def _on_cancel(self):
        self.destroy()
