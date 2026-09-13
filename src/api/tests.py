import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytz
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from api.utils import (
	backfill_status_processing_context_from_db_if_missing,
	build_status_processing_context,
	get_status_processing_context_from_status_cache,
	is_device_status_replay_locked,
	process_raw_data,
	replay_stored_raw_data,
	refresh_status_processing_context_boundaries,
	save_status_processing_context_to_status_cache,
	set_device_status_replay_lock,
)
from api.viewsets.device_details_views import _get_report_event_marker, _sync_report_events_for_device
from api.viewsets.device_views import _normalize_favorite_device_ids
from device.models import AssetStatus, Device, RawData, StatusCache, StatusType
from event.models import Action, DeviceEvent, EventType
from event.tasks import daily_energy_report
from device_schemas.schema import get_status_expression_helper_content, translate_data_from_schema
from utils.reports.report_helpers import get_report_status_type_for_period


class EventEquationTests(SimpleTestCase):
	def test_eval_equation_returns_true_for_none_equation(self):
		device_event = DeviceEvent(equation_threshold=None)
		device_event.typ = EventType(
			name="Auto Report",
			description="Auto report event",
			trigger_type="Time",
			equation=None,
		)

		self.assertTrue(device_event.eval_equation(data=Mock()))

	def test_eval_equation_returns_true_for_blank_equation(self):
		device_event = DeviceEvent(equation_threshold=None)
		device_event.typ = EventType(
			name="Auto Report",
			description="Auto report event",
			trigger_type="Time",
			equation="   ",
		)

		self.assertTrue(device_event.eval_equation(data=Mock()))


