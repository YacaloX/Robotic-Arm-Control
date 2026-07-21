"""
Tests for PSMoveController.
Mock psmoveapi since no physical hardware is available.
"""
import sys
import os
import math
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.psmove_controller import PSMoveController


class MockPSMoveAPI:
    def __init__(self):
        self.quit = False
        self._controllers = {}
        self._connected_handler = None

    def update(self):
        if self._connected_handler is None:
            self._connected_handler = True
            mock_ctrl = MagicMock()
            mock_ctrl.bluetooth = True
            mock_ctrl.serial = "MOCK1234"
            self.on_connect(mock_ctrl)

    def on_connect(self, controller):
        pass

    def on_update(self, controller):
        pass

    def on_disconnect(self, controller):
        pass


class MockButton:
    TRIANGLE = 1 << 4
    CIRCLE = 1 << 5
    CROSS = 1 << 6
    SQUARE = 1 << 7
    SELECT = 1 << 8
    START = 1 << 11
    PS = 1 << 16
    MOVE = 1 << 19
    T = 1 << 20


def _make_mock_psmoveapi_module():
    mod = types.ModuleType('psmoveapi')
    mod.PSMoveAPI = MockPSMoveAPI
    mod.RGB = lambda r, g, b: (r, g, b)
    mod.Button = MockButton
    return mod


def _install_mock_psmoveapi():
    mock_mod = _make_mock_psmoveapi_module()
    sys.modules['psmoveapi'] = mock_mod
    return mock_mod


def _remove_mock_psmoveapi():
    sys.modules.pop('psmoveapi', None)


class TestPSMoveControllerInit(unittest.TestCase):
    def setUp(self):
        self.ctrl = PSMoveController(log_callback=MagicMock())

    def test_initial_state(self):
        self.assertIsNone(self.ctrl._api)
        self.assertIsNone(self.ctrl._controller)
        self.assertEqual(self.ctrl._orientation, (0.0, 0.0))
        self.assertEqual(self.ctrl._position, (0.0, 0.0, 0.0))
        self.assertEqual(self.ctrl._trigger_value, 0.0)
        self.assertFalse(self.ctrl._connected)

    def test_defaults(self):
        self.assertEqual(PSMoveController.POLL_INTERVAL, 1.0 / 60.0)
        self.assertEqual(PSMoveController.ACCEL_SCALE, 4.0)
        self.assertEqual(PSMoveController.TRIGGER_THRESHOLD, 0.1)


class TestPSMoveAvailability(unittest.TestCase):
    def test_available_when_psmoveapi_installed(self):
        _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController()
            self.assertTrue(ctrl.available)
        finally:
            _remove_mock_psmoveapi()

    def test_available_when_psmoveapi_missing(self):
        _remove_mock_psmoveapi()
        ctrl = PSMoveController()
        self.assertFalse(ctrl.available)


class TestPSMoveConnect(unittest.TestCase):
    def test_connect_without_psmoveapi(self):
        _remove_mock_psmoveapi()
        ctrl = PSMoveController(log_callback=MagicMock())
        result = ctrl.connect()
        self.assertFalse(result)
        ctrl._log.assert_any_call("psmoveapi no disponible. Ver README para instalación.")

    def test_connect_when_already_connected(self):
        _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController(log_callback=MagicMock())
            ctrl._connected = True
            result = ctrl.connect()
            self.assertFalse(result)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_connect_creates_handler_and_thread(self):
        mock_mod = _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController(log_callback=MagicMock())
            result = ctrl.connect()
            self.assertTrue(result)
            self.assertIsNotNone(ctrl._api)
            self.assertIsInstance(ctrl._api, mock_mod.PSMoveAPI)
            ctrl._log.assert_any_call("Iniciando psmoveapi...")
            ctrl.stop()
        finally:
            _remove_mock_psmoveapi()

    def test_connect_api_thread_is_daemon(self):
        _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController(log_callback=MagicMock())
            ctrl.connect()
            self.assertTrue(ctrl._api_thread.daemon)
            ctrl.stop()
        finally:
            _remove_mock_psmoveapi()


