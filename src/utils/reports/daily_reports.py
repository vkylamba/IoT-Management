from utils.reports.report_helpers import get_latest_report_data_for_period


def get_daily_report(device):
    return get_latest_report_data_for_period(device, 'yesterday')
