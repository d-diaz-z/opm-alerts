import requests
import json
import os
import base64
import re
import urllib.parse
from datetime import datetime
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# SETTINGS
DEBUG = False 
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

def shorten_url(url):
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={urllib.parse.quote(url)}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            return response.text.strip()
        else:
            log_message(f"WARNING: TinyURL returned status {response.status_code}, using original URL.")
            return url
    except Exception as e:
        log_message(f"WARNING: URL shortening failed: {str(e)}, using original URL.")
        return url
        
def format_applies_to(applies_to_str):
    try:
        dt = datetime.strptime(applies_to_str, "%B %d, %Y")
        return dt.strftime("%m/%d/%y")
    except ValueError:
        return applies_to_str[:15] + "..." if len(applies_to_str) > 15 else applies_to_str

def build_sms(latest_record):
    current_status = latest_record.get('StatusSummary', 'Unknown')
    short_msg = latest_record.get('ShortStatusMessage', '').strip()
    long_msg = latest_record.get('LongStatusMessage', '').strip()
    applies_to = format_applies_to(latest_record.get('AppliesTo', 'N/A'))
    url = shorten_url(latest_record.get('Url', latest_record.get('StatusWebPage', '')))

    # Clean HTML entities and collapse whitespace
    short_msg = re.sub(r'&[a-z]+;', '', short_msg).strip()
    long_msg = re.sub(r'&[a-z]+;', '', long_msg).strip()
    long_msg = ' '.join(long_msg.split())

    # If short and summary are the same, use long message for more detail
    if short_msg == current_status:
        detail = long_msg
    else:
        detail = short_msg

    # Build body with guaranteed URL at end
    url_line = f"\n{url}"
    date_line = f"{applies_to}\n"
    overhead = len(date_line) + len(url_line)
    max_detail = 160 - overhead - 3  # 3 for ellipsis

    if len(detail) > max_detail:
        detail = detail[:max_detail] + "..."

    sms_subject = current_status
    sms_body = f"{date_line}{detail}{url_line}"

    return sms_subject, sms_body

def send_sms_alert(subject, message):
    try:
        token_info = os.environ.get("GMAIL_TOKEN")
        recipient = os.environ.get("SMS_RECIPIENT")

        if not token_info or not recipient:
            log_message("ERROR: GMAIL_TOKEN or SMS_RECIPIENT secret not set.")
            return

        creds = Credentials.from_authorized_user_info(
            json.loads(token_info), SCOPES
        )
        service = build('gmail', 'v1', credentials=creds)

        msg = EmailMessage()
        msg.set_content(message)
        msg['To'] = recipient
        msg['Subject'] = subject

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
            sms_subject, sms_body = build_sms(latest_record)
            send_sms_alert(sms_subject, sms_body)

            with open(LAST_ALERT_FILE, 'w') as f:
                f.write(current_timestamp)
        else:
            log_message("Conditions not met for an alert.")

    except Exception as e:
        log_message(f"ERROR: {str(e)}")

if __name__ == "__main__":
    check_opm()
