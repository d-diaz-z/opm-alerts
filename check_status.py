import requests
import json
import os
from datetime import datetime

# SETTINGS
DEBUG = True  
ENDPOINT = "https://www.opm.gov/json/operatingstatus.json"
LAST_ALERT_FILE = "last_alert.txt"
LOG_FILE = "activity.log"

def log_message(message):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Rotation Logic: Check if existing log is from a previous day
    if os.path.exists(LOG_FILE):
        # Get the last modification time of the file
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(LOG_FILE))
        file_date_str = file_mod_time.strftime("%Y-%m-%d")

        # If the file's date is not today, rename it to a backup
        if file_date_str != today_str:
            backup_name = f"activity_{file_date_str}.log"
            os.rename(LOG_FILE, backup_name)
            # Optional: Start the new log with a rotation notice
            with open(LOG_FILE, "a") as f:
                f.write(f"[{timestamp}] Log rotated from {backup_name}\n")

    # Write the actual message to the current activity.log
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

# Use it in your check_opm() function as before:
# log_message(f"Checking Status: {current_status}")

def check_opm():
    try:
        response = requests.get(ENDPOINT, timeout=10)
        # OPM current status returns a single object, not a list
        latest_record = response.json()
        
        current_status = latest_record.get('StatusSummary', 'Unknown')
        current_timestamp = latest_record.get('DateStatusPosted')

        log_message(f"Checking Status: {current_status} (Posted: {current_timestamp})")

        # 3. Check against last alerted timestamp
        if os.path.exists(LAST_ALERT_FILE):
            with open(LAST_ALERT_FILE, 'r') as f:
                last_timestamp = f.read().strip()
        else:
            last_timestamp = ""

        if current_timestamp == last_timestamp:
            log_message("No new update since last alert. Skipping.")
            return

        # 4. Alert Logic
        is_open = "open" in current_status.lower()
        should_alert = False

        if DEBUG:
            if is_open:
                should_alert = True
                log_message("DEBUG MODE: Triggering alert because status is OPEN.")
        else:
            if not is_open:
                should_alert = True
                log_message(f"CRITICAL: Non-Open status detected: {current_status}")

        # 5. Send Alert and Save Progress
        if should_alert:
            # TRIGGER ALERT LOGIC HERE (e.g., Google App Script)
            log_message(">>> ALERT SIGNAL SENT <<<") 
            
            with open(LAST_ALERT_FILE, 'w') as f:
                f.write(current_timestamp)
        else:
            log_message("Conditions not met for an alert.")

    except Exception as e:
        log_message(f"ERROR: {str(e)}")

if __name__ == "__main__":
    check_opm()
