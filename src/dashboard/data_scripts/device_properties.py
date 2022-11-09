from .property_updaters import (
    update_currency,
    update_monthly_bill,
    update_pay_per_unit,
    update_cost_savings,
    update_energy_generated_this_month,
    update_energy_consumed_this_month,
    update_energy_exported_this_month,
    update_energy_imported_this_month,
    update_energy_generated_this_day,
    update_energy_consumed_this_day,
    update_energy_exported_this_day,
    update_energy_imported_this_day,
    update_battery_charging_status,
    update_net_meter_status,
    update_solar_status,
    update_load_status,
    update_system_status
)


DEV_PROPERTIES = {
    "Home": [
        {
            "name": "currency",
            "type": "String",
            "value": "$",
            "update": True,
            "update_method": update_currency
        },
        {
            "name": "pay_per_unit",
            "type": "Float",
            "value": "5.0",
            "update": True,
            "update_method": update_pay_per_unit
        },
        {
            "name": "monthly_bill_amount",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_monthly_bill
        },
        {
            "name": "monthly_bill_limit",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_month
        },
        {
            "name": "energy_consumed_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_day
        },
        {
            "name": "energy_consumption_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumption_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "load_status",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_load_status
        },
    ],
    "DELTA-RPI Inverter": [
        {
            "name": "currency",
            "type": "String",
            "value": "$",
            "update": True,
            "update_method": update_currency
        },
        {
            "name": "pay_per_unit",
            "type": "Float",
            "value": "5.0",
            "update": True,
            "update_method": update_pay_per_unit
        },
        {
            "name": "cost_savings_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_cost_savings
        },
        {
            "name": "cost_savings_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_month
        },
        {
            "name": "energy_generation_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_day
        },
        {
            "name": "energy_generation_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_month
        },
        {
            "name": "energy_consumption_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_day
        },
        {
            "name": "energy_consumption_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        }
    ],
     "Charge Controller": [
        {
            "name": "currency",
            "type": "String",
            "value": "₹",
            "update": True,
            "update_method": update_currency
        },
        {
            "name": "pay_per_unit",
            "type": "Float",
            "value": "5.0",
            "update": True,
            "update_method": update_pay_per_unit
        },
        {
            "name": "cost_savings_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_cost_savings
        },
        {
            "name": "cost_savings_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_month
        },
        {
            "name": "energy_generation_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_day
        },
        {
            "name": "energy_generation_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_month
        },
        {
            "name": "energy_consumption_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_exported_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_exported_this_month
        },
        {
            "name": "energy_export_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_day
        },
        {
            "name": "energy_consumption_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_exported_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_exported_this_day
        },
        {
            "name": "energy_export_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        }
    ],
    "SOLAR HYBRID INVERTER": [
        {
            "name": "currency",
            "type": "String",
            "value": "₹",
            "update": True,
            "update_method": update_currency
        },
        {
            "name": "pay_per_unit",
            "type": "Float",
            "value": "5.0",
            "update": True,
            "update_method": update_pay_per_unit
        },
        {
            "name": "monthly_bill_amount",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_monthly_bill
        },
        {
            "name": "total_investment",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "total_recovery_amount",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "cost_savings_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_cost_savings
        },
        {
            "name": "total_cost_savings",
            "type": "Float",
            "value": "0.0",
            "update": False,
        },
        {
            "name": "cost_savings_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_month
        },
        {
            "name": "energy_generation_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_generated_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_generated_this_day
        },
        {
            "name": "energy_generation_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_month
        },
        {
            "name": "energy_consumption_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_exported_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_exported_this_month
        },
        {
            "name": "energy_export_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_imported_this_month",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_imported_this_month
        },
        {
            "name": "energy_import_limit_this_month",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_consumed_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_consumed_this_day
        },
        {
            "name": "energy_consumption_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_exported_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_exported_this_day
        },
        {
            "name": "energy_export_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "energy_imported_this_day",
            "type": "Float",
            "value": "0.0",
            "update": True,
            "update_method": update_energy_imported_this_day
        },
        {
            "name": "energy_import_limit_this_day",
            "type": "Float",
            "value": "0.0",
            "update": False
        },
        {
            "name": "battery_charging_status",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_battery_charging_status
        },
        {
            "name": "net_meter_status",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_net_meter_status
        },
        {
            "name": "solar_status",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_solar_status
        },
        {
            "name": "load_status",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_load_status
        },
        {
            "name": "system_state",
            "type": "String",
            "value": "",
            "update": True,
            "update_method": update_system_status
        }
    ]
}
