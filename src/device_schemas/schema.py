import json
import logging
import os
from typing import Dict

import jsonschema

logger = logging.getLogger("django")

DEVICE_SCHEMAS = {}

SCHEMA_PATH = "device_schemas/schemas/"
schema_files = os.listdir(SCHEMA_PATH)
for schema_file in schema_files:
    device_type = schema_file.replace(".json", "").upper()
    file_path = os.path.join(SCHEMA_PATH, schema_file)

    file_p = open(file_path, "r")
    DEVICE_SCHEMAS[device_type] = json.loads(file_p.read())
    file_p.close()


DATA_TRANSLATORS = {}

DATA_TRANSLATION_FILES_PATH = "device_schemas/data_translation_configurations/"
translator_files = os.listdir(DATA_TRANSLATION_FILES_PATH)
for translator_file in translator_files:
    device_type = translator_file.replace(".json", "").upper()
    file_path = os.path.join(DATA_TRANSLATION_FILES_PATH, translator_file)

    file_p = open(file_path, "r")
    DATA_TRANSLATORS[device_type] = json.loads(file_p.read())
    file_p.close()


def collect_data_paths(data, prefix="", fields=None):
    if fields is None:
        fields = set()

    if not isinstance(data, dict):
        return [] if prefix == "" else sorted(fields)

    for key, value in data.items():
        full_path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            collect_data_paths(value, full_path, fields)
        elif isinstance(value, (int, float, str, bool)) or value is None:
            fields.add(full_path)

    return sorted(fields)


def get_status_expression_helper_content(raw_data_sample=None):
    raw_field_paths = collect_data_paths(raw_data_sample or {})
    return {
        "summary": {
            "title": "Status Expression Helper",
            "description": "Translation schemas create calculated status payloads from current raw data, cached helper data, and previously stored status snapshots.",
            "expression_rules": [
                "Use space-separated expressions. Example: meter_1.power * 120 / 3600000",
                "Calculated fields can reuse earlier or later fields in the same status with .field_name.",
                "Expressions follow the token-based evaluator used by translate_data_from_schema.",
            ],
        },
        "status_targets": [
            {
                "value": "device",
                "label": "Device",
                "description": "Stores device-wide derived values such as power, energy, state, or weather-linked status.",
            },
            {
                "value": "user",
                "label": "User",
                "description": "Stores user-level summary values derived from the device stream.",
            },
            {
                "value": "meter",
                "label": "Meter",
                "description": "Stores meter-specific derived output when the status represents a meter target.",
            },
            {
                "value": "alarm",
                "label": "Alarm",
                "description": "Stores alarm-specific evaluation output and trigger state.",
            },
            {
                "value": "report",
                "label": "Report",
                "description": "Stores report-style aggregate status values.",
            },
        ],
        "field_types": [
            {
                "value": "raw",
                "description": "Reads a field directly from the current raw payload.",
                "example": {
                    "target": "load_status",
                    "type": "raw",
                    "source": "meter_1.power",
                    "multiplier": 1,
                    "offset": 0,
                },
            },
            {
                "value": "calculated",
                "description": "Evaluates an expression using raw fields, sibling fields, and history helpers.",
                "example": {
                    "target": "energy_consumed",
                    "type": "calculated",
                    "source": "lastValue__energy_consumed + meter_1.power * 120 / 3600000",
                    "multiplier": 1,
                    "offset": 0,
                },
            },
            {
                "value": "dataCache",
                "description": "Reads helper data injected outside the raw payload, such as weather.",
                "example": {
                    "target": "weather",
                    "type": "dataCache",
                    "source": "weather",
                    "multiplier": 1,
                    "offset": 0,
                },
            },
        ],
        "expression_sources": [
            {
                "name": "Current raw field",
                "syntax": "meter_1.power",
                "description": "Reads from the raw payload currently being processed.",
                "example": "meter_2.power - meter_1.power",
            },
            {
                "name": "Current sibling field",
                "syntax": ".energy_consumed",
                "description": "Reuses another field from the same status payload. If needed, the field is resolved on demand.",
                "example": ".energy_consumed + meter_0.power * 120 / 3600000",
            },
            {
                "name": "Last value helper",
                "syntax": "lastValue__energy_generated",
                "description": "Reads the latest stored value from the last status snapshot for the same target, then falls back to last raw data when available.",
                "example": "lastValue__energy_generated + meter_2.power * 120 / 3600000",
            },
            {
                "name": "Daily delta helper",
                "syntax": "changeToday__energy_consumed",
                "description": "Uses the current value minus the first value from today. Current value can come from raw data or a sibling field; first value comes from the firstToday snapshot.",
                "example": "changeToday__energy_revenue",
            },
            {
                "name": "Data cache helper",
                "syntax": "type=dataCache, source=weather",
                "description": "Reads enriched helper data passed in separately from the raw payload.",
                "example": "weather",
            },
        ],
        "supported_operators": [
            {"operator": "+", "description": "Addition"},
            {"operator": "-", "description": "Subtraction or negative literals such as -1"},
            {"operator": "*", "description": "Multiplication"},
            {"operator": "/", "description": "Division"},
            {"operator": ">, <, >=, <=, ==, !=", "description": "Comparisons"},
            {"operator": "and, or", "description": "Boolean combinations"},
            {"operator": "if ... else ...", "description": "Inline conditional expressions"},
            {"operator": "quoted strings", "description": "String literals such as \"Exporting\""},
        ],
        "history_context": [
            {
                "name": "firstToday",
                "description": "The first status/raw snapshot for the selected device-local day. Used internally by changeToday__ helpers and shown in preview debug context.",
            },
            {
                "name": "lastToday",
                "description": "The latest status/raw snapshot available before the current calculation. Used internally by lastValue__ helpers and preview debug context.",
            },
        ],
        "notes": [
            "If you want cumulative values across updates or replay, use lastValue__field_name instead of .field_name.",
            "Use .field_name when you want to build one field from another field inside the same status payload.",
            "changeToday__field_name is safest when the base field is also defined in the same status or already stored in previous snapshots.",
            "dataCache fields are not expression operators; they are field definitions that read from helper data such as weather.",
        ],
        "available_raw_fields": raw_field_paths,
        "raw_data_sample": raw_data_sample or {},
    }


