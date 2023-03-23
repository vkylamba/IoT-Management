import pytest
from device.models import Device
from .daily_reports import get_daily_report


@pytest.mark.django_db
def test_daily_report_solar_pump_device():
    device = Device.objects.get(
        ip_address__iexact='0.0.0.13'
    )
    report = get_daily_report(device)
    assert report["device"] == device.alias
