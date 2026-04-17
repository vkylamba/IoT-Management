from django.test import SimpleTestCase

from device_schemas.schema import translate_data_from_schema


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