def validate_data_schema(device_type: str, data: Dict, existing_statuses: Dict, data_cache: Dict = None) -> Dict:

    schema = DEVICE_SCHEMAS.get(device_type)
    translated_data = None
    if schema is not None:
        logger.debug(f"Schema for device {device_type} is {schema}")
        if not validate_schema(schema, data):
            logger.warning(
                f"Error validating schema for device type {device_type}, data: {data}"
            )
            return None

        try:
            translated_data = translate_data(device_type, data, existing_statuses, data_cache)
        except Exception as ex:
            logger.warning(
                f"Error translating data for device type {device_type}, data: {data}",
                ex,
            )
            return None
    else:
        logger.warning(f"No schema file found for schema {device_type}")

    return translated_data


def validate_schema(schema: Dict, data: Dict):
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as ex:
        return False

    return True


def translate_data(device_type: str, data: Dict, existing_statuses: Dict, data_cache: Dict = None) -> Dict:
    translator = DATA_TRANSLATORS.get(device_type)
    translated_data = {}
    if isinstance(translator, list):
        logger.debug(f"Translation schema for device {device_type} is {translator}")
        translated_data = translate_data_from_schema(
            translator, data, existing_statuses, data_cache
        )
    else:
        logger.warning(f"No translation schema file found for schema {device_type}")

    return translated_data


