import os
import time


while True:
    print("Starting MQTT process...")
    try:
        os.system("python manage.py mqtt")
    except Exception as ex:
        print(f"MQTT Process exception: {ex}")
        time.sleep(3)
