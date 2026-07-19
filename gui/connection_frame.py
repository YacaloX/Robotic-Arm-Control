import re
import threading
import customtkinter as ctk
from core.serial_manager import SerialManager
from core.bluetooth_manager import BluetoothManager


class ConnectionFrame(ctk.CTkFrame):
    MODE_USB = "USB"
    MODE_BT = "Bluetooth"

    def __init__(self, master, serial_manager, bluetooth_manager=None, **kwargs):
        super().__init__(master, **kwargs)
        self._serial = serial_manager
        self._bt = bluetooth_manager
        self._connect_callback = None
        self._disconnect_callback = None
        self._mode = self.MODE_USB
        self._build_ui()
        self._refresh_devices()

    def set_callbacks(self, on_connect=None, on_disconnect=None):
        self._connect_callback = on_connect
        self._disconnect_callback = on_disconnect

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(self, text="CONEXIÓN", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=5, pady=(0, 6), sticky="w")

        # Selector de modo USB / Bluetooth
        self._mode_var = ctk.StringVar(value=self.MODE_USB)
        usb_rb = ctk.CTkRadioButton(
            self, text="USB", variable=self._mode_var, value=self.MODE_USB,
            command=self._on_mode_change, font=("Segoe UI", 10),
        )
        usb_rb.grid(row=1, column=0, padx=(0, 2), pady=1, sticky="w")
        bt_rb = ctk.CTkRadioButton(
            self, text="Bluetooth", variable=self._mode_var, value=self.MODE_BT,
            command=self._on_mode_change, font=("Segoe UI", 10),
        )
        bt_rb.grid(row=1, column=1, padx=0, pady=1, sticky="w")

        # Puerto / dispositivo
        self._port_var = ctk.StringVar()
        self._port_menu = ctk.CTkOptionMenu(
            self, variable=self._port_var, values=["Sin puertos"],
            command=self._on_port_selected, width=120,
        )
        self._port_menu.grid(row=2, column=0, padx=(0, 2), pady=2, sticky="ew")

        self._refresh_btn = ctk.CTkButton(
            self, text="⟳", width=28, command=self._refresh_devices,
            font=("Segoe UI", 14),
        )
        self._refresh_btn.grid(row=2, column=1, padx=(0, 2), pady=2)

        self._connect_btn = ctk.CTkButton(
            self, text="Conectar", command=self._toggle_connection,
            width=80, font=("Segoe UI", 10),
        )
        self._connect_btn.grid(row=2, column=2, padx=0, pady=2)

        self._led = ctk.CTkLabel(self, text="🔴", font=("Segoe UI", 16))
        self._led.grid(row=2, column=3, padx=(2, 0), pady=2)

        self._status_label = ctk.CTkLabel(
            self, text="Desconectado", font=("Segoe UI", 10),
            text_color=("#868e96", "#909296"),
        )
        self._status_label.grid(row=3, column=0, columnspan=5, pady=(2, 0), sticky="w")

    def _on_mode_change(self):
        self._mode = self._mode_var.get()
        self._refresh_devices()

    def _refresh_devices(self):
        if self._mode == self.MODE_USB:
            ports = SerialManager.list_ports()
            if ports:
                self._port_menu.configure(values=ports)
                current = self._port_var.get()
                if current not in ports:
                    self._port_var.set(ports[0])
            else:
                self._port_menu.configure(values=["Sin puertos"])
                self._port_var.set("Sin puertos")
        else:
            self._status_label.configure(
                text="Escaneando Bluetooth...",
                text_color=("#868e96", "#909296"),
            )
            self._refresh_btn.configure(state="disabled")
            self._connect_btn.configure(state="disabled")
            threading.Thread(target=self._scan_bt, daemon=True).start()

    def _scan_bt(self):
        try:
            if not self._bt:
                self.after(0, lambda: self._finish_bt_scan(["No disponible"], "No disponible"))
                return
            devices = BluetoothManager.discover_devices(timeout=8)
            bt_list = [f"{name} ({addr})" for addr, name in devices]
            if bt_list:
                self.after(0, lambda: self._finish_bt_scan(bt_list, bt_list[0]))
                self.after(0, lambda: self._status_label.configure(
                    text=f"{len(bt_list)} dispositivo(s) encontrado(s)",
                    text_color=("#868e96", "#909296"),
                ))
            else:
                self.after(0, lambda: self._finish_bt_scan(["Sin dispositivos BT"], "Sin dispositivos BT"))
                self.after(0, lambda: self._status_label.configure(text="No se encontraron dispositivos"))
        except Exception as e:
            self.after(0, lambda: self._finish_bt_scan(["Error escaneo BT"], "Error escaneo BT"))
            self.after(0, lambda: self._status_label.configure(
                text=f"Error BT: {e}", text_color="#ff6b6b",
            ))

    def _finish_bt_scan(self, values, current):
        self._port_menu.configure(values=values)
        self._port_var.set(current)
        self._refresh_btn.configure(state="normal")
        self._connect_btn.configure(state="normal")

    def _on_port_selected(self, choice):
        pass

    def _get_active_transport(self):
        if self._mode == self.MODE_BT:
            return self._bt
        return self._serial

    def _toggle_connection(self):
        transport = self._get_active_transport()
        if transport and transport.is_connected:
            transport.disconnect()
            self._on_disconnected()
            return

        if self._mode == self.MODE_USB:
            port = self._port_var.get()
            if port and port not in ("Sin puertos",):
                if self._serial.connect(port):
                    self._on_connected(f"USB:{port}")
                else:
                    self._on_connection_failed()
            else:
                self._status_label.configure(text="Seleccione un puerto USB")
        else:
            choice = self._port_var.get()
            if choice and choice not in ("Sin dispositivos BT", "No disponible"):
                m = re.search(r"\(([0-9A-F:]+)\)$", choice)
                addr = m.group(1) if m else choice
                self._connect_btn.configure(state="disabled")
                self._status_label.configure(
                    text="Conectando...", text_color=("#868e96", "#909296"),
                )
                threading.Thread(
                    target=self._bt_connect_thread, args=(addr,), daemon=True,
                ).start()
            else:
                self._status_label.configure(text="Seleccione un dispositivo BT")

    def _bt_connect_thread(self, addr):
        try:
            ok = self._bt and self._bt.connect(addr)
        except Exception:
            ok = False
        self.after(0, lambda: self._bt_connect_result(addr, ok))

    def _bt_connect_result(self, addr, ok):
        self._connect_btn.configure(state="normal")
        if ok:
            self._on_connected(f"BT:{addr}")
        else:
            self._on_connection_failed()

    def _on_connected(self, label):
        self._connect_btn.configure(
            text="Desconectar", fg_color="#e03131", hover_color="#c92a2a",
        )
        self._led.configure(text="🟢")
        self._status_label.configure(text=f"Conectado ({label})", text_color="#51cf66")
        self._port_menu.configure(state="disabled")
        self._refresh_btn.configure(state="disabled")
        if self._connect_callback:
            self._connect_callback()

    def _on_disconnected(self):
        self._connect_btn.configure(
            text="Conectar",
            fg_color=("#1971c2", "#4c9aff"),
            hover_color=("#1864ab", "#3a8af0"),
        )
        self._led.configure(text="🔴")
        self._status_label.configure(
            text="Desconectado", text_color=("#868e96", "#909296"),
        )
        self._port_menu.configure(state="normal")
        self._refresh_btn.configure(state="normal")
        if self._disconnect_callback:
            self._disconnect_callback()

    def _on_connection_failed(self):
        self._led.configure(text="🔴")
        self._status_label.configure(
            text="Error de conexión", text_color="#ff6b6b",
        )

    def on_port_lost(self):
        self._on_disconnected()

    def refresh(self):
        self._refresh_devices()