class TestPSMoveStop(unittest.TestCase):
    def test_stop_clears_state(self):
        ctrl = PSMoveController(log_callback=MagicMock())
        ctrl._connected = True
        ctrl._running = True
        ctrl._api = MockPSMoveAPI()
        ctrl._controller = MagicMock()
        ctrl.stop()
        self.assertFalse(ctrl._enabled)
        self.assertFalse(ctrl._running)
        self.assertIsNone(ctrl._api)
        self.assertFalse(ctrl._connected)
        self.assertIsNone(ctrl._controller)

    def test_stop_logs_message(self):
        ctrl = PSMoveController(log_callback=MagicMock())
        ctrl.stop()
        ctrl._log.assert_called_with("Controlador PSMove detenido")


class TestPSMoveDisconnect(unittest.TestCase):
    def test_disconnect_calls_stop(self):
        ctrl = PSMoveController(log_callback=MagicMock())
        ctrl._connected = True
        ctrl._running = True
        ctrl.disconnect()
        self.assertFalse(ctrl._running)
        self.assertFalse(ctrl._connected)


class TestPSMoveUpdateTarget(unittest.TestCase):
    def setUp(self):
        self.ctrl = PSMoveController(log_callback=MagicMock())
        self.ctrl._enabled = True

    def test_center_orientation(self):
        self.ctrl._orientation = (0.0, 0.0)
        self.ctrl._trigger_value = 0.0
        self.ctrl._yaw_angle = 0.0
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertIsNotNone(target)
        self.assertEqual(target[0], 0)
        self.assertEqual(target[1], 0)
        self.assertEqual(target[3], 0)
        self.assertEqual(target[5], -20)

    def test_positive_pitch(self):
        self.ctrl._orientation = (45.0, 0.0)
        self.ctrl._trigger_value = 0.0
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertEqual(target[1], 90)

    def test_negative_roll(self):
        self.ctrl._orientation = (0.0, -30.0)
        self.ctrl._trigger_value = 0.0
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertEqual(target[0], -60)

    def test_trigger_above_threshold(self):
        self.ctrl._orientation = (0.0, 0.0)
        self.ctrl._trigger_value = 0.5
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertIsNotNone(target[5])
        expected = max(-20, min(45, round(-20 + 0.5 * 65)))
        self.assertEqual(target[5], expected)

    def test_trigger_below_threshold(self):
        self.ctrl._orientation = (0.0, 0.0)
        self.ctrl._trigger_value = 0.05
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        expected = max(-20, min(45, round(-20 + 0.05 * 65)))
        self.assertEqual(target[5], expected)

    def test_extreme_orientation_clamped(self):
        self.ctrl._orientation = (100.0, -100.0)
        self.ctrl._trigger_value = 0.0
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertEqual(target[0], -90)
        self.assertEqual(target[1], 90)

    def test_yaw_maps_to_servo3(self):
        self.ctrl._orientation = (0.0, 0.0)
        self.ctrl._trigger_value = 0.0
        self.ctrl._yaw_angle = 30.0
        self.ctrl._update_target()
        target = self.ctrl.read_target()
        self.assertEqual(target[3], 60)


class TestPSMoveGetters(unittest.TestCase):
    def test_get_orientation(self):
        ctrl = PSMoveController()
        ctrl._orientation = (25.5, -10.3)
        self.assertEqual(ctrl.get_orientation(), (25.5, -10.3))

    def test_get_position(self):
        ctrl = PSMoveController()
        ctrl._position = (1.0, 2.0, 3.0)
        self.assertEqual(ctrl.get_position(), (1.0, 2.0, 3.0))


