import customtkinter as ctk


class ControllerFrame(ctk.CTkFrame):
    SENS_VALUES = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
    SENS_LABELS = ["Lento", "", "Normal", "", "Rápido", "", ""]

    def __init__(self, master, controller, **kwargs):
        super().__init__(master, **kwargs)
        self._controller = controller
        self._toggle_callback = None
        self._precision_callback = None
        self._sensitivity_callback = None
        self._build_ui()

    def set_toggle_callback(self, callback):
        self._toggle_callback = callback

    def set_precision_callback(self, callback):
        self._precision_callback = callback

    def set_sensitivity_callback(self, callback):
        self._sensitivity_callback = callback

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(4, weight=0)
        title = ctk.CTkLabel(self, text="🎮  CONTROLADOR XBOX", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=5, pady=(0, 6), sticky="w")
        self._led = ctk.CTkLabel(self, text="🔴", font=("Segoe UI", 16))
        self._led.grid(row=1, column=0, padx=(0, 4), pady=1)
        self._status_label = ctk.CTkLabel(
            self, text="No detectado",
            font=("Segoe UI", 10),
            text_color=("#868e96", "#909296"),
        )
        self._status_label.grid(row=1, column=1, padx=(0, 4), pady=1, sticky="w")
        self._toggle_switch = ctk.CTkSwitch(
            self, text="Activo", command=self._on_toggle,
            font=("Segoe UI", 10), onvalue=1, offvalue=0,
            state="disabled",
        )
        self._toggle_switch.grid(row=1, column=2, padx=(0, 0), pady=1, columnspan=2)
        legend = ctk.CTkLabel(
            self,
            text="LS→Base/Hombro  RS→Muñecas  DP→Codo/Mano\nA:Home  B:Guardar  Y:Agregar  Start:Play  Back:Stop",
            font=("Segoe UI", 9),
            text_color=("#868e96", "#909296"),
            justify="left",
        )
        legend.grid(row=2, column=0, columnspan=5, pady=(2, 2), sticky="w")
        self._precision_switch = ctk.CTkSwitch(
            self, text="Modo precisión", command=self._on_precision_toggle,
            font=("Segoe UI", 10), onvalue=1, offvalue=0,
        )
        self._precision_switch.grid(row=3, column=0, columnspan=2, padx=0, pady=1, sticky="w")
        sens_label = ctk.CTkLabel(self, text="Sens:", font=("Segoe UI", 10))
        sens_label.grid(row=3, column=2, padx=(0, 2), pady=1, sticky="e")
        self._sens_slider = ctk.CTkSlider(
            self, from_=0, to=len(self.SENS_VALUES) - 1,
            number_of_steps=len(self.SENS_VALUES) - 1,
            command=self._on_sensitivity_change,
            width=80,
        )
        self._sens_slider.set(2)
        self._sens_slider.grid(row=3, column=3, padx=(0, 2), pady=1, sticky="ew")
        self._sens_label = ctk.CTkLabel(self, text="Normal", font=("Segoe UI", 10, "bold"), width=50)
        self._sens_label.grid(row=3, column=4, padx=0, pady=1, sticky="w")

    def set_connected(self, connected):
        if connected:
            self._led.configure(text="🟢")
            self._status_label.configure(text="Mando conectado", text_color="#51cf66")
            self._toggle_switch.configure(state="normal")
        else:
            self._led.configure(text="🔴")
            self._status_label.configure(text="No detectado", text_color=("#868e96", "#909296"))
            self._toggle_switch.configure(state="disabled")
            self._toggle_switch.deselect()

    def set_active(self, active):
        self._toggle_switch.select() if active else self._toggle_switch.deselect()

    def get_sensitivity(self):
        idx = int(round(self._sens_slider.get()))
        idx = max(0, min(len(self.SENS_VALUES) - 1, idx))
        return self.SENS_VALUES[idx]

    def _on_toggle(self):
        if self._toggle_callback:
            self._toggle_callback(bool(self._toggle_switch.get()))

    def _on_precision_toggle(self):
        active = bool(self._precision_switch.get())
        if self._precision_callback:
            self._precision_callback(active)

    def _on_sensitivity_change(self, value):
        idx = int(round(value))
        idx = max(0, min(len(self.SENS_VALUES) - 1, idx))
        label = self.SENS_LABELS[idx] or f"{self.SENS_VALUES[idx]:.2f}×"
        self._sens_label.configure(text=label)
        if self._sensitivity_callback:
            self._sensitivity_callback(self.SENS_VALUES[idx])
