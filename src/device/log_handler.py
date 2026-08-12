import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from django.utils import timezone
from datetime import timedelta

def set_device_for_logger(logger, device):
    for handler in logger.handlers:
        if hasattr(handler, 'set_device'):
            handler.set_device(device)

class DeviceLogHandler(TimedRotatingFileHandler):

    def __init__(self, *args, **kwargs) -> None:
        init_args = list(args)
        self.filename = kwargs.get("filename") or (init_args[0] if init_args else None)
        if not self.filename:
            raise ValueError("DeviceLogHandler requires a filename")
        self.filename = os.path.abspath(self.filename)
        self.logdir = os.path.dirname(self.filename)
        self.device = "unknown-device"

        def apply_filename(target_filename: str) -> None:
            if "filename" in kwargs:
                kwargs["filename"] = target_filename
            elif init_args:
                init_args[0] = target_filename
            else:
                kwargs["filename"] = target_filename

        def fallback_to_tmp() -> None:
            fallback_dir = "/tmp/device-logs"
            os.makedirs(fallback_dir, exist_ok=True)
            self.logdir = fallback_dir
            self.filename = os.path.join(fallback_dir, os.path.basename(self.filename))

        try:
            if not os.path.exists(self.logdir):
                os.makedirs(self.logdir)
        except PermissionError:
            # Docker named volumes may be owned by root; fall back to writable tmp.
            fallback_to_tmp()

        apply_filename(self.filename)

        self.backupCountDays = kwargs.get("backupCount") or 0
        try:
            super().__init__(*init_args, **kwargs)
        except PermissionError:
            # File creation may still fail even if directory exists.
            fallback_to_tmp()
            apply_filename(self.filename)
            super().__init__(*init_args, **kwargs)
        self.baseFilename = os.path.abspath(self.filename)

    def get_device_filename(self) -> str:
        date_str = timezone.now().strftime("%Y-%m-%d")
        name, _ = os.path.splitext(self.filename)
        return os.path.abspath(f"{name}-{self.device}-{date_str}.log")
        
    def set_device(self, device):
        self.device = device
        self.baseFilename = self.get_device_filename()
        log_dir = os.path.dirname(self.baseFilename)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        self.clean_old_files()

    def emit(self, record):
        try:
            message = self.format(record)
            device = getattr(self, 'device', 'unknown-device')
            with open(self.baseFilename, 'a', encoding=self.encoding or 'utf-8') as f:
                f.write(f"{device} -> {message}\n")
        except Exception:
            sys.stderr.write(
                f"Failed to write device log record to {self.baseFilename}\n"
            )
            self.handleError(record)
            
    def clean_old_files(self) -> None:
        date_old = timezone.now() - timedelta(days=self.backupCountDays)
        date_old = date_old.strftime("%Y-%m-%d")
        files = os.listdir(self.logdir)
        files_to_remove = []
        for file in files:
            if file.endswith(f"-{date_old}.log"):
                files_to_remove.append(file)
        for file_to_remove in files_to_remove:
            os.remove(os.path.join(self.logdir, file_to_remove))