class TestPSMoveSetLed(unittest.TestCase):
    def test_set_led_no_controller(self):
        ctrl = PSMoveController()
        ctrl.set_led(1.0, 0.0, 0.0)

    def test_set_led_with_controller(self):
        mock_mod = _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController()
            mock_controller = MagicMock()
            ctrl._controller = mock_controller
            ctrl._psmoveapi = mock_mod
            ctrl.set_led(1.0, 0.5, 0.0)
            self.assertEqual(mock_controller.color, (1.0, 0.5, 0.0))
        finally:
            _remove_mock_psmoveapi()

    def test_set_led_exception_swallows(self):
        _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController()
            ctrl._controller = MagicMock()
            ctrl._psmoveapi = MagicMock()
            ctrl._psmoveapi.RGB.side_effect = RuntimeError("fail")
            ctrl.set_led(1.0, 0.0, 0.0)
        finally:
            _remove_mock_psmoveapi()


class TestPSMoveSetRumble(unittest.TestCase):
    def test_set_rumble_no_controller(self):
        ctrl = PSMoveController()
        ctrl.set_rumble(0.5)

    def test_set_rumble_clamps_high(self):
        ctrl = PSMoveController()
        ctrl._controller = MagicMock()
        ctrl.set_rumble(2.0)
        self.assertEqual(ctrl._controller.rumble, 1.0)

    def test_set_rumble_clamps_low(self):
        ctrl = PSMoveController()
        ctrl._controller = MagicMock()
        ctrl.set_rumble(-1.0)
        self.assertEqual(ctrl._controller.rumble, 0.0)

    def test_set_rumble_normal(self):
        ctrl = PSMoveController()
        ctrl._controller = MagicMock()
        ctrl.set_rumble(0.7)
        self.assertEqual(ctrl._controller.rumble, 0.7)

    def test_set_rumble_exception_swallows(self):
        ctrl = PSMoveController()
        ctrl._controller = MagicMock()
        type(ctrl._controller).rumble = PropertyMock(side_effect=RuntimeError("fail"))
        ctrl.set_rumble(0.5)