class SchemaTranslationTests(SimpleTestCase):
	def test_report_status_type_lookup_avoids_djongo_unsupported_active_filter(self):
		device = Mock()
		device.type = None
		class QuerySetLike(list):
			def order_by(self, *args, **kwargs):
				return self

		matching_type = Mock(active=True)
		query_set = QuerySetLike([matching_type])

		with patch('utils.reports.report_helpers.StatusType.objects.filter', return_value=query_set) as filter_mock:
			result = get_report_status_type_for_period(device, 'yesterday')

		self.assertIs(result, matching_type)
		self.assertEqual(filter_mock.call_count, 1)
		self.assertNotIn('active', filter_mock.call_args.kwargs)
		self.assertEqual(filter_mock.call_args.kwargs['device'], device)
		self.assertEqual(filter_mock.call_args.kwargs['target_type'], 'report')
		self.assertEqual(filter_mock.call_args.kwargs['report_period'], 'yesterday')

	def test_energy_expression_can_reference_current_sibling_field(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "meter_0.energy",
						"multiplier": 0.1,
						"offset": 0,
					},
					{
						"target": "energy_generated",
						"type": "calculated",
						"source": ".energy_consumed + meter_1.power * 120 / 3600000",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		test_data = {
			"meter_0": {"energy": 100},
			"meter_1": {"power": 300},
		}

		translated_data = translate_data_from_schema(schema, test_data)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed"], 10.0)
		self.assertAlmostEqual(
			translated_data["DAILY_STATUS"]["energy_generated"],
			10.01,
			places=6,
		)

	def test_first_today_helper_reads_initial_snapshot_and_keeps_value(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_generated",
						"type": "calculated",
						"source": "firstToday__energy_generated + meter_0.power * 120 / 3600000",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_generated_today",
						"type": "calculated",
						"source": "changeToday__energy_generated",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		test_data = {
			"meter_0": {"power": 100},
		}
		existing_statuses = {
			"firstToday": {
				"device": {"DAILY_STATUS": {"energy_generated": 12}},
				"raw": {},
			},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_generated": 15}},
				"raw": {},
			},
		}

		translated_data = translate_data_from_schema(schema, test_data, existing_statuses)

		self.assertAlmostEqual(
			translated_data["DAILY_STATUS"]["energy_generated"],
			12 + 100 * 120 / 3600000,
			places=6,
		)
		self.assertAlmostEqual(
			translated_data["DAILY_STATUS"]["energy_generated_today"],
			100 * 120 / 3600000,
			places=6,
		)
		self.assertEqual(
			existing_statuses["firstToday"]["device"]["DAILY_STATUS"]["energy_generated"],
			12,
		)

	def test_change_today_can_reference_current_calculated_field(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "lastValue__energy_consumed + meter_0.power * 120 / 3600000",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_consumed_today",
						"type": "calculated",
						"source": "changeToday__energy_consumed",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		test_data = {
			"meter_0": {"power": 100},
		}
		existing_statuses = {
			"firstToday": {
				"device": {"DAILY_STATUS": {"energy_consumed": 12}},
				"raw": {},
			},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_consumed": 15}},
				"raw": {},
			},
		}

		translated_data = translate_data_from_schema(schema, test_data, existing_statuses)

		self.assertAlmostEqual(
			translated_data["DAILY_STATUS"]["energy_consumed"],
			15 + 100 * 120 / 3600000,
			places=6,
		)
		self.assertAlmostEqual(
			translated_data["DAILY_STATUS"]["energy_consumed_today"],
			3 + 100 * 120 / 3600000,
			places=6,
		)

	def test_change_today_seeds_missing_first_today_baseline(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "lastValue__energy_consumed + 400",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_consumed_today",
						"type": "calculated",
						"source": "changeToday__energy_consumed",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		existing_statuses = {
			"firstToday": {},
			"lastToday": {},
			"firstThisMonth": {},
		}

		translated_data = translate_data_from_schema(schema, {}, existing_statuses)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed"], 400)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed_today"], 0)
		self.assertEqual(
			existing_statuses["firstToday"]["device"]["DAILY_STATUS"]["energy_consumed"],
			400,
		)

	def test_change_today_prefers_previous_day_last_baseline(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "lastValue__energy_consumed + 10",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_consumed_today",
						"type": "calculated",
						"source": "changeToday__energy_consumed",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		existing_statuses = {
			"firstToday": {},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_consumed": 150}},
				"raw": {},
			},
			"firstThisMonth": {},
			"lastYesterday": {
				"device": {"DAILY_STATUS": {"energy_consumed": 120}},
				"raw": {},
			},
		}

		translated_data = translate_data_from_schema(schema, {}, existing_statuses)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed"], 160)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed_today"], 40)

	def test_change_this_month_seeds_missing_first_month_baseline(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "lastValue__energy_consumed + 400",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_consumed_this_month",
						"type": "calculated",
						"source": "changeThisMonth__energy_consumed",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		existing_statuses = {
			"firstToday": {},
			"lastToday": {},
			"firstThisMonth": {},
		}

		translated_data = translate_data_from_schema(schema, {}, existing_statuses)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed"], 400)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed_this_month"], 0)
		self.assertEqual(
			existing_statuses["firstThisMonth"]["device"]["DAILY_STATUS"]["energy_consumed"],
			400,
		)

	def test_change_this_month_prefers_previous_month_last_baseline(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_consumed",
						"type": "calculated",
						"source": "lastValue__energy_consumed + 10",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_consumed_this_month",
						"type": "calculated",
						"source": "changeThisMonth__energy_consumed",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		existing_statuses = {
			"firstToday": {},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_consumed": 150}},
				"raw": {},
			},
			"firstThisMonth": {},
			"lastPreviousMonth": {
				"device": {"DAILY_STATUS": {"energy_consumed": 90}},
				"raw": {},
			},
		}

		translated_data = translate_data_from_schema(schema, {}, existing_statuses)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed"], 160)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_consumed_this_month"], 70)

	def test_last_value_energy_exported_uses_last_today_after_day_rollover(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_exported",
						"type": "calculated",
						"source": "lastValue__energy_exported + 25",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_exported_this_day",
						"type": "calculated",
						"source": "changeToday__energy_exported",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]
		existing_statuses = {
			"firstToday": {},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_exported": 200}},
				"raw": {},
			},
			"firstThisMonth": {},
		}

		translated_data = translate_data_from_schema(schema, {}, existing_statuses)

		self.assertEqual(translated_data["DAILY_STATUS"]["energy_exported"], 225)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_exported_this_day"], 0)
		self.assertEqual(
			existing_statuses["firstToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			225,
		)

	def test_full_status_schema_can_resolve_fields_needed_during_replay(self):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{"target": "load_status", "type": "raw", "source": "meter_1.power", "multiplier": 1, "offset": 0},
					{"target": "solar_status", "type": "raw", "source": "meter_2.power", "multiplier": 1, "offset": 0},
					{"target": "energy_generated_this_day", "type": "calculated", "source": "changeToday__energy_generated", "multiplier": 1, "offset": 0},
					{"target": "energy_consumed_this_day", "type": "calculated", "source": "changeToday__energy_consumed", "multiplier": 1, "offset": 0},
					{"target": "energy_revenue_this_day", "type": "calculated", "source": "changeToday__energy_revenue", "multiplier": 1, "offset": 0},
					{"target": "weather", "type": "dataCache", "source": "weather", "multiplier": 1, "offset": 0},
					{"target": "net_meter_power_factor", "type": "raw", "source": "meter_0.powerFactor", "multiplier": 1, "offset": 0},
					{"target": "system_temperature", "type": "raw", "source": "dht.temperature", "multiplier": 1, "offset": 0},
					{"target": "system_humidity", "type": "raw", "source": "dht.humidity", "multiplier": 1, "offset": 0},
					{"target": "battery_charging_status", "type": "calculated", "source": "meter_2.power - meter_1.power if meter_2.power > meter_1.power + meter_0.power else meter_0.power - meter_1.power", "multiplier": 1, "offset": 0},
					{"target": "net_meter_status", "type": "calculated", "source": "meter_0.power if meter_2.power > meter_1.power + meter_0.power else -1 * meter_0.power", "multiplier": 1, "offset": 0},
					{"target": "system_status", "type": "calculated", "source": "\"Exporting\" if meter_2.power > meter_1.power + meter_0.power else \"Importing\"", "multiplier": 1, "offset": 0},
					{"target": "energy_generated", "type": "calculated", "source": "lastValue__energy_generated  + meter_2.power * 120 / 3600000", "multiplier": 1, "offset": 0},
					{"target": "energy_consumed", "type": "calculated", "source": "lastValue__energy_consumed + meter_1.power * 120 / 3600000", "multiplier": 1, "offset": 0},
					{"target": "energy_revenue", "type": "calculated", "source": "lastValue__energy_revenue + meter_0.power * 120 / 3600000", "multiplier": 1, "offset": 0},
				],
			}
		]
		test_data = {
			"meter_0": {"power": 100, "powerFactor": 0.95},
			"meter_1": {"power": 500},
			"meter_2": {"power": 700},
			"dht": {"temperature": 26.5, "humidity": 61},
		}
		existing_statuses = {
			"firstToday": {
				"device": {"DAILY_STATUS": {"energy_generated": 5.0, "energy_consumed": 3.0, "energy_revenue": 1.0}},
				"raw": {},
			},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_generated": 9.0, "energy_consumed": 7.0, "energy_revenue": 2.0}},
				"raw": {},
			},
		}
		data_cache = {
			"weather": {"condition": "sunny"},
		}

		translated_data = translate_data_from_schema(schema, test_data, existing_statuses, data_cache)
		status_data = translated_data["DAILY_STATUS"]

		self.assertEqual(set(status_data.keys()), {
			"load_status",
			"solar_status",
			"energy_generated_this_day",
			"energy_consumed_this_day",
			"energy_revenue_this_day",
			"weather",
			"net_meter_power_factor",
			"system_temperature",
			"system_humidity",
			"battery_charging_status",
			"net_meter_status",
			"system_status",
			"energy_generated",
			"energy_consumed",
			"energy_revenue",
		})
		self.assertEqual(status_data["load_status"], 500)
		self.assertEqual(status_data["solar_status"], 700)
		self.assertEqual(status_data["weather"], {"condition": "sunny"})
		self.assertEqual(status_data["net_meter_power_factor"], 0.95)
		self.assertEqual(status_data["system_temperature"], 26.5)
		self.assertEqual(status_data["system_humidity"], 61)
		self.assertEqual(status_data["battery_charging_status"], 200)
		self.assertEqual(status_data["net_meter_status"], 100)
		self.assertEqual(status_data["system_status"], "Exporting")
		self.assertAlmostEqual(status_data["energy_generated"], 9 + 700 * 120 / 3600000, places=6)
		self.assertAlmostEqual(status_data["energy_consumed"], 7 + 500 * 120 / 3600000, places=6)
		self.assertAlmostEqual(status_data["energy_revenue"], 2 + 100 * 120 / 3600000, places=6)
		self.assertAlmostEqual(
			status_data["energy_generated_this_day"],
			status_data["energy_generated"] - 5.0,
			places=6,
		)
		self.assertAlmostEqual(
			status_data["energy_consumed_this_day"],
			status_data["energy_consumed"] - 3.0,
			places=6,
		)
		self.assertAlmostEqual(
			status_data["energy_revenue_this_day"],
			1 + 100 * 120 / 3600000,
			places=6,
		)

	def test_status_translation_accepts_raw_fields_payload_and_validates_status(self):
		raw_schema_payload = {
			"fields": [
				{"target": "pay_per_unit", "type": "calculated", "source": "10 * 1", "multiplier": 1, "offset": 0},
				{"target": "load_status", "type": "raw", "source": "meter_3.power", "multiplier": 1, "offset": 0},
				{"target": "car_charging_status", "type": "raw", "source": "meter_4.power", "multiplier": 1, "offset": 0},
				{"target": "weather", "type": "dataCache", "source": "weather", "multiplier": 1, "offset": 0},
				{"target": "net_meter_power_factor", "type": "raw", "source": "meter_3.powerFactor", "multiplier": 1, "offset": 0},
				{"target": "system_temperature", "type": "raw", "source": "dht.temperature", "multiplier": 1, "offset": 0},
				{"target": "system_humidity", "type": "raw", "source": "dht.humidity", "multiplier": 1, "offset": 0},
				{"target": "system_status", "type": "calculated", "source": "\"Exporting\" if .net_meter_power_factor < 0 else \"Importing\"", "multiplier": 1, "offset": 0},
				{"target": "net_meter_status", "type": "calculated", "source": "meter_3.power if .net_meter_power_factor < 0 else -1 * meter_3.power", "multiplier": 1, "offset": 0},
				{"target": "energy_imported", "type": "calculated", "source": "lastValue__energy_imported + (-1 * .net_meter_status if .net_meter_status < 0 else 0) * 120 / 3600000", "multiplier": 1, "offset": 0},
				{"target": "energy_exported", "type": "calculated", "source": "lastValue__energy_exported + (1 * .net_meter_status if .net_meter_status > 0 else 0) * 120 / 3600000", "multiplier": 1, "offset": 0},
				{"target": "energy_exported_this_day", "type": "calculated", "source": "changeToday__energy_exported", "multiplier": 1, "offset": 0},
				{"target": "energy_exported_this_month", "type": "calculated", "source": "changeThisMonth__energy_exported", "multiplier": 1, "offset": 0},
				{"target": "energy_imported_this_day", "type": "calculated", "source": "changeToday__energy_imported", "multiplier": 1, "offset": 0},
				{"target": "energy_imported_this_month", "type": "calculated", "source": "changeThisMonth__energy_imported", "multiplier": 1, "offset": 0},
				{"target": "monthly_bill_amount", "type": "calculated", "source": ".energy_imported_this_month * .pay_per_unit", "multiplier": 1, "offset": 0},
				{"target": "timeUTC", "type": "raw", "source": "timeUTC", "multiplier": 1, "offset": 0},
			],
		}
		schema = [{"target": "device", "name": "DAILY_STATUS", **raw_schema_payload}]

		fixture_path = Path(__file__).resolve().parent.parent / "device_schemas" / "schemas" / "sample-raw-data.json"
		raw_samples = json.loads(fixture_path.read_text())
		meter_sample = next(
			record["data"]
			for record in raw_samples
			if record.get("data_type") == "meters-data"
		)

		base_data = {
			"meter_3": {
				"power": meter_sample.get("meter_3", {}).get("power", 360),
				"powerFactor": meter_sample.get("meter_3", {}).get("powerFactor", 0.56),
			},
			"meter_4": {
				"power": meter_sample.get("meter_4", {}).get("power", 0),
			},
			"dht": {
				"temperature": meter_sample.get("dht", {}).get("temperature", 26.5),
				"humidity": meter_sample.get("dht", {}).get("humidity", 61),
			},
			"timeUTC": meter_sample.get("timeUTC", "2026-09-10T10:00:00Z"),
		}
		existing_statuses = {
			"firstToday": {
				"device": {"DAILY_STATUS": {"energy_exported": 3.0, "energy_imported": 4.0}},
				"raw": {},
			},
			"lastToday": {
				"device": {"DAILY_STATUS": {"energy_exported": 7.0, "energy_imported": 8.0}},
				"raw": {},
			},
			"firstThisMonth": {
				"device": {"DAILY_STATUS": {"energy_exported": 2.0, "energy_imported": 1.0}},
				"raw": {},
			},
		}
		data_cache = {"weather": {"condition": "cloudy"}}

		exporting_data = {
			**base_data,
			"meter_3": {
				"power": base_data["meter_3"]["power"],
				"powerFactor": -abs(base_data["meter_3"]["powerFactor"]),
			},
		}
		exporting_status = translate_data_from_schema(
			schema,
			exporting_data,
			existing_statuses,
			data_cache,
		)["DAILY_STATUS"]

		self.assertEqual(exporting_status["pay_per_unit"], 10)
		self.assertEqual(exporting_status["load_status"], base_data["meter_3"]["power"])
		self.assertEqual(exporting_status["car_charging_status"], base_data["meter_4"]["power"])
		self.assertEqual(exporting_status["weather"], {"condition": "cloudy"})
		self.assertEqual(exporting_status["system_temperature"], base_data["dht"]["temperature"])
		self.assertEqual(exporting_status["system_humidity"], base_data["dht"]["humidity"])
		self.assertEqual(exporting_status["system_status"], "Exporting")
		self.assertEqual(exporting_status["net_meter_status"], base_data["meter_3"]["power"])
		self.assertAlmostEqual(exporting_status["energy_imported"], 8.0, places=6)
		self.assertAlmostEqual(
			exporting_status["energy_exported"],
			7.0 + base_data["meter_3"]["power"] * 120 / 3600000,
			places=6,
		)
		self.assertAlmostEqual(
			exporting_status["energy_exported_this_day"],
			exporting_status["energy_exported"] - 3.0,
			places=6,
		)
		self.assertAlmostEqual(
			exporting_status["energy_exported_this_month"],
			exporting_status["energy_exported"] - 2.0,
			places=6,
		)
		self.assertAlmostEqual(exporting_status["energy_imported_this_day"], 4.0, places=6)
		self.assertAlmostEqual(exporting_status["energy_imported_this_month"], 7.0, places=6)
		self.assertAlmostEqual(exporting_status["monthly_bill_amount"], 70.0, places=6)
		self.assertEqual(exporting_status["timeUTC"], base_data["timeUTC"])

		importing_data = {
			**base_data,
			"meter_3": {
				"power": base_data["meter_3"]["power"],
				"powerFactor": abs(base_data["meter_3"]["powerFactor"]),
			},
		}
		importing_status = translate_data_from_schema(
			schema,
			importing_data,
			existing_statuses,
			data_cache,
		)["DAILY_STATUS"]

		self.assertEqual(importing_status["system_status"], "Importing")
		self.assertEqual(importing_status["net_meter_status"], -base_data["meter_3"]["power"])
		self.assertAlmostEqual(importing_status["energy_exported"], 7.0, places=6)
		self.assertAlmostEqual(
			importing_status["energy_imported"],
			8.0 + base_data["meter_3"]["power"] * 120 / 3600000,
			places=6,
		)


