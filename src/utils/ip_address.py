from typing import Tuple


def is_valid_ip_address(str_address: str) -> Tuple[bool, int]:
    temp_address = str_address.split('.')
    is_valid = False
    address_numeric = None
    if len(temp_address) == 4:
        try:
            num_address = 0
            i = 0
            while i < len(temp_address):
                num_address *= 256
                num_address += int(temp_address[i]) if temp_address[i] != '' else 0
                i += 1
        except Exception as e:
            pass
        else:
            is_valid = True
            address_numeric = num_address
    
    return is_valid, address_numeric
