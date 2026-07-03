import serial
import serial.tools.list_ports
import threading
import time
from queue import Queue, Empty

from core.protocol_handler import ProtocolHandler


# VID/PID de conversores USB-UART típicos en ESP32 DevKit v1
ESP32_VID_PID = [
    (0x10C4, 0xEA60),  # Silicon Labs CP2102
    (0x1A86, 0x7523),  # CH340
    (0x1A86, 0x55D4),  # CH9102
    (0x0403, 0x6001),  # FTDI FT232
]


class SerialManager:
    def __init__(self, baud=115200):
        self._port = None
        self._baud = baud
        self._serial = None
        self._connected = False
        self._lock = threading.RLock()
        self._reader_thread = None
        self._running = False
        self._log_queue = Queue()
        self._disconnect_callback = None
        self._protocol = ProtocolHandler(self._log_queue)

    @property
    def is_connected(self):
        with self._lock:
            if not self._connected or self._serial is None:
                return False
            try:
                return self._serial.is_open
            except (serial.SerialException, AttributeError):
                return False

    @property
    def port(self):
        return self._port

    @property
    def detected_dof(self):
        return self._protocol.detected_dof

    @property
    def detected_pins(self):
        return self._protocol.detected_pins

    @property
    def firmware_ready(self):
        return self._protocol.firmware_ready

    def set_disconnect_callback(self, callback):
        self._disconnect_callback = callback

    def get_log(self, timeout=0.05):
        try:
            return self._log_queue.get_nowait()
        except Empty:
            return None

    @staticmethod
    def list_ports():
        return [p.device for p in serial.tools.list_ports.comports()]

    @staticmethod
    def list_esp32_ports():
        esp32_ports = []
        for p in serial.tools.list_ports.comports():
            if (p.vid, p.pid) in ESP32_VID_PID:
                esp32_ports.append(p.device)
            elif p.vid is None and "COM" in p.device.upper():
                esp32_ports.append(p.device)
        return esp32_ports

    @staticmethod
    def is_esp32_port(port):
        for p in serial.tools.list_ports.comports():
            if p.device == port:
                return (p.vid, p.pid) in ESP32_VID_PID
        return False

    def connect(self, port, timeout=25):
        if self.is_connected:
            self.disconnect()
        t0 = time.time()
        try:
            ser = serial.Serial(
                port=port,
                baudrate=self._baud,
                timeout=0.1,
                write_timeout=0.1,
            )
            time.sleep(0.5)
            with self._lock:
                self._serial = ser
                self._port = port
                self._connected = True
                self._running = True
                self._protocol._firmware_ready = False
            self._handshake_event = threading.Event()
            self._handshake_event.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            self._log_queue.put(f"Conectado a {port} a {self._baud} baudios")

            ser.reset_input_buffer()
            handshake_ok = False
            for attempt in range(2):
                if time.time() - t0 > timeout:
                    break
                ser.write(b"PING\n")
                ser.flush()
                if self._handshake_event.wait(timeout=3):
                    handshake_ok = True
                    break
                self._log_queue.put(f"Handshake intento {attempt + 1}/2 falló, reintentando...")
                self._handshake_event.clear()
                time.sleep(0.3)

            if not handshake_ok:
                self._log_queue.put("No se recibió respuesta del ESP32 — handshake falló")
                self.disconnect()
                return False

            return True
        except serial.SerialException as e:
            self._log_queue.put(f"Error al conectar: {e}")
            self._cleanup()
            return False

    def disconnect(self):
        with self._lock:
            self._running = False
            self._protocol._firmware_ready = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        ser, port = self._cleanup()
        if port:
            self._log_queue.put(f"Desconectado de {port}")

    def _cleanup(self):
        ser = None
        port = self._port
        with self._lock:
            self._connected = False
            self._port = None
            if self._serial:
                ser = self._serial
                self._serial = None
        if ser:
            try:
                if ser.is_open:
                    ser.close()
            except Exception:
                pass
        return ser, port

    def _reader_loop(self):
        while True:
            with self._lock:
                if not self._running:
                    break
                ser = self._serial
            if ser is None:
                self._on_disconnect()
                break
            try:
                if ser.is_open:
                    try:
                        line = ser.readline().decode("utf-8", errors="replace").strip()
                        if line:
                            self._protocol.process_line(line, self._handshake_event)
                    except serial.SerialTimeoutException:
                        pass
                else:
                    self._on_disconnect()
                    break
            except serial.SerialException:
                self._on_disconnect()
                break
            except Exception as e:
                self._log_queue.put(f"Error en lectura: {e}")
                break

    def _on_disconnect(self):
        with self._lock:
            if not self._connected:
                return
        ser, port = self._cleanup()
        if not port:
            return
        self._protocol._firmware_ready = False
        self._log_queue.put(f"Puerto {port} perdido")
        if self._disconnect_callback:
            self._disconnect_callback()

    def send(self, servo_id, angle):
        if not self.is_connected:
            return False
        angle = max(-90, min(90, int(angle)))
        command = f"{servo_id} {angle}\n"
        with self._lock:
            try:
                self._serial.write(command.encode("utf-8"))
                self._serial.flush()
                self._log_queue.put(f"Servo {servo_id} → {angle}°")
                return True
            except serial.SerialException as e:
                self._log_queue.put(f"Error al enviar: {e}")
                self._on_disconnect()
                return False

    def send_config(self, num_servos, pins):
        if not self.is_connected:
            return False
        pins_str = " ".join(str(p) for p in pins)
        command = f"CONFIG {num_servos} {pins_str}\n"
        with self._lock:
            try:
                self._serial.write(command.encode("utf-8"))
                self._serial.flush()
                self._log_queue.put(f"Config → {num_servos} DOF, pines: {pins_str}")
                return True
            except serial.SerialException as e:
                self._log_queue.put(f"Error al enviar CONFIG: {e}")
                return False
