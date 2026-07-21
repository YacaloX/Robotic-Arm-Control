import customtkinter as ctk


class MotionControllerFrame(ctk.CTkFrame):
    SENS_VALUES = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
    SENS_LABELS = ["Lento", "", "Normal", "", "Rápido", "", ""]

    CONTROLLER_TYPES = ["PSMove", "Wiimote"]

    def __init__(self, master, psmove_controller, wiimote_controller, **kwargs):
        super().__init__(master, **kwargs)
        self._psmove = psmove_controller
        self._wiimote = wiimote_controller
        self._active_type = None
        self._toggle_callback = None
        self._sensitivity_callback = None
        self._connect_callback = None
        self._disconnect_callback = None
        self._build_ui()

    def set_toggle_callback(self, callback):
        self._toggle_callback = callback

    def set_sensitivity_callback(self, callback):
        self._sensitivity_callback = callback

    def set_connect_callback(self, callback):
        self._connect_callback = callback

    def set_disconnect_callback(self, callback):
        self._disconnect_callback = callback

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self, text="🎮  CONTROL DE MOVIMIENTO",
            font=("Segoe UI", 12, "bold"),
        )
        title.grid(row=0, column=0, columnspan=6, pady=(0, 6), sticky="w")

        self._type_var = ctk.StringVar(value="PSMove")
        self._type_menu = ctk.CTkOptionMenu(
            self, values=self.CONTROLLER_TYPES,
            variable=self._type_var, width=100,
            font=("Segoe UI", 10),
        )
        self._type_menu.grid(row=1, column=0, padx=(0, 6), pady=1)

        self._led = ctk.CTkLabel(self, text="🔴", font=("Segoe UI", 16))
        self._led.grid(row=1, column=1, padx=(0, 4), pady=1)

        self._status_label = ctk.CTkLabel(
            self, text="No detectado",
            font=("Segoe UI", 10),
            text_color=("#868e96", "#909296"),
        )
        self._status_label.grid(row=1, column=2, padx=(0, 4), pady=1, sticky="w")

        self._connect_btn = ctk.CTkButton(
            self, text="Conectar", width=70, height=24,
            font=("Segoe UI", 10),
            fg_color="#51cf66", hover_color="#40c057",
            command=self._on_connect,
        )
        self._connect_btn.grid(row=1, column=3, padx=(0, 2), pady=1)

        self._disconnect_btn = ctk.CTkButton(
            self, text="Desconectar", width=70, height=24,
            font=("Segoe UI", 10),
            fg_color="#868e96", hover_color="#748ffc",
            state="disabled",
            command=self._on_disconnect,
        )
        self._disconnect_btn.grid(row=1, column=4, padx=(0, 2), pady=1)

        self._toggle_switch = ctk.CTkSwitch(
            self, text="Activo", command=self._on_toggle,
            font=("Segoe UI", 10), onvalue=1, offvalue=0,
            state="disabled",
        )
        self._toggle_switch.grid(row=1, column=5, padx=(0, 0), pady=1)

        self._legend = ctk.CTkLabel(
            self,
            text=(
                "PSMove: Pitch→Hombro  Roll→Base  Yaw→Rot.Muneca  Trigger→Pinza\n"
                "Wiimote: Pitch→Hombro  Roll→Base  IR→Muñecas\n"
                "PSMove: ▲Home  ●Guardar  ✕Agregar  ▶Play  ■Stop\n"
                "Wiimote: A→Home  B→Guardar  1→Agregar  +→Play  −→Stop"
            ),
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
            justify="left",
        )
        self._legend.grid(row=2, column=0, columnspan=6, pady=(2, 2), sticky="w")

        sens_label = ctk.CTkLabel(self, text="Sens:", font=("Segoe UI", 10))
        sens_label.grid(row=3, column=0, padx=(0, 2), pady=1, sticky="e")
        self._sens_slider = ctk.CTkSlider(
            self, from_=0, to=len(self.SENS_VALUES) - 1,
            number_of_steps=len(self.SENS_VALUES) - 1,
            command=self._on_sensitivity_change,
            width=80,
        )
        self._sens_slider.set(2)
        self._sens_slider.grid(row=3, column=1, columnspan=2, padx=(0, 2), pady=1, sticky="ew")
        self._sens_label = ctk.CTkLabel(
            self, text="Normal", font=("Segoe UI", 10, "bold"), width=50,
        )
        self._sens_label.grid(row=3, column=3, padx=0, pady=1, sticky="w")

        self._info_label = ctk.CTkLabel(
            self, text="",
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
        )
        self._info_label.grid(row=4, column=0, columnspan=6, pady=(2, 0), sticky="w")

    def _on_connect(self):
        selected = self._type_var.get()
        if selected == "PSMove":
            self._active_type = "psmove"
            ok = self._psmove.connect()
        else:
            self._active_type = "wiimote"
            ok = self._wiimote.connect()

        if ok:
            self._connect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="normal")
            self._type_menu.configure(state="disabled")

    def _on_disconnect(self):
        if self._active_type == "psmove":
            self._psmove.disconnect()
        elif self._active_type == "wiimote":
            self._wiimote.disconnect()
        self._active_type = None
        self._connected_state(False)
        self._connect_btn.configure(state="normal")
        self._disconnect_btn.configure(state="disabled")
        self._type_menu.configure(state="normal")

    def _on_toggle(self):
        active = bool(self._toggle_switch.get())
        if self._toggle_callback:
            self._toggle_callback(active)

    def _on_sensitivity_change(self, value):
        idx = int(round(value))
        idx = max(0, min(len(self.SENS_VALUES) - 1, idx))
        label = self.SENS_LABELS[idx] or f"{self.SENS_VALUES[idx]:.2f}x"
        self._sens_label.configure(text=label)
        if self._sensitivity_callback:
            self._sensitivity_callback(self.SENS_VALUES[idx])

    def set_connected(self, connected):
        self._connected_state(connected)

    def _connected_state(self, connected):
        if connected:
            self._led.configure(text="🟢")
            self._status_label.configure(
                text="Conectado", text_color="#51cf66",
            )
            self._toggle_switch.configure(state="normal")
            ctrl = self._get_active()
            if ctrl:
                orient = ctrl.get_orientation()
                pos = ctrl.get_position()
                self._info_label.configure(
                    text=f"Orient: pitch={orient[0]:.1f} roll={orient[1]:.1f}  "
                         f"Pos: x={pos[0]:.2f} y={pos[1]:.2f}",
                )
        else:
            self._led.configure(text="🔴")
            self._status_label.configure(
                text="No detectado",
                text_color=("#868e96", "#909296"),
            )
            self._toggle_switch.configure(state="disabled")
            self._toggle_switch.deselect()
            self._info_label.configure(text="")

    def set_active(self, active):
        if active:
            self._toggle_switch.select()
        else:
            self._toggle_switch.deselect()

    def get_sensitivity(self):
        idx = int(round(self._sens_slider.get()))
        idx = max(0, min(len(self.SENS_VALUES) - 1, idx))
        return self.SENS_VALUES[idx]

    def _get_active(self):
        if self._active_type == "psmove" and self._psmove.is_connected:
            return self._psmove
        if self._active_type == "wiimote" and self._wiimote.is_connected:
            return self._wiimote
        return None

    def update_info(self):
        ctrl = self._get_active()
        if ctrl and ctrl.is_connected:
            orient = ctrl.get_orientation()
            pos = ctrl.get_position()
            self._info_label.configure(
                text=f"Orient: pitch={orient[0]:.1f} roll={orient[1]:.2f}  "
                     f"Pos: x={pos[0]:.2f} y={pos[1]:.2f}",
            )
            self.after(100, self.update_info)
