from django.core.management.base import BaseCommand
from django.db import transaction


from device.models import (
    Device,
    Data,
)
import csv
import sys
from datetime import datetime


class Command(BaseCommand):

    """
        Command to load initial data into database.
    """

    help = 'Loads initial data set into database.'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('device_ip', nargs='+', type=str)

        # Named (optional) arguments
        parser.add_argument(
            '--datafile',
            default='',
            help='Use the data file as source.',
        )

    @transaction.atomic
    def handle(self, *args, **options):

        data_file = options.get('datafile', None)

        device_ip = options.get('device_ip')

        if not device_ip:
            sys.exit("Device ip not provided.")

        # Find the deivce
        device, created = Device.objects.get_or_create(ip_address=device_ip[0])
        if created:
            device.save()

        data = []
        if data_file:
            data, data_type = self.read_data_file(data_file)

        if len(data) > 1:
            header = data[0]
            header_dict = {}
            for idx, title in enumerate(header):
                header_dict.update({
                    title: idx
                })
            data = data[1:]

        for data_line in data:
            print(data_line)
            data_obj = Data(
                device=device,
                data_arrival_time=datetime.strptime(data_line[header_dict['time']], "%d-%b-%Y %H:%M"),
                voltage=data_line[header_dict['voltage']].replace('.', ''),
                current=data_line[header_dict['current']].replace('.', ''),
                power=data_line[header_dict['power']].replace('.', ''),
                energy=data_line[header_dict['energy']].replace('.', ''),
                runtime=data_line[header_dict['runtime']].replace('.', ''),
                state=0
            )
            data_obj.save()

    def read_data_file(self, datafile):
        data = []
        file_type = datafile.split('.')[-1]
        if 'json' in file_type:
            json_file = open(datafile, encoding='utf-8')
            data = json.load(json_file)
            json_file.close()
        elif 'csv' in file_type:
            with open(datafile) as csvfile:
                spamreader = csv.reader(csvfile, delimiter=',')
                for row in spamreader:
                    data.append(row)
        return data, file_type
