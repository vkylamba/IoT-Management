
SYSTEM_VARIABLES = {
    "GRID",
    "WEATHER",
    "GENERATION",
    "LOAD",
    "DAYHOUR"
}

GRID_STATES = [
    "ABSENT",
    "PRESENT",
    "IMPORTING",
    "EXPORTING"
]

WEATHER_STATES = [
    "SUNNY",
    "CLOUDY",
    "RAINY"
]

GENERATION_STATES = [
    "HIGH",
    "MEDIUM",
    "LOW",
    "ZERO"
]

LOAD_STATES = [
    "HIGH",
    "MEDIUM",
    "LOW",
    "ZERO"
]

DAYTIME = [
    "NIGHT",
    "MORNING",
    "NOON",
    "EVENING"
]

SYSTEM_STATES = {
    # (DAYTIME, GRID_STATE, WEATHER_STATE, GENERATION_STATE, LOAD_STATE)
    ("NIGHT", "ABSENT"): "NA",
    ("NIGHT", "PRESENT"): "NA",
    ("MORNING", "ABSENT"): "NA",
    ("MORNING", "PRESENT"): "NA",
    ("NOON", "ABSENT", "RAINY"): "NA",
    ("NOON", "ABSENT", "CLOUDY"): "NA",
    ("NOON", "ABSENT", "SUNNY", "HIGH"): "NA",
    ("NOON", "ABSENT", "SUNNY", "MEDIUM"): "SOLAR_UNDER_UTILIZED",
    ("NOON", "ABSENT", "SUNNY", "LOW"): "SOLAR_UNDER_UTILIZED",
    ("NOON", "ABSENT", "SUNNY", "ZERO"): "SOLAR_DISCONNECTED",
    ("NOON", "PRESENT", "RAINY"): "NA",
    ("NOON", "PRESENT", "CLOUDY"): "NA",
    ("NOON", "IMPORTING", "SUNNY", "HIGH", "HIGH"): "NA",
    ("NOON", "IMPORTING", "SUNNY", "HIGH", "MEDIUM"): "SYSTEM_POWER_LEAKAGE",
    ("NOON", "IMPORTING", "SUNNY", "HIGH", "LOW"): "SYSTEM_POWER_LEAKAGE",
    ("NOON", "EXPORTING", "SUNNY"): "NA"
}


def get_solar_system_state(grid_status, solar_status, day_status, load_status, weather_status):

    # import ipdb; ipdb.set_trace()
    key = (day_status, grid_status, weather_status, solar_status, load_status)
    
    state = SYSTEM_STATES.get(key)
    while state is None and len(key) > 0:
        key = key[:-1]
        state = SYSTEM_STATES.get(key)

    return state


def generate_matrix():
    pass


if __name__ == "__main__":
    generate_matrix()

    print(get_solar_system_state("ABSENT", "HIGH", "NOON", "LOW", "SUNNY"))
    print(get_solar_system_state("ABSENT", "MEDIUM", "NOON", "LOW", "SUNNY"))
    print(get_solar_system_state("PRESENT", "MEDIUM", "NOON", "LOW", "SUNNY"))