class StatusProcessingContextTests(TestCase):
	@patch("api.utils.build_status_processing_context")
	def test_backfill_context_reads_from_db_when_last_today_missing(self, build_context_mock):
		db_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 180}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 200}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 120}}},
			},
			"last_status_models_by_target": {"device": Mock()},
			"current_raw_data": {"meter_0": {"power": 100}},
			"day_start_utc": datetime(2026, 5, 2, 0, 0, tzinfo=pytz.utc),
			"month_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
		}
		build_context_mock.return_value = db_context

		status_processing_context = {
			"existing_statuses": {
				"firstToday": {},
				"lastToday": {},
				"firstThisMonth": {},
			},
			"last_status_models_by_target": {},
			"current_raw_data": {},
		}

		backfill_status_processing_context_from_db_if_missing(
			status_processing_context,
			user=Mock(),
			device=Mock(),
			last_raw_data=None,
			as_of_time=datetime(2026, 5, 2, 0, 5, tzinfo=pytz.utc),
		)

		self.assertEqual(
			status_processing_context["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			200,
		)
		self.assertEqual(status_processing_context["current_raw_data"], {"meter_0": {"power": 100}})
		self.assertEqual(
			status_processing_context["existing_statuses"]["firstToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			180,
		)
		build_context_mock.assert_called_once()

	@patch("api.utils.build_status_processing_context")
	def test_backfill_context_keeps_existing_cached_snapshots(self, build_context_mock):
		status_processing_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 181}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 201}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 121}}},
			},
			"last_status_models_by_target": {"device": Mock()},
			"current_raw_data": {"meter_0": {"power": 101}},
		}

		backfill_status_processing_context_from_db_if_missing(
			status_processing_context,
			user=Mock(),
			device=Mock(),
			last_raw_data=None,
		)

		build_context_mock.assert_not_called()
		self.assertEqual(
			status_processing_context["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			201,
		)

	def test_day_boundary_reset_still_allows_last_value_energy_exported(self):
		device = Mock()
		device.get_timezone.return_value = pytz.utc

		status_processing_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 195}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 200}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 120}}},
			},
			"day_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
			"month_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
		}

		refresh_status_processing_context_boundaries(
			status_processing_context,
			device,
			datetime(2026, 5, 2, 0, 5, tzinfo=pytz.utc),
		)

		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "energy_exported",
						"type": "calculated",
						"source": "lastValue__energy_exported + 25",
						"multiplier": 1,
						"offset": 0,
					},
					{
						"target": "energy_exported_this_day",
						"type": "calculated",
						"source": "changeToday__energy_exported",
						"multiplier": 1,
						"offset": 0,
					},
				],
			}
		]

		translated_data = translate_data_from_schema(
			schema,
			{},
			status_processing_context["existing_statuses"],
		)

		self.assertEqual(
			status_processing_context["existing_statuses"]["lastYesterday"]["device"]["DAILY_STATUS"]["energy_exported"],
			200,
		)
		self.assertEqual(status_processing_context["existing_statuses"]["firstToday"], {})
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_exported"], 225)
		self.assertEqual(translated_data["DAILY_STATUS"]["energy_exported_this_day"], 25)

	def test_refresh_context_resets_first_today_on_new_day(self):
		device = Mock()
		device.get_timezone.return_value = pytz.utc

		status_processing_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy": 10}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy": 20}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy": 5}}},
			},
			"day_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
			"month_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
		}

		refresh_status_processing_context_boundaries(
			status_processing_context,
			device,
			datetime(2026, 5, 2, 10, 30, tzinfo=pytz.utc),
		)

		self.assertEqual(status_processing_context["existing_statuses"]["firstToday"], {})
		self.assertEqual(
			status_processing_context["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy"],
			20,
		)
		self.assertEqual(
			status_processing_context["existing_statuses"]["firstThisMonth"]["device"]["DAILY_STATUS"]["energy"],
			5,
		)

	def test_refresh_context_resets_first_this_month_on_new_month(self):
		device = Mock()
		device.get_timezone.return_value = pytz.utc

		status_processing_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy": 10}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy": 20}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy": 5}}},
			},
			"day_start_utc": datetime(2026, 5, 31, 0, 0, tzinfo=pytz.utc),
			"month_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
		}

		refresh_status_processing_context_boundaries(
			status_processing_context,
			device,
			datetime(2026, 6, 1, 0, 5, tzinfo=pytz.utc),
		)

		self.assertEqual(status_processing_context["existing_statuses"]["firstToday"], {})
		self.assertEqual(status_processing_context["existing_statuses"]["firstThisMonth"], {})
		self.assertEqual(
			status_processing_context["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy"],
			20,
		)

	@patch("api.utils.cache.get")
	@patch("api.utils.cache.set")
	def test_build_status_processing_context_cache_hit_avoids_db_rebuild(self, cache_set_mock, cache_get_mock):
		device = Mock()
		device.pk = 42
		device.get_timezone.return_value = pytz.utc
		cached_context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 5}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 10}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 1}}},
			},
			"last_status_models_by_target": {"device": Mock()},
			"current_raw_data": {"meter_0": {"power": 22}},
			"day_start_utc": datetime(2026, 5, 2, 0, 0, tzinfo=pytz.utc),
			"month_start_utc": datetime(2026, 5, 1, 0, 0, tzinfo=pytz.utc),
		}
		cache_get_mock.return_value = cached_context

		result = build_status_processing_context(
			user=Mock(pk=7),
			device=device,
			last_raw_data=None,
			as_of_time=datetime(2026, 5, 2, 0, 5, tzinfo=pytz.utc),
		)

		self.assertEqual(result["current_raw_data"]["meter_0"]["power"], 22)
		self.assertEqual(result["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy_exported"], 10)
		cache_set_mock.assert_not_called()

	@patch("api.utils.create_model_instance")
	@patch("api.utils.CLICKHOUSE_ENABLED", True)
	@patch("api.utils.update_user_and_device_statuses")
	@patch("api.utils._submit_background_device_enrichment")
	def test_process_raw_data_submits_background_enrichment_without_waiting(self, submit_mock, update_status_mock, *args):
		device = Device.objects.create(ip_address="192.168.1.77", alias="bg-device", other_data={"device_load_detection_on": True})
		message_data = {
			"last_update_time": "2026-09-13T12:00:00+00:00",
			"meter_0": {"power": 42},
		}

		result = process_raw_data(device, message_data, channel="api", data_type="data", user=None)

		self.assertEqual(result, "")
		self.assertEqual(submit_mock.call_count, 1)
		self.assertEqual(update_status_mock.call_count, 1)

	def test_status_expression_helper_content_lists_supported_sections(self):
		helper_data = get_status_expression_helper_content({
			"meter_0": {"power": 100, "powerFactor": 0.95},
			"dht": {"temperature": 25},
		})

		self.assertEqual(helper_data["summary"]["title"], "Status Expression Helper")
		self.assertTrue(any(item["value"] == "device" for item in helper_data["status_targets"]))
		self.assertTrue(any(item["value"] == "calculated" for item in helper_data["field_types"]))
		self.assertTrue(any(item["syntax"] == "lastValue__energy_generated" for item in helper_data["expression_sources"]))
		self.assertTrue(any(item["syntax"] == "firstToday__energy_generated" for item in helper_data["expression_sources"]))
		self.assertTrue(any(item["syntax"] == "lastToday__energy_generated" for item in helper_data["expression_sources"]))
		self.assertTrue(any(item["name"] == "firstToday" for item in helper_data["history_context"]))
		self.assertIn("meter_0.power", helper_data["available_raw_fields"])
		self.assertIn("dht.temperature", helper_data["available_raw_fields"])

	def test_status_cache_hydrates_context_without_requerying_db(self):
		device = Device.objects.create(ip_address="192.168.1.50", alias="cache-device")
		status_type = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)
		StatusCache.objects.create(
			device=device,
			status_type=status_type,
			cache_data={
				"existing_statuses": {
					"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 180}}},
					"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 200}}},
					"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 120}}},
				},
				"current_raw_data": {"meter_0": {"power": 100}},
				"day_start_utc": "2026-05-02T00:00:00Z",
				"month_start_utc": "2026-05-01T00:00:00Z",
			},
		)

		context = get_status_processing_context_from_status_cache(status_type, device, None)

		self.assertEqual(
			context["existing_statuses"]["firstToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			180,
		)
		self.assertEqual(
			context["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy_exported"],
			200,
		)
		self.assertEqual(context["current_raw_data"]["meter_0"]["power"], 100)

	def test_status_cache_ignores_runtime_status_model_instances_when_saving(self):
		device = Device.objects.create(ip_address="192.168.1.60", alias="cache-model-device")
		status_type = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)
		status_model = AssetStatus.objects.create(
			name="DAILY_STATUS",
			device=device,
			status={"energy_exported": 200},
		)

		context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 180}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 200}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 120}}},
			},
			"current_raw_data": {"meter_0": {"power": 100}},
			"last_status_models_by_target": {"device": status_model},
		}

		record = save_status_processing_context_to_status_cache(context, None, device, status_type)

		self.assertIsNotNone(record)
		self.assertNotIn("last_status_models_by_target", record.cache_data)
		self.assertEqual(record.cache_data["existing_statuses"]["lastToday"]["device"]["DAILY_STATUS"]["energy_exported"], 200)

	def test_status_cache_serializes_datetime_boundaries(self):
		device = Device.objects.create(ip_address="192.168.1.61", alias="cache-datetime-device")
		status_type = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)
		day_start = datetime(2026, 9, 9, 0, 0, tzinfo=pytz.utc)
		month_start = datetime(2026, 9, 1, 0, 0, tzinfo=pytz.utc)

		context = {
			"existing_statuses": {
				"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 10}}},
				"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 20}}},
				"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 5}}},
			},
			"current_raw_data": {"meter_0": {"power": 100}},
			"day_start_utc": day_start,
			"month_start_utc": month_start,
		}

		record = save_status_processing_context_to_status_cache(context, None, device, status_type)

		self.assertIsInstance(record.cache_data["day_start_utc"], str)
		self.assertIsInstance(record.cache_data["month_start_utc"], str)
		self.assertEqual(record.cache_data["day_start_utc"], day_start.isoformat())
		self.assertEqual(record.cache_data["month_start_utc"], month_start.isoformat())

	def test_status_cache_save_deduplicates_same_device_and_status_type(self):
		device = Device.objects.create(ip_address="192.168.1.62", alias="cache-dup-device")
		status_type = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)

		StatusCache.objects.create(
			device=device,
			status_type=status_type,
			cache_data={"current_raw_data": {"meter_0": {"power": 1}}},
		)
		StatusCache.objects.create(
			device=device,
			status_type=status_type,
			cache_data={"current_raw_data": {"meter_0": {"power": 2}}},
		)

		save_status_processing_context_to_status_cache(
			{
				"existing_statuses": {
					"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 10}}},
					"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 20}}},
					"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 5}}},
				},
				"current_raw_data": {"meter_0": {"power": 123}},
			},
			None,
			device,
			status_type,
		)

		rows = list(StatusCache.objects.filter(device=device, status_type=status_type).order_by('-updated_at'))
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].cache_data["current_raw_data"]["meter_0"]["power"], 123)

	def test_status_cache_save_deduplicates_by_device_and_status_name(self):
		device = Device.objects.create(ip_address="192.168.1.63", alias="cache-name-dup-device")
		status_type_1 = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)
		status_type_2 = StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
		)

		StatusCache.objects.create(
			device=device,
			status_type=status_type_1,
			cache_data={"current_raw_data": {"meter_0": {"power": 11}}},
		)
		StatusCache.objects.create(
			device=device,
			status_type=status_type_2,
			cache_data={"current_raw_data": {"meter_0": {"power": 22}}},
		)

		save_status_processing_context_to_status_cache(
			{
				"existing_statuses": {
					"firstToday": {"device": {"DAILY_STATUS": {"energy_exported": 10}}},
					"lastToday": {"device": {"DAILY_STATUS": {"energy_exported": 20}}},
					"firstThisMonth": {"device": {"DAILY_STATUS": {"energy_exported": 5}}},
				},
				"current_raw_data": {"meter_0": {"power": 333}},
			},
			None,
			device,
			status_type_2,
		)

		rows = list(
			StatusCache.objects.filter(device=device, status_type__name="DAILY_STATUS").order_by('-updated_at')
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].status_type_id, status_type_2.id)
		self.assertEqual(rows[0].cache_data["current_raw_data"]["meter_0"]["power"], 333)


