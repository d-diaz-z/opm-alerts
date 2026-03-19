import requests
import json
import os
import base64
from datetime import datetime
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# SETTINGS
DEBUG = True  
ENDPOINT = "https://www.opm.gov/json/operatingstatus.json"
LAST_ALERT_FILE = "last_alert.txt"
LOG_FILE = "activity.log"
LOG_DIR = "logs"
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def log_message(message):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            first_line = f.readline()

        if first_line.startswith("#DATE:"):
            file_date_str = first_line.strip().split(":")[1]
        else:
            file_date_str = today_str

        if file_date_str != today_str:
            backup_path = os.path.join(LOG_DIR, f"activity_{file_date_str}.log")
            os.rename(LOG_FILE, backup_path)
            with open(LOG_FILE, "w") as f:
                f.write(f"#DATE:{today_str}\n")
                f.write(f"[{timestamp}] Log rotated from {backup_path}\n")

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(f"#DATE:{today_str}\n")

    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

def send_sms_alert(message):
    try:
        token_info = json.loads(os.environ.get("GMAIL_TOKEN"))
        recipient = os.environ.get("SMS_RECIPIENT")

        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        service = build('gmail', 'v1', credentials=creds)

        msg = EmailMessage()
        msg.set_content(message)
        msg['To'] = recipient
        msg['Subject'] = 'OPM Status Alert'

        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={'raw': raw_msg}
        ).execute()

        log_message(f">>> ALERT SENT via Gmail. Message ID: {result['id']} <<<")

    except Exception as e:
        log_message(f"ERROR sending alert: {str(e)}")

def check_opm():
    try:
        response = requests.get(ENDPOINT, timeout=10)
        latest_record = response.json()
        
        current_status = latest_record.get('StatusSummary', 'Unknown')
        current_timestamp = latest_record.get('DateStatusPosted')

        log_message(f"Checking Status: {current_status} (Posted: {current_timestamp})")

        if os.path.exists(LAST_ALERT_FILE):
            with open(LAST_ALERT_FILE, 'r') as f:
                last_timestamp = f.read().strip()
        else:
            last_timestamp = ""

        if current_timestamp == last_timestamp:
            log_message("No new update since last alert. Skipping.")
            return

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

        if should_alert:
            send_sms_alert(f"OPM Status: {current_status}")
            
            with open(LAST_ALERT_FILE, 'w') as f:
                f.write(current_timestamp)
        else:
            log_message("Conditions not met for an alert.")

    except Exception as e:
        log_message(f"ERROR: {str(e)}")

if __name__ == "__main__":
    check_opm()