def translate_data_from_schema(
    translator: any,
    data: Dict,
    existing_statuses: Dict = None,
    data_cache: Dict = None,
    include_debug: bool = False,
):
    translated_data = {}
    field_details = []

    first_today = (existing_statuses or {}).get("firstToday", {}) or {}
    last_today = (existing_statuses or {}).get("lastToday", {}) or {}
    if isinstance(translator, dict):
        translator = [translator]
    for translator_config in translator:
        schema_target = translator_config.get("target")
        target_name = translator_config.get("name")
        frequency = translator_config.get("frequency")
        target_fields = translator_config.get("fields", [])
        required_fields = translator_config.get("required_fields", [])
        least_one_field_list = translator_config.get("least_one_field_list", [])
        required_fields_check = len(required_fields) > 0 or len(least_one_field_list) > 0
        data_fields = {}
        resolved_field_details = {}
        data_valid = True
        all_required_fields_exist = len(required_fields) > 0
        at_least_one_required_field_exist = False
        if isinstance(target_fields, list):
            target_field_configs = {
                target_field.get("target"): target_field
                for target_field in target_fields
                if isinstance(target_field, dict) and target_field.get("target")
            }
            resolving_fields = set()

            def resolve_target_field(target_field_name):
                if target_field_name in data_fields:
                    return data_fields.get(target_field_name)

                target_field = target_field_configs.get(target_field_name)
                if target_field is None or target_field_name in resolving_fields:
                    return None

                resolving_fields.add(target_field_name)
                try:
                    translated_field = translate_field_value(
                        schema_target,
                        target_name,
                        target_field,
                        data,
                        existing_statuses,
                        data_cache,
                        current_target_fields=data_fields,
                        target_field_configs=target_field_configs,
                        field_resolver=resolve_target_field,
                        include_debug=include_debug,
                    )
                    if include_debug:
                        field_value = translated_field.get("value")
                        data_fields[target_field_name] = field_value
                        resolved_field_details[target_field_name] = {
                            "status_name": target_name,
                            "status_target": schema_target,
                            "key": target_field_name,
                            "input": translated_field.get("input", {}),
                            "output": field_value,
                        }
                    else:
                        data_fields[target_field_name] = translated_field
                    return data_fields.get(target_field_name)
                finally:
                    resolving_fields.discard(target_field_name)

            for target_field in target_fields:
                resolve_target_field(target_field.get("target"))

            if include_debug:
                for target_field in target_fields:
                    target_field_name = target_field.get("target")
                    field_detail = resolved_field_details.get(target_field_name)
                    if field_detail is not None:
                        field_details.append(field_detail)
        if isinstance(least_one_field_list, list):
            for required_field in least_one_field_list:
                if data_fields.get(required_field) is not None:
                    at_least_one_required_field_exist = True

        if isinstance(required_fields, list):
            for required_field in required_fields:
                if data_fields.get(required_field) is None:
                    logger.warning(
                        f"Required data field {required_field} missing in the data."
                    )
                    all_required_fields_exist = False

        data_valid = (all_required_fields_exist or at_least_one_required_field_exist) if required_fields_check else True
        logger.debug(f"data_valid: {data_valid}, all_required_fields_exist: {all_required_fields_exist}, at_least_one_required_field_exist: {at_least_one_required_field_exist}")
        if data_valid:
            translated_data[target_name] = data_fields
    if include_debug:
        return {
            "translated_data": translated_data,
            "field_details": field_details,
            "debug_context": {
                "first_raw": first_today.get("raw", {}),
                "last_raw": last_today.get("raw", {}),
                "first_statuses": {
                    key: value for key, value in first_today.items() if key != "raw"
                },
                "last_statuses": {
                    key: value for key, value in last_today.items() if key != "raw"
                },
            },
        }
    return translated_data


