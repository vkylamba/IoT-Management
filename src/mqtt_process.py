#!/usr/bin/env python
"""
MQTT Process Manager - Robust monitoring and restart of MQTT listener.

This script monitors the Django MQTT management command and automatically
restarts it if it crashes. Uses psutil for reliable process detection.

Instead of using this script directly, prefer supervisord configuration
which provides better process management, logging, and restart policies.
See supervisord.conf for the recommended setup.
"""
import os
import sys
import time
import signal
import logging
import subprocess
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - MQTT ProcessManager - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/mqtt_process_manager.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
MQTT_COMMAND = [sys.executable, 'manage.py', 'mqtt']
HEALTH_CHECK_INTERVAL = 30  # seconds between health checks
RESTART_DELAY = 5  # seconds to wait before restarting after crash
MAX_RESTART_ATTEMPTS = 5  # max consecutive crash attempts before giving up
RESTART_RESET_TIME = 300  # reset restart counter after 5 minutes of stable uptime

# State tracking
mqtt_process = None
restart_count = 0
last_crash_time = None
stable_start_time = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    if mqtt_process and mqtt_process.poll() is None:
        logger.info("Terminating MQTT process...")
        mqtt_process.terminate()
        try:
            mqtt_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("MQTT process did not terminate, killing...")
            mqtt_process.kill()
    sys.exit(0)


def is_mqtt_process_running():
    """Check if MQTT process is still running."""
    if mqtt_process is None:
        return False
    returncode = mqtt_process.poll()
    return returncode is None


def start_mqtt_process():
    """Start the MQTT listener process."""
    global mqtt_process, restart_count, last_crash_time, stable_start_time
    
    try:
        logger.info(f"Starting MQTT listener... (attempt {restart_count + 1})")
        
        # Start the process with proper stdout/stderr handling
        mqtt_process = subprocess.Popen(
            MQTT_COMMAND,
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        logger.info(f"MQTT listener started with PID {mqtt_process.pid}")
        restart_count += 1
        last_crash_time = time.time()
        
        if restart_count == 1:
            stable_start_time = time.time()
        
        return True
    except Exception as e:
        logger.error(f"Failed to start MQTT process: {e}")
        return False


def handle_mqtt_crash():
    """Handle MQTT process crash."""
    global restart_count, stable_start_time
    
    if stable_start_time and (time.time() - stable_start_time) > RESTART_RESET_TIME:
        logger.info(f"MQTT process was stable for {RESTART_RESET_TIME}s, resetting restart counter")
        restart_count = 0
        stable_start_time = time.time()
    
    if restart_count >= MAX_RESTART_ATTEMPTS:
        logger.error(
            f"MQTT process crashed {MAX_RESTART_ATTEMPTS} times in a short period. "
            f"Giving up. Check logs for root cause."
        )
        return False
    
    logger.warning(f"MQTT process crashed. Waiting {RESTART_DELAY}s before restart...")
    time.sleep(RESTART_DELAY)
    
    return start_mqtt_process()


def monitor_process_output():
    """Non-blocking read and log any process output."""
    if mqtt_process and mqtt_process.stdout:
        import select
        # Use select to check if there's data without blocking
        ready, _, _ = select.select([mqtt_process.stdout], [], [], 0)
        if ready:
            line = mqtt_process.stdout.readline()
            if line:
                print(f"[MQTT] {line.rstrip()}")


def main():
    """Main process manager loop."""
    logger.info("MQTT Process Manager started")
    logger.info(f"Health check interval: {HEALTH_CHECK_INTERVAL}s")
    logger.info(f"Max restart attempts: {MAX_RESTART_ATTEMPTS} in {RESTART_RESET_TIME}s")
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start initial process
    if not start_mqtt_process():
        logger.error("Failed to start MQTT process on first attempt")
        sys.exit(1)
    
    # Main monitoring loop
    try:
        while True:
            time.sleep(HEALTH_CHECK_INTERVAL)
            
            # Monitor output
            monitor_process_output()
            
            # Check if process is still running
            if not is_mqtt_process_running():
                logger.warning("MQTT process is not running")
                if not handle_mqtt_crash():
                    logger.error("Giving up after multiple crash attempts")
                    sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Unexpected error in process manager: {e}", exc_info=True)
        if mqtt_process and mqtt_process.poll() is None:
            mqtt_process.kill()
        sys.exit(1)


if __name__ == '__main__':
    main()