class FavoriteDevicesTests(SimpleTestCase):
	def test_normalize_favorite_device_ids_casts_and_deduplicates(self):
		self.assertEqual(
			_normalize_favorite_device_ids([1, "1", 2, "2", None, ""]),
			["1", "2"],
		)

	def test_normalize_favorite_device_ids_handles_non_list(self):
		self.assertEqual(_normalize_favorite_device_ids(None), [])
		self.assertEqual(_normalize_favorite_device_ids({"id": 1}), [])


class ReportEventSyncTests(TestCase):
	def test_sync_auto_enables_report_events_when_running_status_exists(self):
		device = Device.objects.create(ip_address="192.168.1.209", alias="report-auto-device")
		StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
			active=True,
		)

		_sync_report_events_for_device(device, None)

		self.assertTrue(
			DeviceEvent.objects.filter(
				device=device,
				equation_threshold=_get_report_event_marker("yesterday"),
			).exists()
		)
		self.assertTrue(
			DeviceEvent.objects.filter(
				device=device,
				equation_threshold=_get_report_event_marker("week"),
			).exists()
		)
		self.assertTrue(
			DeviceEvent.objects.filter(
				device=device,
				equation_threshold=_get_report_event_marker("month"),
			).exists()
		)

		self.assertTrue(
			Action.objects.filter(
				device_event__device=device,
				task="event.tasks.daily_energy_report",
			).exists()
		)
		self.assertTrue(
			Action.objects.filter(
				device_event__device=device,
				task="event.tasks.weekly_energy_report",
			).exists()
		)
		self.assertTrue(
			Action.objects.filter(
				device_event__device=device,
				task="event.tasks.monthly_energy_report",
			).exists()
		)

	def test_sync_creates_report_event_and_action_for_active_report_status(self):
		device = Device.objects.create(ip_address="192.168.1.210", alias="report-sync-device")
		StatusType.objects.create(
			name="WEEKLY_REPORT_STATUS",
			target_type=StatusType.STATUS_TARGET_REPORT,
			report_period="week",
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
			active=True,
		)

		_sync_report_events_for_device(device, None)

		event = DeviceEvent.objects.filter(
			device=device,
			equation_threshold=_get_report_event_marker("week"),
		).first()
		self.assertIsNotNone(event)
		self.assertEqual(event.typ.name, "Weekly Report")
		self.assertIsNotNone(event.schedule)

		action = Action.objects.filter(device_event=event, task="event.tasks.weekly_energy_report").first()
		self.assertIsNotNone(action)
		self.assertTrue(action.active)

	def test_sync_deletes_report_event_and_action_when_status_is_inactive(self):
		device = Device.objects.create(ip_address="192.168.1.211", alias="report-sync-delete")
		status_type = StatusType.objects.create(
			name="YESTERDAY_REPORT_STATUS",
			target_type=StatusType.STATUS_TARGET_REPORT,
			report_period="yesterday",
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
			active=True,
		)

		_sync_report_events_for_device(device, None)
		self.assertTrue(
			DeviceEvent.objects.filter(
				device=device,
				equation_threshold=_get_report_event_marker("yesterday"),
			).exists()
		)

		status_type.active = False
		status_type.save(update_fields=["active"])

		_sync_report_events_for_device(device, None)

		self.assertFalse(
			DeviceEvent.objects.filter(
				device=device,
				equation_threshold=_get_report_event_marker("yesterday"),
			).exists()
		)
		self.assertFalse(
			Action.objects.filter(
				device_event__device=device,
				task="event.tasks.daily_energy_report",
			).exists()
		)


