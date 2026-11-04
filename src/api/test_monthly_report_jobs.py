from datetime import datetime
from unittest.mock import patch

import pytz
from api.monthly_report_jobs import is_last_day_of_month
from django.test import SimpleTestCase
from django.utils import timezone


class MonthlyReportJobScheduleTests(SimpleTestCase):
    def test_is_last_day_of_month(self):
        tz = timezone.get_current_timezone()
        last_day = timezone.make_aware(datetime(2026, 2, 28, 12, 0), tz)
        not_last = timezone.make_aware(datetime(2026, 2, 27, 12, 0), tz)
        self.assertTrue(is_last_day_of_month(last_day))
        self.assertFalse(is_last_day_of_month(not_last))

    @patch('event.tasks.enqueue_monthly_report_job')
    @patch('event.tasks.is_last_day_of_month', return_value=False)
    def test_monthly_energy_report_skips_when_not_last_day(self, _is_last_mock, enqueue_mock):
        from event.tasks import monthly_energy_report

        monthly_energy_report(1)
        enqueue_mock.assert_not_called()
