import os
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
        self.filename = kwargs.get("filename") or (args[0] if args else None)
        if self.filename is None:
            raise ValueError("DeviceLogHandler requires a filename")
        self.logdir = "/".join(self.filename.split("/")[:-1])
        self.device = "unknown-device"
        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir)
        self.backupCountDays = kwargs.get("backupCount") or 0
        super().__init__(*args, **kwargs)
        
    def set_device(self, device):
        self.device = device
        date_str = timezone.now().strftime("%Y-%m-%d")
        name = self.filename.split('.')[0]
        self.baseFilename = f"{name}-{self.device}-{date_str}.log"
        self.clean_old_files()

    def emit(self, record):
        message = self.format(record)
        device = getattr(self, 'device', 'unknown-device')
        with open(self.baseFilename, 'a') as f:
            f.write(f"{device} -> {message}\n")
            
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