class ReportTaskOverrideTests(SimpleTestCase):
	def test_daily_report_task_skips_auto_calculation_when_explicit_status_exists(self):
		action = Mock()
		action.id = "action-1"
		device_event = Mock()
		device_event.device = Mock()
		device_event.eval_equation.return_value = True
		action.device_event = device_event

		with patch('event.tasks.Action.objects.get', return_value=action), \
			 patch('event.tasks.get_report_status_type_for_period', return_value=Mock()), \
			 patch('event.tasks.calculate_report_status_for_period') as calculate_mock, \
			 patch('event.tasks.get_daily_report', return_value={'ok': True}), \
			 patch('event.tasks.EventHistory') as event_history_mock:
			daily_energy_report("action-1")

		calculate_mock.assert_not_called()
		event_history_mock.return_value.save.assert_called_once()


class ReplayStatusTests(TestCase):
	def _create_device_status_type(self, device):
		schema = [
			{
				"target": "device",
				"name": "DAILY_STATUS",
				"fields": [
					{
						"target": "load_status",
						"type": "raw",
						"source": "meter_0.power",
						"multiplier": 1,
						"offset": 0,
					}
				],
			}
		]
		return StatusType.objects.create(
			name="DAILY_STATUS",
			target_type=StatusType.STATUS_TARGET_DEVICE,
			device=device,
			update_trigger=StatusType.STATUS_UPDATE_TRIGGER_DATA,
			translation_schema=schema,
		)

	def test_replay_skips_status_raw_data_types(self):
		device = Device.objects.create(ip_address="192.168.1.70", alias="replay-skip-status")
		self._create_device_status_type(device)

		start_time = datetime(2026, 9, 9, 11, 0, tzinfo=pytz.utc)
		end_time = datetime(2026, 9, 9, 12, 0, tzinfo=pytz.utc)

		RawData.objects.create(
			device=device,
			channel="test",
			data_type="status",
			data_arrival_time=datetime(2026, 9, 9, 11, 1, tzinfo=pytz.utc),
			data={"meter_0": {"power": 111}},
		)
		RawData.objects.create(
			device=device,
			channel="test",
			data_type=" Status ",
			data_arrival_time=datetime(2026, 9, 9, 11, 2, tzinfo=pytz.utc),
			data={"meter_0": {"power": 222}},
		)
		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=datetime(2026, 9, 9, 11, 3, tzinfo=pytz.utc),
			data={"meter_0": {"power": 333}},
		)

		result = replay_stored_raw_data(
			device=device,
			start_time=start_time,
			end_time=end_time,
			user=None,
			clear_existing_statuses=True,
			replay_status_interval_minutes=10,
		)

		self.assertEqual(result["skipped_status_raw_count"], 2)
		self.assertEqual(result["replayed_raw_count"], 1)
		self.assertEqual(
			AssetStatus.objects.filter(
				device=device,
				created_at__gte=start_time,
				created_at__lt=end_time,
			).count(),
			1,
		)

	def test_replay_enforces_min_interval_and_does_not_create_per_raw(self):
		device = Device.objects.create(ip_address="192.168.1.71", alias="replay-interval-check")
		self._create_device_status_type(device)

		start_time = datetime(2026, 9, 9, 11, 0, tzinfo=pytz.utc)
		end_time = datetime(2026, 9, 9, 12, 0, tzinfo=pytz.utc)

		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=datetime(2026, 9, 9, 11, 1, tzinfo=pytz.utc),
			data={"meter_0": {"power": 100}},
		)
		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=datetime(2026, 9, 9, 11, 2, tzinfo=pytz.utc),
			data={"meter_0": {"power": 200}},
		)
		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=datetime(2026, 9, 9, 11, 3, tzinfo=pytz.utc),
			data={"meter_0": {"power": 300}},
		)

		result = replay_stored_raw_data(
			device=device,
			start_time=start_time,
			end_time=end_time,
			user=None,
			clear_existing_statuses=True,
			replay_status_interval_minutes=10,
		)

		self.assertEqual(result["replayed_raw_count"], 3)
		self.assertEqual(result["skipped_status_raw_count"], 0)
		self.assertEqual(
			AssetStatus.objects.filter(
				device=device,
				created_at__gte=start_time,
				created_at__lt=end_time,
			).count(),
			1,
		)

	def test_process_raw_data_defers_live_status_updates_while_replay_locked(self):
		device = Device.objects.create(ip_address="192.168.1.72", alias="replay-live-pause")
		self._create_device_status_type(device)

		self.assertFalse(is_device_status_replay_locked(device))
		set_device_status_replay_lock(device, enabled=True, timeout_seconds=3600)

		message_data = {
			"last_update_time": "2026-09-09T11:10:00+0000",
			"meter_0": {"power": 555},
		}
		process_raw_data(device, message_data, channel="test", data_type="raw", user=None)

		self.assertEqual(RawData.objects.filter(device=device).count(), 1)
		self.assertEqual(AssetStatus.objects.filter(device=device).count(), 0)

		set_device_status_replay_lock(device, enabled=False)

	def test_replay_releases_device_lock_after_completion(self):
		device = Device.objects.create(ip_address="192.168.1.73", alias="replay-lock-release")
		self._create_device_status_type(device)

		start_time = datetime(2026, 9, 9, 11, 0, tzinfo=pytz.utc)
		end_time = datetime(2026, 9, 9, 12, 0, tzinfo=pytz.utc)

		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=datetime(2026, 9, 9, 11, 3, tzinfo=pytz.utc),
			data={"meter_0": {"power": 333}},
		)

		self.assertFalse(is_device_status_replay_locked(device))
		replay_stored_raw_data(
			device=device,
			start_time=start_time,
			end_time=end_time,
			user=None,
			clear_existing_statuses=True,
			replay_status_interval_minutes=10,
		)
		self.assertFalse(is_device_status_replay_locked(device))

	def test_replay_runs_post_window_catchup_pass(self):
		device = Device.objects.create(ip_address="192.168.1.74", alias="replay-catchup-pass")
		self._create_device_status_type(device)

		now = timezone.now().astimezone(pytz.utc)
		start_time = now - timedelta(minutes=20)
		end_time = now - timedelta(minutes=5)

		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=start_time + timedelta(minutes=2),
			data={"meter_0": {"power": 101}},
		)
		RawData.objects.create(
			device=device,
			channel="test",
			data_type="raw",
			data_arrival_time=end_time + timedelta(minutes=1),
			data={"meter_0": {"power": 202}},
		)

		result = replay_stored_raw_data(
			device=device,
			start_time=start_time,
			end_time=end_time,
			user=None,
			clear_existing_statuses=True,
			replay_status_interval_minutes=0,
		)

		self.assertEqual(result["catchup_processed_raw_count"], 1)
		self.assertEqual(result["catchup_replayed_raw_count"], 1)
		self.assertEqual(result["replayed_raw_count"], 2)
		self.assertEqual(
			AssetStatus.objects.filter(
				device=device,
				created_at__gte=start_time,
			).count(),
			2,
		)
