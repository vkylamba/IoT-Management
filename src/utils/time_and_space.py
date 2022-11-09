import datetime
import unicodedata
import calendar


def convert_datetime_to_unix_time(time):
    return calendar.timegm(time.utctimetuple())


def convert_unix_time_to_datetime(unix_time):
    time_then = datetime.datetime(1970, 1, 1)
    time = time_then + datetime.timedelta(seconds=unix_time)
    return time


def address_numeric_to_string(num_address):
    address = [0, 0, 0, 0]
    i = 0
    while num_address > 0:
        address[i] = num_address % 256
        num_address //= 256
        i += 1
    return str(address[3]) + "." + str(address[2]) + "." + str(address[1]) + "." + str(address[0])


def address_string_to_numeric(str_address):
    temp_address = str_address.split('.')
    # print str(temp_address)
    num_address = 0
    i = 0
    while i < len(temp_address):
        num_address *= 256
        # print int(temp_address[i]);
        num_address += int(temp_address[i])
        i += 1
    return num_address


def is_number(value):
    """
        Method to check if the passed value is number.
    """
    try:
        float(value)
        return True, float(value)
    except ValueError:
        pass

    try:
        unicodedata.numeric(value)
        return True, unicodedata.numeric(value)
    except (TypeError, ValueError):
        pass

    return False, value
