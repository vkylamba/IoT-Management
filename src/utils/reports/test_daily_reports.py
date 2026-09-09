from unittest.mock import Mock, patch
from django.test import SimpleTestCase

from .daily_reports import get_daily_report
from .monthly_reports import get_monthly_report
from .weekly_reports import get_weekly_report


class ReportGetterTests(SimpleTestCase):
    def test_get_daily_report_reads_latest_status_snapshot(self):
        device = Mock()
        expected_report = {"period": "yesterday"}
        with patch(
            'utils.reports.daily_reports.get_latest_report_data_for_period',
            return_value=expected_report,
        ) as latest_report_mock:
            report = get_daily_report(device)

        self.assertEqual(report, expected_report)
        latest_report_mock.assert_called_once_with(device, 'yesterday')

    def test_get_weekly_report_reads_latest_status_snapshot(self):
        device = Mock()
        expected_report = {"period": "week"}
        with patch(
            'utils.reports.weekly_reports.get_latest_report_data_for_period',
            return_value=expected_report,
        ) as latest_report_mock:
            report = get_weekly_report(device)

        self.assertEqual(report, expected_report)
        latest_report_mock.assert_called_once_with(device, 'week')

    def test_get_monthly_report_reads_latest_status_snapshot(self):
        device = Mock()
        expected_report = {"period": "month"}
        with patch(
            'utils.reports.monthly_reports.get_latest_report_data_for_period',
            return_value=expected_report,
        ) as latest_report_mock:
            report = get_monthly_report(device)

        self.assertEqual(report, expected_report)
        latest_report_mock.assert_called_once_with(device, 'month')
