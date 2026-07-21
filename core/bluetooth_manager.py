import threading
import time
import subprocess
import re
import sys
import socket
import os
import serial
import fcntl
import select
import json
from queue import Queue, Empty
from pathlib import Path

from core.protocol_handler import ProtocolHandler

BT_TARGET_NAME = "Brazo-Robotico"
RFCOMM_DEVICE = "/dev/rfcomm0"
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
CONFIG_DIR = Path.home() / ".config" / "robotic_arm"
CONFIG_FILE = CONFIG_DIR / "bluetooth.json"


class BluetoothManager:
    KEEPALIVE_INTERVAL = 5
    KEEPALIVE_TIMEOUT = 3
    RECV_BUFFER_SIZE = 4096
    SEND_RETRIES = 3
    SEND_RETRY_DELAY = 0.05
    RECONNECT_MAX = 5
    RECONNECT_DELAYS = [1.0, 2.0, 3.0, 5.0, 8.0]

    def __init__(self, baud=115200):
        self._serial = None
        self._connected = False
        self._lock = threading.RLock()
        self._reader_thread = None
        self._running = False
        self._log_queue = Queue()
        self._protocol = ProtocolHandler(self._log_queue)
        self._disconnect_callback = None
        self._address = None
        self._baud = baud
        self._rfcomm_bound = False
        self._is_socket = False
        self._handshake_event = threading.Event()
        self._reconnect_enabled = True
        self._reconnect_count = 0
        self._reconnect_max = self.RECONNECT_MAX
        self._reconnect_timer = None
        self._reconnect_callback = None
        self._reconnect_success_callback = None
        self._reconnecting = False
        self._send_lock = threading.Lock()
        self._last_send_time = 0.0

    @property
    def is_connected(self):
        with self._lock:
            if not self._connected or self._serial is None:
                return False
            if self._is_socket:
                return True
            return self._serial.is_open

    @property
    def port(self):
        return f"BT:{self._address}" if self._address else None

    @property
    def firmware_ready(self):
        return self._protocol.firmware_ready

    @property
    def detected_dof(self):
        return self._protocol.detected_dof

    @property
    def detected_pins(self):
        return self._protocol.detected_pins

    def set_disconnect_callback(self, callback):
        self._disconnect_callback = callback

    def set_reconnect_callback(self, callback):
        self._reconnect_callback = callback

    def set_reconnect_success_callback(self, callback):
        self._reconnect_success_callback = callback

    def get_log(self, timeout=0.05):
        try:
            return self._log_queue.get_nowait()
        except Empty:
            return None

    def connect(self, address=None, timeout=50):
        if self.is_connected:
            self.disconnect()
        t0 = time.time()
        remaining = lambda: max(1.0, timeout - (time.time() - t0))

        if address is None:
            self._log_queue.put("Buscando dispositivo Brazo-Robotico...")
            address = BluetoothManager.find_brazo_device()
            if not address:
                self._log_queue.put("No se encontró el Brazo-Robotico vía Bluetooth")
                return False

        self._address = address
        self._log_queue.put(f"Conectando a {BT_TARGET_NAME} ({address})...")

        self._is_socket = False
        self._handshake_event.clear()

        # Step 1: raw socket directo (rápido si ya conectado previamente)
        success = self._try_raw_socket(address)
        if not success and time.time() - t0 > timeout:
            self._log_queue.put("Tiempo de conexión agotado")
            self._full_cleanup()
            return False

        # Step 2: bluetoothctl pair+trust + raw socket
        if not success:
            self._log_queue.put("Socket directo falló — emparejando vía bluetoothctl...")
            self._bluetoothctl_connect(address, timeout=min(15, remaining()))
            time.sleep(1.0)
            if time.time() - t0 <= timeout:
                success = self._try_raw_socket(address)

        # Step 3: clean stale bond + raw socket (fix for broken bond state)
        if not success and time.time() - t0 <= timeout:
            self._log_queue.put("Socket directo falló — limpiando emparejamiento...")
            self._bluetoothctl_remove(address)
            time.sleep(1.0)
            if time.time() - t0 <= timeout:
                success = self._try_raw_socket(address)

        # Step 4: último recurso — rfcomm bind
        if not success and time.time() - t0 <= timeout:
            self._log_queue.put("Socket directo no disponible — intentando rfcomm bind...")
            success = self._try_rfcomm_bind(address)

        if not success:
            self._log_queue.put(
                "No se pudo conectar. Prueba: "
                "1) Reiniciar el ESP32 (desconectar y reconectar power)  "
                "2) Desconectar USB del ESP32  "
                "3) bluetoothctl remove <MAC> && bluetoothctl pair <MAC>"
            )
            self._full_cleanup()
            return False

        with self._lock:
            self._connected = True
            self._running = True

        if self._is_socket:
            self._serial.settimeout(0.2)
        else:
            fd = self._serial.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            has_nonblock = bool(flags & os.O_NONBLOCK)
            if not has_nonblock:
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        handshake_ok = self._do_handshake()

        if not handshake_ok:
            self._full_cleanup()
            self._log_queue.put(
                "No se recibió respuesta del ESP32 — handshake falló. "
                "Verifica: 1) El ESP32 esté encendido 2) El firmware tenga el fix de LF "
                "3) No haya otro cliente Bluetooth conectado"
            )
            return False

        if not self._is_socket and self._serial is not None:
            self._serial.reset_input_buffer()

        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        self._log_queue.put(f"Conectado vía Bluetooth a {address}")
        return True

    @staticmethod
    def _resolve_spp_channel(address):
        try:
            result = subprocess.run(
                ["sdptool", "browse", address],
                capture_output=True, text=True, timeout=10,
            )
            for m in re.finditer(r"Channel:\s*(\d+)", result.stdout):
                return int(m.group(1))
        except Exception:
            pass
        return 1

    def _try_raw_socket(self, address):
        if not hasattr(socket, "AF_BLUETOOTH"):
            return False
        primary = self._resolve_spp_channel(address)
        channels = [primary]
        for ch in [1, 2, 3]:
            if ch != primary:
                channels.append(ch)
        for channel in channels:
            sock = None
            try:
                sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.RECV_BUFFER_SIZE)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except (OSError, AttributeError):
                    pass
                try:
                    sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, 30000))
                except (OSError, AttributeError, NameError):
                    pass
                sock.settimeout(5.0)
                sock.connect((address, channel))
                sock.settimeout(0.2)
                self._serial = sock
                self._is_socket = True
                self._log_queue.put(f"Conexión Bluetooth por socket directo (canal {channel})")
                return True
            except Exception:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
        return False

    def _bluetoothctl_connect(self, address, timeout=15):
        """Pair + trust via bluetoothctl. Does NOT connect — let raw socket handle the link."""
        # First disconnect any existing link to the device
        try:
            subprocess.run(
                ["bluetoothctl", "disconnect", address],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        time.sleep(0.5)

        try:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            commands = (
                f"agent on\ndefault-agent\n"
                f"pair {address}\ntrust {address}\n"
                f"disconnect {address}\n"
                f"exit\n"
            )
            proc.communicate(input=commands, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Verify bond state
        try:
            result = subprocess.run(
                ["bluetoothctl", "info", address],
                capture_output=True, text=True, timeout=5,
            )
            info_output = (result.stdout or "") + "\n" + (result.stderr or "")
            if "Paired: yes" in info_output:
                self._log_queue.put(f"Bluetooth emparejado: {address}")
            # Always disconnect after pair+trust so raw socket can claim the link
            try:
                subprocess.run(
                    ["bluetoothctl", "disconnect", address],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        except Exception:
            pass
        return True

    def _bluetoothctl_remove(self, address):
        """Remove bond to force fresh re-pairing on next raw socket."""
        try:
            subprocess.run(
                ["bluetoothctl", "disconnect", address],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        time.sleep(0.3)
        try:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            proc.communicate(input=f"remove {address}\nexit\n", timeout=10)
            self._log_queue.put(f"Emparejamiento eliminado: {address}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    def _open_rfcomm_with_timeout(self, timeout=10, retries=2):
        ser = None
        open_result = [None]
        open_done = threading.Event()

        def _open():
            try:
                s = serial.Serial(RFCOMM_DEVICE, self._baud, timeout=0.1, write_timeout=0.1)
                open_result[0] = s
            except Exception as e:
                open_result[0] = e
            finally:
                open_done.set()

        t = threading.Thread(target=_open, daemon=True)
        t.name = "rfcomm-open"
        t.start()
        if not open_done.wait(timeout=timeout):
            self._log_queue.put(f"Tiempo de espera ({timeout}s) abriendo {RFCOMM_DEVICE}")
            return None
        result = open_result[0]
        if isinstance(result, Exception):
            msg = str(result)
            if "Permission denied" in msg or "Errno 13" in msg:
                if retries > 0:
                    self._log_queue.put("Permiso denegado, corrigiendo...")
                    try:
                        subprocess.run(
                            ["sudo", "-n", "chmod", "666", RFCOMM_DEVICE],
                            capture_output=True, timeout=10,
                        )
                    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                        pass
                    return self._open_rfcomm_with_timeout(timeout, retries - 1)
                self._log_queue.put("Permiso denegado y no se pudo corregir")
                return None
            self._log_queue.put(f"Error abriendo {RFCOMM_DEVICE}: {result}")
            return None
        return result

    def _try_rfcomm_bind(self, address, _retry=0):
        if _retry >= 3:
            self._log_queue.put("rfcomm bind agotado — no se pudo establecer conexión activa")
            return False

        try:
            subprocess.run(["modprobe", "rfcomm"], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        for dev in ("0", "all"):
            try:
                subprocess.run(
                    ["rfcomm", "release", dev], capture_output=True, timeout=3,
                )
            except subprocess.TimeoutExpired:
                subprocess.run(["pkill", "-f", "rfcomm"], capture_output=True)
            except (FileNotFoundError, OSError):
                pass

        self._log_queue.put("Ejecutando rfcomm bind...")
        bind_candidates = [
            ["sudo", "-n", "rfcomm", "bind", "0", address, "1"],
            ["rfcomm", "bind", "0", address, "1"],
            ["sudo", "-n", "rfcomm", "bind", "0", address],
            ["rfcomm", "bind", "0", address],
        ]
        bind_ok = False
        for cmd in bind_candidates:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10,
                )
                self._log_queue.put(f"  {' '.join(cmd)} → rc={result.returncode}")
                if result.stderr:
                    for line in result.stderr.strip().split("\n"):
                        self._log_queue.put(f"    stderr: {line}")
                if result.returncode == 0:
                    bind_ok = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                self._log_queue.put(f"  {' '.join(cmd)} → error: {e}")
                continue

        if not bind_ok:
            self._log_queue.put("rfcomm bind falló — prueba: sudo rfcomm bind 0 <MAC> 1")
            self._log_queue.put("Intentando rfcomm connect como alternativa...")
            ser = self._try_rfcomm_connect(address)
            if ser:
                self._serial = ser
                self._rfcomm_bound = True
                return True
            return False

        for _ in range(30):
            if os.path.exists(RFCOMM_DEVICE):
                break
            time.sleep(0.3)

        if not os.path.exists(RFCOMM_DEVICE):
            subprocess.run(["udevadm", "settle"], capture_output=True, timeout=5)
            if not os.path.exists(RFCOMM_DEVICE):
                self._log_queue.put(f"{RFCOMM_DEVICE} no apareció tras bind")
                self._log_queue.put("Creando nodo rfcomm manualmente...")
                try:
                    subprocess.run(
                        ["sudo", "-n", "mknod", RFCOMM_DEVICE, "c", "216", "0"],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass
                if not os.path.exists(RFCOMM_DEVICE):
                    self._log_queue.put("rfcomm bind falló — no se pudo crear /dev/rfcomm0")
                    return False

        ser = self._open_rfcomm_with_timeout(timeout=10)
        if ser is None:
            return False

        # Verify the RFCOMM link is connected
        time.sleep(0.5)
        connected = False
        for _ in range(5):
            try:
                r = subprocess.run(
                    ["rfcomm", "show", "0"],
                    capture_output=True, text=True, timeout=3,
                )
                if "connected" in r.stdout.lower():
                    connected = True
                    break
            except Exception:
                pass
            time.sleep(1.0)

        if not connected:
            self._log_queue.put("RFCOMM bind exitoso pero sin conexión activa — reintentando...")
            ser.close()
            self._serial = None
            subprocess.run(["rfcomm", "release", "0"], capture_output=True, timeout=3)
            time.sleep(2.0)
            return self._try_rfcomm_bind(address, _retry + 1)

        self._serial = ser
        self._rfcomm_bound = True
        self._log_queue.put("Conexión Bluetooth por rfcomm bind")
        time.sleep(1.0)
        return True

    def _try_rfcomm_connect(self, address):
        self._log_queue.put(f"Ejecutando: rfcomm connect 0 {address} 1 (6s timeout)...")
        candidates = [
            ["rfcomm", "connect", "0", address, "1"],
            ["sudo", "-n", "rfcomm", "connect", "0", address, "1"],
        ]
        for cmd in candidates:
            t0 = time.time()
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                while time.time() - t0 < 6:
                    if os.path.exists(RFCOMM_DEVICE):
                        time.sleep(0.5)
                        if os.path.exists(RFCOMM_DEVICE):
                            self._log_queue.put("rfcomm connect exitoso")
                            return self._open_rfcomm_with_timeout(timeout=8)
                    time.sleep(0.2)
                proc.kill()
                proc.wait(timeout=2)
            except (FileNotFoundError, OSError) as e:
                self._log_queue.put(f"  error: {e}")
                continue
        self._log_queue.put("rfcomm connect falló (timeout)")
        return None

    def disconnect(self):
        self._cancel_reconnect()
        with self._lock:
            self._running = False
            self._protocol._firmware_ready = False
            was_rfcomm = self._rfcomm_bound
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        addr = self._address
        self._close_serial()
        if was_rfcomm:
            threading.Thread(target=self._release_rfcomm, daemon=True).start()
        with self._lock:
            self._rfcomm_bound = False
            self._connected = False
            self._address = None
            self._reconnect_count = 0
        if addr:
            self._log_queue.put(f"Desconectado de {addr}")

    def _release_rfcomm(self):
        try:
            subprocess.run(["rfcomm", "release", "0"], capture_output=True, timeout=3)
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-9", "-f", "rfcomm"], capture_output=True, timeout=3)
        except (FileNotFoundError, OSError):
            pass
        try:
            subprocess.run(
                ["sudo", "-n", "rfcomm", "release", "0"],
                capture_output=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    def _close_serial(self):
        ser = None
        with self._lock:
            if self._serial:
                ser = self._serial
                self._serial = None
        if ser:
            try:
                if self._is_socket:
                    try:
                        ser.settimeout(0.5)
                    except Exception:
                        pass
                    ser.close()
                elif hasattr(ser, "is_open") and ser.is_open:
                    ser.close()
            except Exception:
                pass

    def _full_cleanup(self):
        with self._lock:
            self._connected = False
        self._close_serial()
        threading.Thread(target=self._release_rfcomm, daemon=True).start()
        self._rfcomm_bound = False

    def _do_handshake(self):
        for hretry in range(3 if not self._is_socket else 1):
            with self._lock:
                ser = self._serial
                is_socket = self._is_socket
            if ser is None:
                return False
            for ping_cmd in ["PING\r\n", "PING\n"]:
                for attempt in range(3):
                    if is_socket:
                        try:
                            ser.settimeout(5)
                            ser.sendall(ping_cmd.encode())
                        except (OSError, socket.timeout):
                            self._log_queue.put(f"Handshake send falló (intento {attempt + 1})")
                            time.sleep(0.3)
                            continue
                    else:
                        try:
                            ser.write(ping_cmd.encode())
                            ser.flush()
                        except Exception:
                            self._log_queue.put(f"Handshake write falló (intento {attempt + 1})")
                            time.sleep(0.3)
                            continue
                    t0 = time.time()
                    while time.time() - t0 < 5:
                        try:
                            if is_socket:
                                remaining = 5 - (time.time() - t0)
                                ser.settimeout(min(1.0, max(0.1, remaining)))
                                resp = ser.recv(4096).decode("utf-8", errors="replace")
                            else:
                                resp = ser.read_until(b'\n').decode("utf-8", errors="replace")
                            if resp:
                                for line in resp.splitlines():
                                    line = line.strip()
                                    if line == "PONG":
                                        self._protocol._firmware_ready = True
                                        self._log_queue.put("Handshake OK")
                                        return True
                                    self._log_queue.put(f"RX: {line}")
                        except serial.SerialTimeoutException:
                            pass
                        except (OSError, socket.timeout):
                            pass
                    self._log_queue.put(f"Handshake intento {attempt + 1}/3 ({ping_cmd!r}) falló")
                    time.sleep(0.5)
            if hretry < 2:
                self._log_queue.put("Reconectando rfcomm para reintentar handshake...")
                self._close_serial()
                time.sleep(1)
                subprocess.run(["rfcomm", "release", "0"], capture_output=True, timeout=3)
                if not self._try_rfcomm_bind(self._address):
                    break
        return False

    def _ensure_nonblocking(self):
        if self._is_socket:
            return
        with self._lock:
            if self._serial is None:
                return
            fd = self._serial.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            if not (flags & os.O_NONBLOCK):
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _write_nonblocking(self, data, timeout=3):
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        with self._lock:
            if self._serial is None:
                return False
            ser = self._serial
            is_socket = self._is_socket
        t0 = time.time()
        if is_socket:
            for attempt in range(self.SEND_RETRIES):
                try:
                    prev_timeout = ser.gettimeout()
                    ser.settimeout(timeout)
                    ser.sendall(data_bytes)
                    ser.settimeout(prev_timeout if prev_timeout is not None else 0.2)
                    return True
                except socket.timeout:
                    if attempt < self.SEND_RETRIES - 1:
                        time.sleep(self.SEND_RETRY_DELAY)
                        continue
                    self._log_queue.put("Timeout BT al enviar datos (reintentos agotados)")
                    return False
                except OSError as e:
                    if attempt < self.SEND_RETRIES - 1:
                        time.sleep(self.SEND_RETRY_DELAY)
                        continue
                    self._log_queue.put(f"Error BT al escribir: {e}")
                    self._on_disconnect()
                    return False
            return False
        else:
            total = 0
            fd = ser.fileno()
            while total < len(data_bytes):
                remaining = timeout - (time.time() - t0)
                if remaining <= 0:
                    if total < len(data_bytes):
                        self._log_queue.put("Timeout serial al enviar datos")
                    return total >= len(data_bytes)
                _, wlist, _ = select.select([], [fd], [], min(remaining, 1.0))
                if not wlist:
                    continue
                try:
                    n = os.write(fd, data_bytes[total:])
                    if n > 0:
                        total += n
                except BlockingIOError:
                    time.sleep(0.01)
                    continue
                except OSError as e:
                    self._log_queue.put(f"Error BT al escribir: {e}")
                    self._on_disconnect()
                    return False
        return True

    def _write(self, data):
        with self._lock:
            if self._serial is None:
                return False
            self._ensure_nonblocking()
            if not self._write_nonblocking(data, timeout=2):
                self._on_disconnect()
                return False
            return True

    def send(self, servo_id, angle):
        if not self.is_connected:
            return False
        angle = max(-90, min(90, int(angle)))
        command = f"{servo_id} {angle}\n"
        ok = self._write(command)
        if ok:
            self._log_queue.put(f"Servo {servo_id} → {angle}° (BT)")
        return ok

    def send_config(self, num_servos, pins):
        if not self.is_connected:
            return False
        pins_str = " ".join(str(p) for p in pins)
        command = f"CONFIG {num_servos} {pins_str}\n"
        ok = self._write(command)
        if ok:
            self._log_queue.put(f"Config (BT) → {num_servos} DOF, pines: {pins_str}")
        return ok

    @staticmethod
    def discover_devices(timeout=10):
        devices = {}
        if sys.platform == "linux":
            # Method 1: active scan via bluetoothctl
            try:
                result = subprocess.run(
                    ["bluetoothctl", "--timeout", str(timeout), "scan", "on"],
                    capture_output=True, text=True, timeout=timeout + 5,
                )
                for line in (result.stdout + result.stderr).splitlines():
                    m = re.search(
                        r"NEW.*Device\s+([0-9A-F:]+)\s+(.+)", line
                    )
                    if m:
                        addr, name = m.group(1), m.group(2).strip()
                        if name and addr not in devices:
                            devices[addr] = name
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

            # Method 2: list all cached devices
            try:
                result = subprocess.run(
                    ["bluetoothctl", "devices"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.splitlines():
                    m = re.match(r"Device\s+([0-9A-F:]+)\s+(.+)", line)
                    if m:
                        addr, name = m.group(1), m.group(2).strip()
                        if addr not in devices:
                            devices[addr] = name
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

            # Method 3: hcitool as last resort
            if not devices:
                try:
                    result = subprocess.run(
                        ["hcitool", "scan"],
                        capture_output=True, text=True, timeout=timeout,
                    )
                    for line in result.stdout.splitlines():
                        m = re.match(r"\s+([0-9A-F:]+)\s+(.+)", line)
                        if m:
                            addr, name = m.group(1), m.group(2).strip()
                            devices[addr] = name
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass

        return list(devices.items())

    @staticmethod
    def _load_config():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _save_config(data):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

    @staticmethod
    def find_brazo_device(timeout=8):
        devices = BluetoothManager.discover_devices(timeout)
        for addr, name in devices:
            if BT_TARGET_NAME.lower() in name.lower():
                BluetoothManager._save_config({"last_addr": addr})
                return addr
        # Fallback: try cached address from previous session
        config = BluetoothManager._load_config()
        cached = config.get("last_addr")
        if cached:
            try:
                sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                sock.settimeout(3)
                sock.connect((cached, 1))
                sock.close()
                return cached
            except Exception:
                pass
        return None

    def _reader_loop(self):
        buffer = ""
        last_keepalive = time.time()
        last_data_time = time.time()
        while True:
            with self._lock:
                if not self._running:
                    break
                ser = self._serial
                is_socket = self._is_socket
                if ser is None:
                    break

            try:
                if is_socket:
                    try:
                        data = ser.recv(self.RECV_BUFFER_SIZE).decode("utf-8", errors="replace")
                    except socket.timeout:
                        data = ""
                    except OSError:
                        self._log_queue.put("BT recv error - conexión perdida")
                        self._on_disconnect()
                        return
                    if is_socket and not data:
                        if time.time() - last_data_time > 15:
                            self._log_queue.put("BT recv vacío prolongado — conexión cerrada")
                            self._on_disconnect()
                            return
                    else:
                        last_data_time = time.time()
                        last_keepalive = time.time()
                        buffer += data
                else:
                    if not ser.is_open:
                        self._log_queue.put("Puerto serial cerrado")
                        self._on_disconnect()
                        return
                    try:
                        data = ser.readline().decode("utf-8", errors="replace")
                        if data:
                            last_keepalive = time.time()
                            last_data_time = time.time()
                            buffer += data
                    except serial.SerialTimeoutException:
                        pass
                    except Exception:
                        self._log_queue.put("Error leyendo serial")
                        self._on_disconnect()
                        return

                if is_socket and time.time() - last_keepalive > self.KEEPALIVE_INTERVAL:
                    with self._lock:
                        if self._serial is None or not self._running:
                            break
                    data_bytes = b"PING\n"
                    for attempt in range(2):
                        try:
                            prev = ser.gettimeout()
                            ser.settimeout(self.KEEPALIVE_TIMEOUT)
                            ser.sendall(data_bytes)
                            ser.settimeout(prev if prev is not None else 0.2)
                            last_keepalive = time.time()
                            break
                        except (OSError, socket.timeout):
                            if attempt == 0:
                                time.sleep(0.1)
                            else:
                                self._log_queue.put("BT keepalive falló — conexión perdida")
                                self._on_disconnect()
                                return

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._protocol.process_line(line, self._handshake_event)
            except socket.timeout:
                pass
            except (OSError, ConnectionError, serial.SerialException) as e:
                self._log_queue.put(f"BT error: {type(e).__name__}: {e}")
                self._on_disconnect()
                return
            except Exception as e:
                if not self._running:
                    return
                self._log_queue.put(f"Error en lectura BT: {e}")
                return

    def _on_disconnect(self):
        with self._lock:
            was_connected = self._connected
            self._running = False
            self._connected = False
            self._protocol._firmware_ready = False
            addr = self._address
            self._address = None
        self._close_serial()
        if was_connected and self._disconnect_callback:
            try:
                self._disconnect_callback()
            except Exception:
                pass
            self._try_reconnect(addr)

    def _cancel_reconnect(self):
        self._reconnecting = False
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None

    def _try_reconnect(self, addr):
        if self._reconnecting:
            return
        if not self._reconnect_enabled or not addr:
            return
        if self._reconnect_count >= self._reconnect_max:
            self._log_queue.put("Reconexión agotada — conecte manualmente")
            self._reconnect_count = 0
            return
        self._reconnecting = True
        self._reconnect_count += 1
        if self._reconnect_callback:
            self._reconnect_callback(self._reconnect_count, self._reconnect_max)
        delay_idx = min(self._reconnect_count - 1, len(self.RECONNECT_DELAYS) - 1)
        delay = self.RECONNECT_DELAYS[delay_idx]
        self._log_queue.put(f"Reconectando ({self._reconnect_count}/{self._reconnect_max}) en {delay}s...")
        self._reconnect_timer = threading.Timer(delay, self._do_reconnect, args=[addr])
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _do_reconnect(self, addr):
        self._reconnecting = False
        if self.is_connected:
            return
        if not addr:
            self._log_queue.put("Reconexión cancelada — dirección inválida")
            return
        self._log_queue.put(f"Intentando reconexión a {addr}...")
        try:
            ok = self.connect(addr)
        except Exception as e:
            self._log_queue.put(f"Error en reconexión: {e}")
            ok = False
        if ok:
            self._reconnect_count = 0
            self._log_queue.put("Reconexión exitosa")
            if self._reconnect_success_callback:
                self._reconnect_success_callback()
        else:
            self._log_queue.put("Reconexión falló")
            self._try_reconnect(addr)
