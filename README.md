# Brazo Robótico 6 DOF

Control de brazo robótico multi-articulado vía USB Serial o Bluetooth SPP, con interfaz gráfica en Python (CustomTkinter), firmware ESP32 y app Android companion.

![Python](https://img.shields.io/badge/Python-3.12%2B-blue) ![ESP32](https://img.shields.io/badge/ESP32-Arduino-green) ![MIT App Inventor](https://img.shields.io/badge/App_Inventor-AIA-orange) ![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Características

- **Conexión dual**: Puerto serie USB (CP2102/CH340) o Bluetooth SPP
- **Control manual**: Sliders individuales por servo con botones de ajuste fino (±10°)
- **Secuencias**: Grabación, edición y reproducción de movimientos con interpolación suave
- **Keyframe compression**: Reduce grabaciones largas a posturas clave automáticamente
- **Mando Xbox**: Control por joysticks analógicos (XInput en Windows)
- **Paro de emergencia**: Botón y atajo `Ctrl+E` — envía HOME al instante
- **Auto-reconexión Bluetooth**: Reintenta hasta 3 veces si la conexión se pierde
- **App Android companion**: Escanea, conecta y controla desde un teléfono
- **Barra de estado**: Información en tiempo real de conexión, DOF y comandos
- **Configurable**: Hasta 6 servos, pines asignables, calibración por test

---

## 📦 Requisitos

### PC (Python)
```bash
pip install -r requirements.txt
```

### ESP32
- Arduino IDE o PlatformIO
- Placa: `ESP32 Dev Module`
- Librería: `BluetoothSerial`

### Android
- [MIT App Inventor 2](https://ai2.appinventor.mit.edu)
- Importar `android/Robotic_Arm_Control.aia` y generar APK

---

## 🚀 Uso rápido

### 1. Cargar firmware al ESP32
```bash
# En Arduino IDE: abrir arduino/robotic_arm/robotic_arm.ino
# Seleccionar placa: ESP32 Dev Module
# Upload
```

### 2. Iniciar la aplicación de escritorio
```bash
python main.pyw
```

### 3. Conectar
- **USB**: Seleccionar puerto (ej. `/dev/ttyUSB0`) y pulsar *Conectar*
- **Bluetooth**: Cambiar a modo Bluetooth, seleccionar *Brazo-Robotico* y conectar

### 4. Controlar
- Arrastrar sliders o usar botones ±10
- Grabar secuencias con el botón 🔴 *Grabar*
- Reproducir con ▶ *Reproducir*
- En Windows, conectar mando Xbox para control analógico

---

## 🔧 Estructura del proyecto

```
robotic_arm_control/
├── main.pyw                    # Punto de entrada de la app
├── requirements.txt            # Dependencias Python
├── android/
│   └── Robotic_Arm_Control.aia # App Android (MIT App Inventor)
├── arduino/
│   └── robotic_arm/
│       ├── robotic_arm.ino     # Firmware ESP32
│       └── robotic_arm.ino.test # Test de Bluetooth sin PWM
├── core/
│   ├── bluetooth_manager.py    # Gestión de conexión Bluetooth
│   ├── serial_manager.py       # Gestión de conexión serie USB
│   ├── robot_arm.py            # Modelo del brazo robótico
│   ├── sequence.py             # Reproductor de secuencias
│   └── xinput_controller.py    # Control por mando Xbox (Windows)
├── gui/
│   ├── app.py                  # Ventana principal y orquestación
│   ├── connection_frame.py     # Panel de conexión
│   ├── control_frame.py        # Panel de control de servos
│   ├── controller_frame.py     # Panel del mando Xbox
│   ├── sequence_frame.py       # Panel de secuencias
│   └── configurator_frame.py   # Ventana de configuración DOF/pines
├── utils/
│   ├── config_manager.py       # Persistencia de configuración
│   └── theme.py                # Paleta de colores (oscuro/claro)
└── tests/
    └── test_aia_blocks.py      # Validación de bloques App Inventor
```

---

## 🔌 Protocolo de comunicación

**Reglas del protocolo:**
- Todo comando enviado por el cliente **debe** terminar con LF (`\n`, 0x0A)
- Toda respuesta del ESP32 **siempre** termina con LF (`\n`, 0x0A)
- El ESP32 descarta buffers incompletos tras 500ms de inactividad

El ESP32 acepta comandos tanto por Serial USB como por Bluetooth SPP:

| Comando | Respuesta | Descripción |
|---------|-----------|-------------|
| `PING` | `PONG` | Verificación de conexión |
| `CHECK` | `CHECKED` | Health-check periódico |
| `STATUS` | `STATUS OK <n> <a0> <a1> ...` | Estado: n=servos, aN=ángulos actuales |
| `<id> <angulo>` | `OK servo <id> -> <angulo> deg` | Mover servo (-90 a 90) |
| `CONFIG <n> <p0> <p1> ...` | `CONFIG OK - <n> servos en pines: ...` | Reconfigurar DOF |

Nota: las respuestas de error siguen el formato `Error: <descripcion>` y también terminan con LF.

---

## 🧪 Tests

```bash
python tests/test_aia_blocks.py
```

Valida que los bloques del archivo `.aia` usen métodos reales de App Inventor (BluetoothClient, Notifier) y que las variables globales sean consistentes.

---

## 📄 Licencia

Este proyecto cuenta con una [Licencia MIT](LICENSE).

## 👤 Autor

**YacaloX**
