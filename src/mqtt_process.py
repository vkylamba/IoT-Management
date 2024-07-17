import os
import time
import subprocess

while True:
    print("Starting MQTT process...")
    # Check if the process is already running
    proc = subprocess.Popen(["ps -ef | grep 'python manage.py mqtt'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    processes_running = out.decode().split('\n')
    if len(processes_running) > 2:
        print("MQTT process already running.")
    else:
        os.system("python manage.py mqtt")
    time.sleep(10)
