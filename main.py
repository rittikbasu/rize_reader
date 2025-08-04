import base64
import os.path
import pickle
import re
from datetime import datetime, timedelta

import supabase
import openai
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define the SCOPES. If modifying it, delete the token.pickle file.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY")
RIZE_MAIL_ID = os.environ.get("RIZE_MAIL_ID")

# Create a Supabase client
client = supabase.Client(SUPABASE_URL, SUPABASE_API_KEY)

openai.api_key = os.environ.get("OPENAI_API_KEY")

max_results = 1


def load_credentials(SCOPES):
    creds = None
    if os.path.exists("token.pickle"):
        print("Loading Credentials From File...")
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return creds


def initialize_gmail_service(creds):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_email_list(service, RIZE_MAIL_ID, max_results):
    query = f'from:{RIZE_MAIL_ID} subject:"Your Daily Report"'
    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return result.get("messages")


def get_email_content(service, email):
    txt = service.users().messages().get(userId="me", id=email["id"]).execute()
    payload = txt["payload"]
    headers = payload["headers"]

    subject = sender = date = None
    for d in headers:
        if d["name"] == "Subject":
            subject = d["value"]
        if d["name"] == "From":
            sender = d["value"]
        if d["name"] == "Date":
            date = d["value"]

    print("subject:", subject)

    parts = payload.get("parts")
    if not parts or "body" not in parts[0] or "data" not in parts[0]["body"]:
        raise ValueError("Email format is unexpected. Skipping this email.")

    data = parts[0]["body"]["data"]
    data = data.replace("-", "+").replace("_", "/")
    decoded_data = base64.b64decode(data).decode("utf-8")

    return {"subject": subject, "sender": sender, "date": date, "body": decoded_data}


def convert_time_to_hours(time_str):
    time_parts = re.findall(r"\d+", time_str)
    if len(time_parts) == 2:
        hours, minutes = map(int, time_parts)
    else:
        hours, minutes = 0, int(time_parts[0])

    total_hours = round(hours + minutes / 60, 4)

    return total_hours


def convert_hours_to_time(total_hours):
    hours = int(total_hours)
    minutes = round((total_hours - hours) * 60)

    if hours == 0:
        time_str = f"{minutes} min"
    elif minutes == 0:
        time_str = f"{hours} hr"
    else:
        time_str = f"{hours} hr {minutes} min"

    return time_str


def extract_date_from_subject_and_date(subject, date):
    date_match = re.search(r"(\d+)", date).group(1)
    date_obj = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %z")
    date_str = date_obj.strftime("%Y-%m-%d")

    pattern = r"Your Daily Report for (\w+), (\w+) (\d+)"
    match = re.match(pattern, subject)
    day = match.group(1)

    if int(date_match) != int(match.group(3)):
        date_str = (date_obj - timedelta(days=1)).strftime("%Y-%m-%d")

    return date_str, day


def extract_categories_from_data(data):
    categories_pattern = r"Categories\s*-+\s*\r\n\r\n((?:[\w\s]+\s*(?:\r\n|\n)+\d+%\s*\r\n[\d hr min<]+\s*(?:\r\n|\n)+)+)-+"
    categories_text = re.search(categories_pattern, data)

    categories = []

    if categories_text:
        category_info = re.findall(
            r"([\w\s]+)\s*(?:\r\n|\n)+\d+%[\s-]*\r\n([\d hr min<]+)",
            categories_text.group(1),
        )

        for category in category_info:
            category_name = re.sub(
                r"\b(?:Percent|Total Time|\d+%)\b", "", category[0]
            ).strip()

            # Clean up time string by removing "<" if present
            time_str = category[1].replace("<", "").strip()
            category_time = convert_time_to_hours(time_str)

            categories.append({"name": category_name, "time": category_time})

    return categories


def extract_categories_from_data_alternative(data):
    data = re.sub(r".*Categories", "Categories", data, flags=re.DOTALL)
    data = re.sub(r"\b(?:Percent|Total Time|\d+%)\b", "", data).strip()

    # Find the Categories section until the next section
    categories_match = re.search(
        r"Categories\s*-+\s*(.*?)(?:-------------------|\Z)", data, flags=re.DOTALL
    )

    if not categories_match:
        return []

    categories_text = categories_match.group(1)

    # Extract category name and time, handling "< 1 min" format
    categories = []
    lines = categories_text.split("\r\n")

    i = 0
    while i < len(lines) - 2:
        if i + 2 < len(lines) and "%" in lines[i + 1]:
            name = lines[i].strip()
            time_str = lines[i + 2].strip().replace("<", "").strip()

            if name and time_str:
                time = convert_time_to_hours(time_str)
                categories.append({"name": name, "time": time})
        i += 1

    return categories


