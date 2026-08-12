import logging
import os
from datetime import datetime, timezone as datetime_timezone
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from device.log_handler import DeviceLogHandler


class DeviceLogHandlerTests(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "device.log")

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_handler(self):
        handler = DeviceLogHandler(filename=self.log_path, when="midnight", backupCount=7, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def create_record(self, message):
        return logging.LogRecord(
            name="device",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_emit_uses_default_filename_before_set_device(self):
        handler = self.create_handler()
        self.assertEqual(handler.baseFilename, os.path.abspath(self.log_path))

        try:
            handler.emit(self.create_record("hello world"))
        finally:
            handler.close()

        with open(self.log_path, encoding="utf-8") as log_file:
            self.assertEqual(log_file.read().strip(), "unknown-device -> hello world")

    def test_set_device_updates_filename_and_emit_uses_device_name(self):
        handler = self.create_handler()
        current_time = datetime(2026, 8, 12, tzinfo=datetime_timezone.utc)

        with mock.patch("device.log_handler.timezone.now", return_value=current_time):
            handler.set_device("sensor-1")
            expected_filename = os.path.abspath(
                os.path.join(self.temp_dir.name, "device-sensor-1-2026-08-12.log")
            )
            self.assertEqual(handler.baseFilename, expected_filename)

            try:
                handler.emit(self.create_record("after set_device"))
            finally:
                handler.close()

        with open(expected_filename, encoding="utf-8") as log_file:
            self.assertEqual(log_file.read().strip(), "sensor-1 -> after set_device")

    def test_emit_logs_write_failures_and_handles_error(self):
        handler = self.create_handler()
        handler.handleError = mock.Mock()
        mock_logger = mock.Mock()

        try:
            with mock.patch("device.log_handler.open", side_effect=OSError("disk full")):
                with mock.patch("device.log_handler.logging.getLogger", return_value=mock_logger):
                    handler.emit(self.create_record("will fail"))
        finally:
            handler.close()

        mock_logger.exception.assert_called_once()
        handler.handleError.assert_called_once()
