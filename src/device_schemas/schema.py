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
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as ex:
            logger.error(f"Error validating schema for device type {device_type}, data: {data}", ex)
            return None

        try:
            translated_data = translate_data(device_type, data, last_raw_data)
        except Exception as ex:
            logger.error(f"Error translating data for device type {device_type}, data: {data}", ex)
            return None
    else:
        logger.error(f"No schema file found for schema {device_type}")

    return translated_data


def translate_data(device_type: str, data: Dict, last_raw_data: Dict) -> Dict:
    translator = DATA_TRANSLATORS.get(device_type)
    translated_data = {}
    if isinstance(translator, list):
        for translator_config in translator:
            target = translator_config.get("target")
            target_name = translator_config.get("name")
            target_type = translator_config.get("type")
            target_fields = translator_config.get("fields", [])
            data_fields = {}
            if target == "meter":
                if isinstance(target_fields, list):
                    for target_field in target_fields:
                        target_field_name = target_field.get("target")
                        data_fields[target_field_name] = translate_field_value(target_field, data, last_raw_data)

            translated_data[target_name] = data_fields
    else:
        logger.error(f"No translation schema file found for schema {device_type}")
    
    return translated_data


def translate_field_value(field_config: Dict, data: Dict, last_raw_data: Dict):

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
        logger.info(f"Extracting value for source: {source} {type} {multiplier} {offset}")
        if type == "raw":
            raw_val = extract_data(source, data)
            if raw_val is not None:
                value = raw_val * multiplier + offset
        elif type == "calculated":
            raw_val = extract_calculated_data(source, data, last_raw_data)
            if raw_val is not None:
                value = float(raw_val) * multiplier + offset

    return value


def extract_data(field_name: str, data: Dict):
    fields_list = field_name.split('.')
    current_dict = data
    for this_field_name in fields_list:
        if isinstance(current_dict, dict):
            current_dict = current_dict.get(this_field_name)

    return current_dict


def extract_calculated_data(field_name: str, data: Dict, last_raw_data: Dict):
    fields_and_operators = field_name.split()
    equation = ''
    print(fields_and_operators)
    for field_or_operator in fields_and_operators:
        operator = None
        field_name = None
        if field_or_operator.startswith('lastValue__'):
            field_name = field_or_operator.replace('lastValue__', '')
            next_value = extract_data(field_name, last_raw_data)
            if next_value is None:
                next_value = 0
        elif '.' in field_or_operator:
            field_name = field_or_operator
        else:
            operator = field_or_operator
        
        if field_name is not None:
            next_value = extract_data(field_name, data)

            if next_value is not None:
                equation += f"{next_value}"

        elif operator is not None:
            equation += ' ' + operator + ' '

    value = None
    try:
        value = eval(equation)
    except Exception as ex:
        logger.error(f"Error evaluating equation {equation} for field {field_name}. Exception: {ex}")
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