def translate_field_value(
    schema_target: str,
    target_name: str,
    field_config: Dict,
    data: Dict,
    existing_statuses: Dict = None,
    data_cache: Dict = None,
    current_target_fields: Dict = None,
    target_field_configs: Dict = None,
    field_resolver=None,
    include_debug: bool = False,
):

    target_field_name = field_config.get("target")
    type = field_config.get("type")
    source_match_key = field_config.get("sourceMatchKey")
    source_match_key_value = field_config.get("sourceMatchKeyValue")
    source = field_config.get("source")
    multiplier = field_config.get("multiplier", 1)
    offset = field_config.get("offset", 0)

    value = None
    input_detail = {
        "type": type,
        "source": source,
        "multiplier": multiplier,
        "offset": offset,
    }
    should_pick = False
    if source_match_key is None or source_match_key_value is None:
        should_pick = True
    else:
        source_match_key_current_value = extract_data(source_match_key, data, multiplier, offset)
        should_pick = source_match_key_current_value == source_match_key_value
        if include_debug:
            input_detail["source_match"] = {
                "key": source_match_key,
                "expected": source_match_key_value,
                "actual": source_match_key_current_value,
                "matched": should_pick,
            }

    if should_pick:
        logger.info(
            f"Extracting value for source. source: {source} type: {type} multiplier: {multiplier} offset: {offset}"
        )
        if type == "raw":
            value = extract_data(source, data, multiplier, offset)
            if include_debug:
                input_detail["resolved_input"] = extract_data(source, data, 1, 0)
        elif type == "calculated":
            calculated_output = extract_calculated_data(
                schema_target,
                target_name,
                target_field_name,
                source,
                data,
                multiplier,
                offset,
                existing_statuses,
                current_target_fields=current_target_fields,
                target_field_configs=target_field_configs,
                field_resolver=field_resolver,
                include_debug=include_debug,
            )
            if include_debug:
                value = calculated_output.get("value")
                input_detail["calculation"] = calculated_output.get("detail", {})
            else:
                value = calculated_output
        elif type == "dataCache":
            value = (data_cache or {}).get(source)
            if include_debug:
                input_detail["resolved_input"] = value
        logger.info(f"Extracted value for source {source} is: {value}")

    if include_debug:
        input_detail["picked"] = should_pick
        return {
            "value": value,
            "input": input_detail,
        }

    return value


def extract_data(field_name: str, data: Dict, multiplier, offset):
    fields_list = field_name.split(".")
    if field_name == "":
        return 0
    current_dict = data
    for this_field_name in fields_list:
        if isinstance(current_dict, dict) and len(this_field_name) > 0:
            current_dict = current_dict.get(this_field_name)

    if isinstance(current_dict, float) or isinstance(current_dict, int):
        value = current_dict * multiplier + offset
        return value

    return current_dict


