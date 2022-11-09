import csv
import sys
from datetime import datetime
import random


class DataGenerator(object):
    """
        Class to generate random electricity data CSV files.
    """

    def __init__(self):
        time_now = datetime.now()
        self.file_name = time_now.strftime("data/data_%Y_%m_%d_%H.csv")

    def generate(self):

        with open(self.file_name, 'w') as csvfile:
            spamwriter = csv.writer(csvfile, delimiter=',')

            header = [
                # 'latitude',
                # 'longitude',
                'month',
                'day',
                'weekday',
                'hour',
                'power',
                'temperature',
                'humidity',
                'wind',

                'Bulb',
                'CFL',
                'Tubelgiht',
                'TV',
                'Refrigerator',
                'Fan',
                'Cooler',
                'AC',
                'Water Pump',
                'Iron',
                'Immersion'
            ]
            spamwriter.writerow(header)
            for datapoint in self.get_next():
                spamwriter.writerow(datapoint)

    def get_next(self):

        for i in range(0, 10000):
            # latitude = 19.31114335506464
            # longitude = 76.640625

            month = random.randrange(1, 13)
            day = random.randrange(1, 31)
            weekday = random.randrange(0, 7)
            hour = random.randrange(0, 24)

            winter = 0
            # Winter case
            if month in [9, 10, 11, 12, 1, 2]:
                winter = 1
            temp = 273 + (1 - winter) * 20 + 0.5 * hour + random.randrange(0, 5)
            humidity = random.randrange(0, 3)
            wind = random.randrange(0, 100)  # km/hour multiplied by 10

            daytime = 1 if (hour > 6 and hour < 19) else 0

            bulb = 0
            cfl = (1 - daytime) * (random.randrange(0, 5))
            tubelgiht = (1 - daytime) * (random.randrange(0, 3))

            tv = 1 if (weekday in [5, 6] and (hour > 6 and hour < 24)) or (hour > 19 and hour < 22) else 0

            refrigerator = 1 - winter

            fan = (1 - winter) * (random.randrange(daytime, 5))
            cooler = (1 - winter) * (1 if temp > (274 + 38) else 0)

            ac = (1 - winter) * (random.randrange(0, 2))

            water_pump = 1 if hour in [6, 7, 17, 19] else 0

            iron = daytime * random.randrange(0, 2)

            imerssion = (winter) * daytime * random.randrange(0, 2)

            power = (100 * bulb) + (10 * cfl) + (40 * tubelgiht) + (150 * tv) + (random.randrange(100, 200) * refrigerator) + (60 * fan) + (150 * cooler) + (1500 * ac) + (350 * water_pump) + (1000 * iron) + (1000 * imerssion)
            data = [
                # latitude, longitude,
                month, day, weekday, hour, power, temp, humidity, wind,
                bulb, cfl, tubelgiht, tv, refrigerator, fan, cooler, ac, water_pump, iron, imerssion
            ]
            yield data


if __name__ == '__main__':
    dg = DataGenerator()
    dg.generate()
