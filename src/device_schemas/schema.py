import json
import logging
import os
from typing import Dict

import jsonschema

logger = logging.getLogger('django')

DEVICE_SCHEMAS = {}

SCHEMA_PATH = "device_schemas/schemas/"
schema_files = os.listdir(SCHEMA_PATH)
for schema_file in schema_files:
    device_type = schema_file.replace('.json', '').upper()
    file_path = os.path.join(SCHEMA_PATH, schema_file)

    file_p = open(file_path, "r")
    DEVICE_SCHEMAS[device_type] = json.loads(file_p.read())
    file_p.close()


DATA_TRANSLATORS = {}

DATA_TRANSLATION_FILES_PATH = "device_schemas/data_translation_configurations/"
translator_files = os.listdir(DATA_TRANSLATION_FILES_PATH)
for translator_file in translator_files:
    device_type = translator_file.replace('.json', '').upper()
    file_path = os.path.join(DATA_TRANSLATION_FILES_PATH, translator_file)

    file_p = open(file_path, "r")
    DATA_TRANSLATORS[device_type] = json.loads(file_p.read())
    file_p.close()


def validate_data_schema(device_type: str, data: Dict, last_raw_data: Dict) -> Dict:

    schema = DEVICE_SCHEMAS.get(device_type)
    translated_data = None
    if schema is not None:
        logger.debug(f"Schema for device {device_type} is {schema}")
        if not validate_schema(schema, data):
            logger.warning(f"Error validating schema for device type {device_type}, data: {data}")
            return None

        try:
            translated_data = translate_data(device_type, data, last_raw_data)
        except Exception as ex:
            logger.warning(f"Error translating data for device type {device_type}, data: {data}", ex)
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


def translate_data(device_type: str, data: Dict, last_raw_data: Dict) -> Dict:
    translator = DATA_TRANSLATORS.get(device_type)
    translated_data = {}
    if isinstance(translator, list):
        logger.debug(f"Translation schema for device {device_type} is {translator}")
        translated_data = translate_data_from_schema(translator, data, last_raw_data)
    else:
        logger.warning(f"No translation schema file found for schema {device_type}")
    
    return translated_data


def translate_data_from_schema(translator: any, data: Dict, last_status_data: Dict, first_status_today_data: Dict = None):
    translated_data = {}
    if isinstance(translator, dict):
        translator = [translator]
    for translator_config in translator:
        target = translator_config.get("target")
        target_name = translator_config.get("name")
        target_type = translator_config.get("type")
        target_fields = translator_config.get("fields", [])
        required_fields = translator_config.get("required_fields", [])
        data_fields = {}
        data_valid = True
        if isinstance(last_status_data, Dict) and target in last_status_data:
            last_status_data = last_status_data.get(target)
        if isinstance(first_status_today_data, Dict) and target in first_status_today_data:
            first_status_today_data = first_status_today_data.get(target)
        if isinstance(target_fields, list):
            for target_field in target_fields:
                target_field_name = target_field.get("target")
                data_fields[target_field_name] = translate_field_value(target_field, data, last_status_data, first_status_today_data)
        if isinstance(required_fields, list):
            for required_field in required_fields:
                if data_fields.get(required_field) is None:
                    logger.warning(f"Required data field {required_field} missing in the data.")
                    data_valid = False
        if data_valid:
            translated_data[target_name] = data_fields
    return translated_data


def translate_field_value(field_config: Dict, data: Dict, last_status_data: Dict, first_status_today_data: Dict = None):

    target = field_config.get("target")
    type = field_config.get("type")
    source_match_key = field_config.get("sourceMatchKey")
    source_match_key_value = field_config.get("sourceMatchKeyValue")
    source = field_config.get("source")
    multiplier = field_config.get("multiplier", 1)
    offset = field_config.get("offset", 0)

    value = None
    should_pick = False
    if source_match_key is None or source_match_key_value is None:
        should_pick = True
    else:
        source_match_key_current_value = extract_data(source_match_key, data)
        should_pick = source_match_key_current_value == source_match_key_value

    if should_pick:
        logger.info(f"Extracting value for source. source: {source} type: {type} multiplier: {multiplier} offset: {offset}")
        if type == "raw":
            raw_val = extract_data(source, data)
            if raw_val is not None:
                value = raw_val * multiplier + offset
        elif type == "calculated":
            raw_val = extract_calculated_data(target, source, data, last_status_data, first_status_today_data)
            if raw_val is not None:
                value = float(raw_val) * multiplier + offset
        logger.info(f"Extracted value for source {source} is: {value}")

    return value


def extract_data(field_name: str, data: Dict):
    fields_list = field_name.split('.')
    if field_name == "":
        return 0
    current_dict = data
    for this_field_name in fields_list:
        if isinstance(current_dict, dict):
            current_dict = current_dict.get(this_field_name)

    return current_dict


def extract_calculated_data(target: str, field_name: str, data: Dict, last_status_data: Dict, first_status_today_data: Dict = None):
    fields_and_operators = field_name.split()
    equation = ''
    for field_or_operator in fields_and_operators:
        operator = None
        field_name = None
        value_already_fetched = False
        if field_or_operator.startswith('lastValue__'):
            field_name = field_or_operator.replace('lastValue__', '')
            next_value = extract_data(field_name, last_status_data)
            value_already_fetched = True
            if next_value is None:
                next_value = 0
        elif field_or_operator.startswith('changeToday__'):
            field_name = field_or_operator.replace('changeToday__', '')
            value_now = extract_data(field_name, data)
            value_first = extract_data(field_name, first_status_today_data)
            value_already_fetched = True
            next_value = None
            try:
                next_value = value_now - value_first
            except Exception as ex:
                logger.warning(ex)
                next_value = value_now
        elif '.' in field_or_operator:
            field_name = field_or_operator
        else:
            operator = field_or_operator

        if field_name is not None and not value_already_fetched:
            next_value = extract_data(field_name, data)
            value_already_fetched = True

        if value_already_fetched and next_value is not None:
            equation += f"{next_value}"

        elif operator is not None:
            equation += ' ' + operator + ' '

    value = None
    try:
        value = eval(equation)
    except Exception as ex:
        logger.warning(f"Error evaluating equation {equation} for field {field_name}. Exception: {ex}")
    return value


if __name__ == "__main__":
    print("hello")
    schemas = ', '.join(DEVICE_SCHEMAS.keys())
    print(f"Available Schemas: {schemas}")

    target_schema = 'IOT-GW-SHAKTI-SOLAR-PUMP'
    test_data = json.loads("""
        {
            "total_time": 1418,
            "total_energy_kwh": 8342,
            "max_power": 9600,
            "vfd_master_switch_state": 1,
            "total_flow": 1252
        }
    """)
    validated_data = validate_data_schema(target_schema, test_data, None)
    print(f"{target_schema}: {validated_data}")
    validated_data = validate_data_schema(target_schema, test_data, test_data)
    print(f"{target_schema}: {validated_data}")

    target_schema = 'IOT-GW-V2-MODBUS-WIFI'
    test_data = json.loads("""
        {
            "adc": { "1": 1782, "2": 1668, "3": 2037, "4": 2037, "5": 2037, "6": 2037 },
            "dht": {
                "state": 3,
                "humidity": 66.0,
                "temperature": 22.700001,
                "hic": 22.748661
            }
        }
    """)
    validated_data = validate_data_schema(target_schema, test_data, None)
    print(f"{target_schema}: {validated_data}")
    validated_data = validate_data_schema(target_schema, test_data, test_data)
    print(f"{target_schema}: {validated_data}")