def generate_gpt_context_string(metrics_dict):
    output = []

    for key, value in metrics_dict.items():
        if key in ("date", "day"):
            output.append(f"{key.replace('_', ' ').capitalize()}: {value}")
        elif key == "categories":
            categories = ", ".join(
                [
                    f"{item['name']}: {convert_hours_to_time(item['time'])}"
                    for item in value
                ]
            )
            output.append(f"{key.capitalize()}: [{categories}]")
        else:
            output.append(
                f"{key.replace('_', ' ').capitalize()}: {convert_hours_to_time(value)}"
            )

    result = ", ".join(output)
    return result


def remove_unnecessary_data(data):
    start_index = data.find("Did you know")
    if start_index != -1:
        data = data[:start_index]
    return data


def get_embedding(gpt_context):
    response = openai.Embedding.create(
        input=gpt_context, model="text-embedding-ada-002"
    )
    return response["data"][0]["embedding"]


def extract_email_metrics(email_content):
    try:
        metrics = {}
        work_hours_pattern = r"Work Hours[\s-]+\r\n([\d hr min]+)"
        work_hours = re.search(work_hours_pattern, email_content["body"])

        keys = [
            "Focus",
            "Meetings",
            "Breaks",
            "Other",
            "Work categories",
            "Non-work categories",
        ]

        for key in keys:
            pattern = r"{}\r\n(\d+)%\r\n([\d hr min]+)".format(key)
            match = re.search(pattern, email_content["body"])
            if match:
                # Format key names correctly for database
                if key == "Work categories":
                    clean_key = "work_categories"
                elif key == "Non-work categories":
                    clean_key = "nonwork_categories"
                else:
                    clean_key = key.lower()

                metrics[clean_key] = convert_time_to_hours(match.group(2))
            else:
                # Format key names correctly for database
                if key == "Work categories":
                    clean_key = "work_categories"
                elif key == "Non-work categories":
                    clean_key = "nonwork_categories"
                else:
                    clean_key = key.lower()

                metrics[clean_key] = 0

        # Fix the issue with date extraction
        try:
            date_and_day = extract_date_from_subject_and_date(
                email_content["subject"], email_content["date"]
            )
            metrics["date"] = date_and_day[0]
            metrics["day"] = date_and_day[1]
        except Exception as e:
            print(f"Error extracting date: {e}")
            # Fallback date extraction from subject
            subject = email_content["subject"]
            date_match = re.search(r"Your Daily Report for (\w+), (\w+) (\d+)", subject)
            if date_match:
                day_name = date_match.group(1)
                month_name = date_match.group(2)
                day_num = date_match.group(3)
                # Assuming the year is current year
                date_str = f"{datetime.now().year}-{month_name[:3]}-{int(day_num):02d}"
                metrics["date"] = date_str
                metrics["day"] = day_name
            else:
                # If all else fails, use current date
                metrics["date"] = datetime.now().strftime("%Y-%m-%d")
                metrics["day"] = "Unknown"

        metrics["work_hours"] = (
            convert_time_to_hours(work_hours.group(1)) if work_hours else 0
        )
        metrics["categories"] = []

        try:
            categories = extract_categories_from_data(email_content["body"])
            if categories:
                for category in categories:
                    metrics["categories"].append(
                        {
                            "name": category["name"],
                            "time": category["time"],
                        }
                    )
            else:
                categories = extract_categories_from_data_alternative(
                    email_content["body"]
                )
                for category in categories:
                    metrics["categories"].append(
                        {
                            "name": category["name"],
                            "time": category["time"],
                        }
                    )
        except Exception as e:
            print(f"Error extracting categories: {e}")
            # Add empty categories if extraction fails
            metrics["categories"] = []

        metrics["gpt_context"] = generate_gpt_context_string(metrics)

        raw_data = remove_unnecessary_data(email_content["body"])
        metrics["raw_data"] = raw_data
        metrics["embedding"] = get_embedding(metrics["gpt_context"])

        return metrics

    except Exception as e:
        print("extract_email_metrics:", e)
        return None


def main():
    creds = load_credentials(SCOPES)
    service = initialize_gmail_service(creds)
    email_list = get_email_list(service, RIZE_MAIL_ID, max_results)

    if not email_list:
        print("No emails found")
        return

    for email in email_list:
        email_content = get_email_content(service, email)
        metrics = extract_email_metrics(email_content)

        if metrics is None:
            print(
                f"Failed to extract metrics for email with subject: {email_content.get('subject')}"
            )
            continue

        print(f"📅 Date: {metrics.get('date')}, 🎯 Focus: {metrics.get('focus')} hours")

        try:
            client.table("timelog").insert([metrics]).execute()
            print(f"Successfully inserted data for {metrics.get('date')}")
        except Exception as e:
            if "duplicate key value" in str(e):
                print(f"Skipping duplicate entry for date: {metrics.get('date')}")
            else:
                print(f"An error occurred while inserting data into Supabase: {e}")


if __name__ == "__main__":
    main()
