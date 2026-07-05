import customtkinter as ctk
from core.serial_manager import SerialManager
from core.bluetooth_manager import BluetoothManager
from core.robot_arm import RobotArm
from core.sequence import SequencePlayer
from core.xinput_controller import XInputController
from gui.connection_frame import ConnectionFrame
from gui.control_frame import ControlFrame
from gui.sequence_frame import SequenceFrame
from gui.controller_frame import ControllerFrame
from gui.configurator_frame import ConfiguratorFrame
from utils.theme import THEME, DARK, LIGHT
from utils.config_manager import load_config
from queue import Queue, Empty


class RoboticArmApp(ctk.CTk):
    LERP_FACTOR = 0.25
    UI_POLL_MS = 33

    def __init__(self):
        super().__init__()
        self._config = load_config()
        self._init_components()
        self._setup_window()
        self._build_ui()
        self._setup_keyboard_shortcuts()
        self._start_log_polling()
        self._start_controller_polling()
        self._start_status_polling()
        self._serial.set_disconnect_callback(self._on_port_lost)
        if self._bt:
            self._bt.set_disconnect_callback(self._on_port_lost)
            self._bt.set_reconnect_callback(self._on_reconnect_attempt)

    def _get_transport(self):
        if self._bt and self._bt.is_connected:
            return self._bt
        if self._serial and self._serial.is_connected:
            return self._serial
        return None

    def _init_components(self):
        self._serial = SerialManager(baud=115200)
        self._bt = BluetoothManager()
        num_servos = self._config.get("dof", 6)
        servo_pins = self._config.get("pins", [13, 12, 14, 27, 26, 25])
        self._arm = RobotArm(self._serial, num_servos=num_servos, servo_pins=servo_pins)
        self._seq = SequencePlayer(self._arm, log_callback=self._log)
        self._controller = XInputController(log_callback=self._log)
        self._theme_var = ctk.StringVar(value="dark")
        self._log_queue = Queue()
        self._smoothed_angles = [0] * num_servos
        self._last_sent_angles = [0] * num_servos
        self._precision_mode = False
        self._controller_sensitivity = 1.0
        self._last_cmd_msg = ""
        self._last_cmd_time = 0.0

    def _setup_window(self):
        dof = self._arm.num_servos
        self.title(f"Control de Brazo Robótico — {dof} DOF")
        self.geometry("860x720")
        self.minsize(760, 640)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._apply_theme_colors()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _apply_theme_colors(self):
        colors = DARK if self._theme_var.get() == "dark" else LIGHT
        self.configure(fg_color=colors["bg"])

    def _build_ui(self):
        self._create_toolbar()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=1, column=0, padx=(10, 5), pady=(0, 10), sticky="nsew")
        left_panel.grid_rowconfigure(0, weight=0)
        left_panel.grid_rowconfigure(1, weight=0)
        left_panel.grid_rowconfigure(2, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)
        self._connection_frame = ConnectionFrame(
            left_panel, self._serial, bluetooth_manager=self._bt,
            fg_color=("gray90", "gray20"),
        )
        self._connection_frame.grid(row=0, column=0, pady=(0, 6), sticky="ew")
        self._connection_frame.set_callbacks(
            on_connect=self._on_connected,
            on_disconnect=self._on_disconnected,
        )
        self._controller_frame = ControllerFrame(
            left_panel, self._controller,
            fg_color=("gray90", "gray20"),
        )
        if self._controller.available:
            self._controller_frame.grid(row=1, column=0, pady=(0, 8), sticky="ew")
        self._controller_frame.set_toggle_callback(self._on_controller_toggle)
        self._controller_frame.set_precision_callback(self._on_precision_toggle)
        self._controller_frame.set_sensitivity_callback(self._on_sensitivity_change)
        self._controller.set_connection_callback(self._on_controller_connection)
        self._control_frame = ControlFrame(
            left_panel, self._arm,
            fg_color=("gray90", "gray20"),
        )
        self._control_frame.grid(row=2, column=0, sticky="nsew")
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(row=1, column=1, padx=(5, 10), pady=(0, 10), sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)
        self._sequence_frame = SequenceFrame(
            right_panel, self._arm, self._seq, self._control_frame,
            log_callback=self._log,
            fg_color=("gray90", "gray20"),
        )
        self._sequence_frame.grid(row=0, column=0, sticky="ew")
        self._create_log_panel(right_panel)
        self._create_status_bar()

    def _create_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color=("gray85", "gray15"), height=40)
        toolbar.grid(row=0, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            toolbar, text="⚙  Control de Brazo Robótico",
            font=("Segoe UI", 14, "bold"),
        )
        title.grid(row=0, column=0, padx=(14, 0), pady=8, sticky="w")
        self._estop_btn = ctk.CTkButton(
            toolbar, text="🛑  PARO", command=self._emergency_stop,
            font=("Segoe UI", 11, "bold"), width=80,
            fg_color="#e03131", hover_color="#c92a2a",
            text_color="#ffffff",
        )
        self._estop_btn.grid(row=0, column=1, padx=(0, 4), pady=8, sticky="e")
        self._config_btn = ctk.CTkButton(
            toolbar, text="⚙  Configurar", command=self._open_configurator,
            font=("Segoe UI", 11), width=100,
            fg_color="#7950f2", hover_color="#6741d9",
        )
        self._config_btn.grid(row=0, column=2, padx=(0, 6), pady=8, sticky="e")
        self._theme_switch = ctk.CTkSwitch(
            toolbar, text="🌙 Oscuro", command=self._toggle_theme,
            font=("Segoe UI", 11),
        )
        self._theme_switch.grid(row=0, column=3, padx=(0, 14), pady=8, sticky="e")
        self._theme_switch.select()

    def _create_log_panel(self, parent):
        log_frame = ctk.CTkFrame(parent)
        log_frame.grid(row=1, column=0, pady=(8, 0), sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, pady=(4, 0), padx=8, sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        log_title = ctk.CTkLabel(
            log_header, text="📋  LOG DE EVENTOS",
            font=("Segoe UI", 10, "bold"),
        )
        log_title.grid(row=0, column=0, sticky="w")
        self._clear_log_btn = ctk.CTkButton(
            log_header, text="Limpiar", font=("Segoe UI", 9),
            width=60, height=20, command=self._clear_log,
        )
        self._clear_log_btn.grid(row=0, column=1, padx=(0, 0), pady=0)
        self._log_text = ctk.CTkTextbox(
            log_frame, font=("Consolas", 10), height=120,
            wrap="word",
        )
        self._log_text.grid(row=1, column=0, padx=8, pady=(2, 8), sticky="nsew")
        self._log_text.configure(state="disabled")

    def _open_configurator(self):
        ConfiguratorFrame(
            self, self._get_transport(), self._arm,
            on_apply=self._on_config_applied,
        )

    def _on_config_applied(self, dof, pins):
        num = self._arm.num_servos
        self.title(f"Control de Brazo Robótico — {num} DOF")
        self._control_frame.refresh()
        self._smoothed_angles = [0] * num
        self._last_sent_angles = [0] * num
        transport = self._get_transport()
        if transport is None or not transport.is_connected:
            self._control_frame.set_angles([0] * num)

    def _toggle_theme(self):
        if self._theme_var.get() == "dark":
            self._theme_var.set("light")
            ctk.set_appearance_mode("light")
            self._theme_switch.configure(text="☀️ Claro")
        else:
            self._theme_var.set("dark")
            ctk.set_appearance_mode("dark")
            self._theme_switch.configure(text="🌙 Oscuro")
        self._apply_theme_colors()

    def _create_status_bar(self):
        self._status_bar = ctk.CTkFrame(self, fg_color=("gray85", "gray15"), height=28)
        self._status_bar.grid(row=2, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        self._status_bar.grid_columnconfigure(0, weight=0)
        self._status_bar.grid_columnconfigure(1, weight=1)
        self._status_bar.grid_columnconfigure(2, weight=0)
        self._status_led = ctk.CTkLabel(self._status_bar, text="⚫", font=("Segoe UI", 12))
        self._status_led.grid(row=0, column=0, padx=(10, 4), pady=2)
        self._status_text = ctk.CTkLabel(
            self._status_bar, text="Desconectado",
            font=("Segoe UI", 10), anchor="w",
            text_color=("#868e96", "#909296"),
        )
        self._status_text.grid(row=0, column=1, padx=(0, 8), pady=2, sticky="w")
        self._status_right = ctk.CTkLabel(
            self._status_bar, text="",
            font=("Segoe UI", 9), anchor="e",
            text_color=("#868e96", "#909296"),
        )
        self._status_right.grid(row=0, column=2, padx=(0, 10), pady=2, sticky="e")

    def _update_status_bar(self):
        transport = self._get_transport()
        connected = transport and transport.is_connected
        dof = self._arm.num_servos
        if connected:
            t = "BT" if (self._bt and self._bt.is_connected) else "USB"
            label = f"{t} · {dof} DOF · {transport.port or '—'}"
            self._status_led.configure(text="🟢")
            self._status_text.configure(text=label, text_color="#51cf66")
        else:
            self._status_led.configure(text="🔴")
            self._status_text.configure(text="Desconectado", text_color=("#868e96", "#909296"))
        self._status_right.configure(text=self._last_cmd_msg)

    def _start_status_polling(self):
        self._poll_status()

    def _poll_status(self):
        self._update_status_bar()
        self.after(500, self._poll_status)

    def _emergency_stop(self):
        self._arm.home()
        self._log("🛑 PARO DE EMERGENCIA — todos los servos a HOME")
        self._last_cmd_msg = "PARO"
        self._update_status_bar()

    def _on_reconnect_attempt(self, attempt, max_attempts):
        self._status_text.configure(
            text=f"Reconectando... ({attempt}/{max_attempts})",
            text_color="#fcc419",
        )
        self._status_led.configure(text="🟡")

    def _log(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put(f"[{timestamp}] {message}")

    def _start_log_polling(self):
        self._poll_log()
        self._poll_transport_log()

    def _poll_log(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append_log(msg)
        except Empty:
            pass
        self.after(200, self._poll_log)

    def _poll_transport_log(self):
        for t in [self._serial, self._bt]:
            if t:
                msg = t.get_log()
                while msg:
                    self._append_log(f"[{self._now()}] {msg}")
                    msg = t.get_log()
        self.after(200, self._poll_transport_log)

    @staticmethod
    def _now():
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def _append_log(self, message):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"{message}\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _on_connected(self):
        if self._bt and self._bt.is_connected:
            self._arm.set_transport(self._bt)
        else:
            self._arm.set_transport(self._serial)
        num = self._arm.num_servos
        self._control_frame.set_enabled(True)
        self._control_frame.set_angles([0] * num)
        self._sequence_frame.set_enabled(True)
        self._smoothed_angles = [0] * num
        self._last_sent_angles = [0] * num

    def _on_disconnected(self):
        self._control_frame.set_enabled(False)
        self._sequence_frame.set_enabled(False)

    def _on_port_lost(self):
        self.after(0, self._do_port_lost)

    def _do_port_lost(self):
        self._connection_frame.on_port_lost()
        self._on_disconnected()

    def _on_controller_connection(self, connected):
        self.after(0, lambda: self._controller_frame.set_connected(connected))

    def _on_controller_toggle(self, active):
        self._controller.set_enabled(active)
        self._control_frame.set_controller_active(active)

    def _on_precision_toggle(self, active):
        self._precision_mode = active
        self._log("Modo precisión " + ("activado" if active else "desactivado"))

    def _on_sensitivity_change(self, value):
        self._controller_sensitivity = value

    def _start_controller_polling(self):
        self._controller.start()
        self._poll_controller()

    def _poll_controller(self):
        button = self._controller.read_button()
        while button:
            self._handle_controller_button(button)
            button = self._controller.read_button()

        if self._controller.enabled:
            target = self._controller.read_target()
            if target is not None:
                self._apply_controller_target(target)
            else:
                delta = self._controller.read_delta()
                while delta:
                    idx, value = delta
                    self._smoothed_angles[idx] = max(-90, min(90, self._smoothed_angles[idx] + value))
                    delta = self._controller.read_delta()
                if self._controller.enabled:
                    self._control_frame.set_angles_silent(self._smoothed_angles)
                    self._send_if_changed()

        self.after(self.UI_POLL_MS, self._poll_controller)

    def _handle_controller_button(self, action):
        if action == "home":
            self._sequence_frame.home()
        elif action == "save_posture":
            self._sequence_frame.save_posture()
        elif action == "add_posture":
            self._sequence_frame.add_posture()
        elif action == "play":
            if self._seq.is_playing:
                self._sequence_frame.stop()
            else:
                self._sequence_frame.play()
        elif action == "stop":
            self._sequence_frame.stop()

    def _send_if_changed(self):
        if self._smoothed_angles != self._last_sent_angles:
            self._last_sent_angles = list(self._smoothed_angles)
            self._arm.move_all(self._smoothed_angles)

    def _get_effective_lerp(self):
        if self._precision_mode:
            return 0.05
        return self.LERP_FACTOR * self._controller_sensitivity

    def _apply_controller_target(self, target):
        delta = self._controller.read_delta()
        while delta:
            idx, value = delta
            self._smoothed_angles[idx] = max(-90, min(90, self._smoothed_angles[idx] + value))
            delta = self._controller.read_delta()

        lerp_factor = self._get_effective_lerp()
        for i in (0, 1, 3, 4):
            t = target[i]
            if t is None:
                continue
            current = self._smoothed_angles[i]
            new_val = current + round((t - current) * lerp_factor)
            self._smoothed_angles[i] = new_val

        self._control_frame.set_angles_silent(self._smoothed_angles)
        self._send_if_changed()

    def _setup_keyboard_shortcuts(self):
        self.bind("<Control-h>", lambda e: self._sequence_frame.home())
        self.bind("<Control-s>", lambda e: self._sequence_frame.save_posture())
        self.bind("<Control-o>", lambda e: self._sequence_frame.load_posture())
        self.bind("<Control-S>", lambda e: self._sequence_frame.save_sequence())
        self.bind("<Control-O>", lambda e: self._sequence_frame.load_sequence())
        self.bind("<Control-e>", lambda e: self._emergency_stop())
        self.bind("<space>", lambda e: self._toggle_playback())
        self.bind("<Escape>", lambda e: self._sequence_frame.stop())

    def _toggle_playback(self):
        if self._seq.is_playing:
            self._sequence_frame.stop()
        else:
            self._sequence_frame.play()

    def _on_closing(self):
        if self._seq.is_playing:
            self._seq.stop()
        if self._controller:
            self._controller.stop()
        if self._serial.is_connected:
            self._serial.disconnect()
        if self._bt and self._bt.is_connected:
            self._bt.disconnect()
        self.destroy()
