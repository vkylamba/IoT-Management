from datetime import datetime
from unittest.mock import Mock

import pytz
from django.test import SimpleTestCase

from api.utils import refresh_status_processing_context_boundaries
from device_schemas.schema import (get_status_expression_helper_content,
								   translate_data_from_schema)


class SchemaTranslationTests(SimpleTestCase):
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


class StatusProcessingContextTests(SimpleTestCase):
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

	def test_status_expression_helper_content_lists_supported_sections(self):
		helper_data = get_status_expression_helper_content({
			"meter_0": {"power": 100, "powerFactor": 0.95},
			"dht": {"temperature": 25},
		})

		self.assertEqual(helper_data["summary"]["title"], "Status Expression Helper")
		self.assertTrue(any(item["value"] == "device" for item in helper_data["status_targets"]))
		self.assertTrue(any(item["value"] == "calculated" for item in helper_data["field_types"]))
		self.assertTrue(any(item["syntax"] == "lastValue__energy_generated" for item in helper_data["expression_sources"]))
		self.assertTrue(any(item["name"] == "firstToday" for item in helper_data["history_context"]))
		self.assertIn("meter_0.power", helper_data["available_raw_fields"])
		self.assertIn("dht.temperature", helper_data["available_raw_fields"])