class TestPSMoveHandlerCallback(unittest.TestCase):
    def _make_controller_with_api(self):
        mock_mod = _install_mock_psmoveapi()
        ctrl = PSMoveController(log_callback=MagicMock())
        ctrl.connect()
        return ctrl, mock_mod

    def test_handler_on_connect_sets_connected(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            mock_controller = MagicMock()
            mock_controller.bluetooth = True
            mock_controller.serial = "ABCD1234"

            ctrl._api.on_connect(mock_controller)

            self.assertTrue(ctrl._connected)
            self.assertEqual(ctrl._controller, mock_controller)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_connect_usb(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            mock_controller = MagicMock()
            mock_controller.bluetooth = False
            mock_controller.serial = "USB1234"

            ctrl._api.on_connect(mock_controller)

            self.assertTrue(ctrl._connected)
            ctrl._log.assert_any_call("PSMove conectado (USB): USB1234")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_connect_triggers_callback(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            cb = MagicMock()
            ctrl.set_connection_callback(cb)

            mock_controller = MagicMock()
            mock_controller.bluetooth = True
            mock_controller.serial = "ABCD1234"

            ctrl._api.on_connect(mock_controller)

            cb.assert_called_once_with(True)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_disconnect_clears_state(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._connected = True
            ctrl._controller = MagicMock()

            ctrl._api.on_disconnect(MagicMock())

            self.assertFalse(ctrl._connected)
            self.assertIsNone(ctrl._controller)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_disconnect_triggers_callback(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            cb = MagicMock()
            ctrl.set_connection_callback(cb)
            ctrl._connected = True

            ctrl._api.on_disconnect(MagicMock())

            cb.assert_called_once_with(False)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_disabled_skips(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = False

            mock_controller = MagicMock()
            ctrl._api.on_update(mock_controller)

            mock_controller.accelerometer.assert_not_called()
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_processes_orientation(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock()
            mock_controller.accelerometer.x = 2.0
            mock_controller.accelerometer.y = 0.0
            mock_controller.accelerometer.z = 3.5
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = MagicMock(return_value=False)

            ctrl._api.on_update(mock_controller)

            pitch, roll = ctrl._orientation
            self.assertIsInstance(pitch, float)
            self.assertIsInstance(roll, float)
            self.assertGreater(pitch, 0.0)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_button_triangle(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock(x=0, y=0, z=4)
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = lambda btn: btn == MockButton.TRIANGLE

            ctrl._api.on_update(mock_controller)

            self.assertEqual(ctrl.read_button(), "home")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_button_circle(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock(x=0, y=0, z=4)
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = lambda btn: btn == MockButton.CIRCLE

            ctrl._api.on_update(mock_controller)

            self.assertEqual(ctrl.read_button(), "save_posture")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_button_cross(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock(x=0, y=0, z=4)
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = lambda btn: btn == MockButton.CROSS

            ctrl._api.on_update(mock_controller)

            self.assertEqual(ctrl.read_button(), "add_posture")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_button_start(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock(x=0, y=0, z=4)
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = lambda btn: btn == MockButton.START

            ctrl._api.on_update(mock_controller)

            self.assertEqual(ctrl.read_button(), "play")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()

    def test_handler_on_update_button_select(self):
        ctrl, mock_mod = self._make_controller_with_api()
        try:
            ctrl._enabled = True

            mock_controller = MagicMock()
            mock_controller.accelerometer = MagicMock(x=0, y=0, z=4)
            mock_controller.trigger = 0.0
            mock_controller.pressed = 0
            mock_controller.buttons = 0
            mock_controller.released = 0
            mock_controller.now_pressed = lambda btn: btn == MockButton.SELECT

            ctrl._api.on_update(mock_controller)

            self.assertEqual(ctrl.read_button(), "stop")
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()


class TestPSMoveOrientationMath(unittest.TestCase):
    def _compute_orientation(self, ax, ay, az):
        scale = PSMoveController.ACCEL_SCALE
        ax_n = ax / scale
        ay_n = ay / scale
        az_n = az / scale

        az_clamped = max(0.01, abs(az_n))
        pitch = math.degrees(math.atan2(ax_n, math.sqrt(ay_n ** 2 + az_clamped ** 2)))
        roll = math.degrees(math.atan2(ay_n, math.sqrt(ax_n ** 2 + az_clamped ** 2)))
        pitch = max(-90.0, min(90.0, pitch))
        roll = max(-90.0, min(90.0, roll))
        return pitch, roll

    def test_flat_orientation(self):
        pitch, roll = self._compute_orientation(0, 0, 4)
        self.assertAlmostEqual(pitch, 0.0, places=1)
        self.assertAlmostEqual(roll, 0.0, places=1)

    def test_tilted_forward(self):
        pitch, roll = self._compute_orientation(2, 0, 3.5)
        self.assertGreater(pitch, 0.0)
        self.assertAlmostEqual(roll, 0.0, places=1)

    def test_tilted_right(self):
        pitch, roll = self._compute_orientation(0, 2, 3.5)
        self.assertAlmostEqual(pitch, 0.0, places=1)
        self.assertGreater(roll, 0.0)

    def test_negative_z_clamped(self):
        pitch, roll = self._compute_orientation(0, 0, -4)
        self.assertAlmostEqual(pitch, 0.0, places=1)
        self.assertAlmostEqual(roll, 0.0, places=1)


class TestPSMoveRunApi(unittest.TestCase):
    def test_run_api_stops_when_not_running(self):
        mock_mod = _install_mock_psmoveapi()
        try:
            ctrl = PSMoveController(log_callback=MagicMock())
            ctrl.connect()
            ctrl._running = False
            ctrl._api.quit = True
            ctrl._run_api()
            self.assertTrue(True)
        finally:
            ctrl.stop()
            _remove_mock_psmoveapi()


if __name__ == '__main__':
    unittest.main()
