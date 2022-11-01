from device.models import DeviceProperty
from device.clickhouse_models import MeterData

from utils.dev_data import DataReports

WIDGETS = {
    "energy-weekly": {
        "name": "Energy Generated this week",
        "type": "Energy-Weekly",
        "description": "Energy Generated this week",
        "metadata": {"type": "chart", "chart_type": "bar"}
    }
}

USER_WIDGETS = {
    "Home": [
        {
            "widget": WIDGETS["energy-weekly"],

        }
    ]
}

def update_user_widgets(device):
    pass