def extract_calculated_data(
    schema_target: str,
    target_name: str,
    target_field_name: str,
    field_name: str,
    data: Dict,
    multiplier, offset,
    existing_statuses: Dict = None,
    current_target_fields: Dict = None,
    target_field_configs: Dict = None,
    field_resolver=None,
    include_debug: bool = False,
):
    def _normalize_snapshot(value):
        if isinstance(value, dict):
            return value
        return {}

    def _resolve_status_scope(status_snapshot, status_name):
        status_snapshot = _normalize_snapshot(status_snapshot)
        nested_status = status_snapshot.get(status_name)
        if isinstance(nested_status, dict):
            return nested_status
        return status_snapshot

    def _as_number(value):
        return value if isinstance(value, (int, float)) else 0

    original_expression = field_name
    fields_and_operators = field_name.split()
    equation = ""
    resolved_tokens = []
    if existing_statuses is None:
        existing_statuses = {}
    first_today = _normalize_snapshot(existing_statuses.get("firstToday", {}))
    last_today = _normalize_snapshot(existing_statuses.get("lastToday", {}))
    last_status_root = _normalize_snapshot(last_today.get(schema_target, {}))
    first_status_root = _normalize_snapshot(first_today.get(schema_target, {}))
    last_status_data = _resolve_status_scope(last_status_root, target_name)
    first_status_data = _resolve_status_scope(first_status_root, target_name)
    first_raw_data = _normalize_snapshot(first_today.get("raw", {}))
    last_raw_data = _normalize_snapshot(last_today.get("raw", {}))
    current_target_fields = _normalize_snapshot(current_target_fields)
    for field_or_operator in fields_and_operators:
        operator = None
        field_name = None
        value_already_fetched = False
        next_value = None
        if field_or_operator.startswith("lastValue__"):
            field_name = field_or_operator.replace("lastValue__", "")
            value_source = "last_status_scope"
            next_value = extract_data(field_name, last_status_data, 1, 0)
            if next_value is None:
                value_source = "last_status_root"
                next_value = extract_data(field_name, last_status_root, 1, 0)
            if next_value is None:
                value_source = "last_raw"
                next_value = extract_data(field_name, last_raw_data, 1, 0)
            value_already_fetched = True
            if next_value is None:
                next_value = 0
                value_source = "default_zero"
            if include_debug:
                resolved_tokens.append({
                    "token": field_or_operator,
                    "kind": "lastValue",
                    "field": field_name,
                    "value": next_value,
                    "source": value_source,
                })
        elif field_or_operator.startswith("changeToday__"):
            field_name = field_or_operator.replace("changeToday__", "")
            value_now_source = "current_raw"
            value_now = extract_data(field_name, data, multiplier, offset)
            if value_now is None:
                value_now = extract_data(field_name, current_target_fields, multiplier, offset)
                value_now_source = "current_status_fields"
            if (
                value_now is None
                and callable(field_resolver)
                and field_name != target_field_name
                and field_name in (target_field_configs or {})
            ):
                field_resolver(field_name)
                value_now = extract_data(field_name, current_target_fields, multiplier, offset)
                value_now_source = "current_status_fields"
            value_first = extract_data(field_name, first_raw_data, 1, 0)
            value_first_source = "first_raw"
            if value_first is None:
                value_first_source = "first_status_scope"
                value_first = extract_data(field_name, first_status_data, 1, 0)
            if value_first is None:
                value_first_source = "first_status_root"
                value_first = extract_data(field_name, first_status_root, 1, 0)
            value_already_fetched = True
            try:
                next_value = _as_number(value_now) - _as_number(value_first)
            except Exception as ex:
                logger.warning(ex)
                next_value = value_now
            if include_debug:
                resolved_tokens.append({
                    "token": field_or_operator,
                    "kind": "changeToday",
                    "field": field_name,
                    "value_now": value_now,
                    "value_first": value_first,
                    "value": next_value,
                    "value_now_source": value_now_source,
                    "value_first_source": value_first_source,
                })
        elif "." in field_or_operator:
            field_name = field_or_operator
        else:
            operator = field_or_operator

        if field_name is not None and not value_already_fetched:
            field_source = "current_raw"
            if field_name.startswith("."):
                current_field_name = field_name[1:]
                next_value = extract_data(current_field_name, current_target_fields, multiplier, offset)
                field_source = "current_status_fields"
                if (
                    next_value is None
                    and callable(field_resolver)
                    and current_field_name != target_field_name
                    and current_field_name in (target_field_configs or {})
                ):
                    field_resolver(current_field_name)
                    next_value = extract_data(current_field_name, current_target_fields, multiplier, offset)
                    field_source = "current_status_fields"
                if next_value is None:
                    next_value = extract_data(field_name, data, multiplier, offset)
                    field_source = "current_raw"
            else:
                next_value = extract_data(field_name, data, multiplier, offset)
            value_already_fetched = True
            if include_debug:
                resolved_tokens.append({
                    "token": field_or_operator,
                    "kind": "rawField",
                    "field": field_name,
                    "value": next_value,
                    "source": field_source,
                })

        if value_already_fetched:
            if next_value is None:
                next_value = 0
            equation += f"{next_value}"

        elif operator is not None:
            equation += " " + operator + " "
            if include_debug:
                resolved_tokens.append({
                    "token": field_or_operator,
                    "kind": "operator",
                })

    value = None
    try:
        value = eval(equation)
    except Exception as ex:
        logger.warning(
            f"Error evaluating equation {equation} for field {field_name}. Exception: {ex}"
        )
    if include_debug:
        return {
            "value": value,
            "detail": {
                "expression": original_expression,
                "resolved_expression": equation,
                "resolved_tokens": resolved_tokens,
                "current_status_fields": current_target_fields,
                "first_status_scope": first_status_data,
                "last_status_scope": last_status_data,
            },
        }
    return value


if __name__ == "__main__":

    schemas = ", ".join(DEVICE_SCHEMAS.keys())
    print(f"Available Schemas: {schemas}")

    target_schema = "IOT-GW-SHAKTI-SOLAR-PUMP"
    test_data = json.loads(
        """
        {
            "total_time": 1418,
            "total_energy_kwh": 8342,
            "max_power": 9600,
            "vfd_master_switch_state": 1,
            "total_flow": 1252
        }
    """
    )
    validated_data = validate_data_schema(target_schema, test_data, None)
    print(f"{target_schema}: {validated_data}")
    validated_data = validate_data_schema(target_schema, test_data, test_data)
    print(f"{target_schema}: {validated_data}")

    target_schema = "IOT-GW-V2-MODBUS-WIFI"
    test_data = json.loads(
        """
        {
            "adc": { "1": 1782, "2": 1668, "3": 2037, "4": 2037, "5": 2037, "6": 2037 },
            "dht": {
                "state": 3,
                "humidity": 66.0,
                "temperature": 22.700001,
                "hic": 22.748661
            }
        }
    """
    )
    validated_data = validate_data_schema(target_schema, test_data, None)
    print(f"{target_schema}: {validated_data}")
    validated_data = validate_data_schema(target_schema, test_data, test_data)
    print(f"{target_schema}: {validated_data}")

    schema = [
        {
            "target": "DAILY_STATUS",
            "name": "DAILY_STATUS",
            "required_fields": [],
            "least_one_field_list": ["energy", "uptime"],
            "fields": [
                {
                    "target": "energy",
                    "type": "calculated",
                    "source": "meter_0.energy or lastValue__.energy",
                    "multiplier": 2.78e-7,
                    "offset": 0,
                },
                {
                    "target": "energy_consumed_this_day",
                    "type": "calculated",
                    "source": "changeToday__meter_0.energy or lastValue__.energy_consumed_this_day",
                    "multiplier": 2.78e-7,
                    "offset": 0,
                },
                {
                    "target": "load_status",
                    "type": "calculated",
                    "source": "meter_0.power or lastValue__.power",
                    "multiplier": 1,
                    "offset": 0,
                },
                {
                    "target": "uptime",
                    "type": "calculated",
                    "source": ".uptime or lastValue__.uptime",
                    "multiplier": 1,
                    "offset": 0,
                },
                {
                    "target": "system_temperature",
                    "type": "calculated",
                    "source": "dht.temperature or lastValue__.system_temperature",
                    "multiplier": 1,
                    "offset": 0,
                },
                {
                    "target": "system_humidity",
                    "type": "calculated",
                    "source": "dht.humidity or lastValue__.system_humidity",
                    "multiplier": 1,
                    "offset": 0,
                },
            ],
        }
    ]

    test_data = json.loads("""
        {
            "adc": {
                "0": 0,
                "1": 0,
                "2": 194,
                "3": 606,
                "4": 1045,
                "5": 780
            },
            "dht": {
                "hic": 11553.5,
                "humidity": 200,
                "state": 2,
                "temperature": 200
            },
            "meter_0": {
                "current": 10,
                "energy": 2398662.75,
                "frequency": 0,
                "power": 100,
                "powerFactor": 1,
                "typCfg": "WAC[0,1]",
                "voltage": 10
            },
            "meter_1": {
                "ampSecs": 510200.97,
                "current": 19.4,
                "frequency": 48,
                "typCfg": "AAC[2]"
            },
            "meter_2": {
                "ampSecs": -123889147696906240,
                "current": 60.6,
                "frequency": 44,
                "typCfg": "AAC[3]"
            },
            "meter_3": {
                "ampSecs": 10033661528990810000,
                "current": 104.5,
                "frequency": 41,
                "typCfg": "AAC[4]"
            },
            "timeDelta": 649,
            "timeUTC": "2024-02-22 14:06:30"
        }
    """)
    
    statuses = json.loads("""
        {
            "firstToday": {
                "DAILY_STATUS": {    
                    "energy": 101,
                    "energy_consumed_this_day": 101,
                    "load_status": 101,
                    "uptime": 101,
                    "system_temperature": 101,
                    "system_humidity": 101
                }
            },
            "lastToday": {
                "DAILY_STATUS": {    
                    "energy": 110,
                    "energy_consumed_this_day": 110,
                    "load_status": 110,
                    "uptime": 110,
                    "system_temperature": 110,
                    "system_humidity": 110
                }
            }
        }
    """)

    validated_data = translate_data_from_schema(schema, test_data)
    print(f"validated data: {validated_data}")
    
    test_data = json.loads("""
        {
            "battery": 0,
            "core_version": "6.0.1",
            "fw_version": "1.1.5",
            "mac": 268600848269144,
            "uptime": 446
        }
    """)
    validated_data = translate_data_from_schema(schema, test_data, statuses)
    print(f"validated data: {validated_data}")
