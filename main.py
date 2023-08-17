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
# Create a Supabase client
client = supabase.Client(SUPABASE_URL, SUPABASE_API_KEY)

openai.api_key = os.environ.get("OPENAI_API_KEY")

RIZE_MAIL_ID = os.environ.get("RIZE_MAIL_ID")

max_results = 1


def extract_metrics(data, subject, date):
    try:
        metrics_dict = {}
        work_hours_pattern = r"Work Hours[\s-]+\r\n([\d hr min]+)"
        work_hours = re.search(work_hours_pattern, data)

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
            match = re.search(pattern, data)
            if match:
                metrics_dict[
                    key.lower().replace(" ", "_").replace("-", "")
                ] = time_to_hours(match.group(2))
            else:
                metrics_dict[key.lower().replace(" ", "_")] = 0

        date_and_day = getDate(subject, date)
        metrics_dict["date"] = date_and_day[0]
        metrics_dict["day"] = date_and_day[1]
        metrics_dict["work_hours"] = (
            time_to_hours(work_hours.group(1)) if work_hours else 0
        )
        metrics_dict["categories"] = []

        categories = get_categories(data)

        if categories:
            for category in categories:
                metrics_dict["categories"].append(
                    {
                        "name": category["name"],
                        "time": category["time"],
                    }
                )
        else:
            # if categories is empty, try to get categories using get_categories2
            categories = get_categories2(data)
            for category in categories:
                metrics_dict["categories"].append(
                    {
                        "name": category["name"],
                        "time": category["time"],
                    }
                )

        metrics_dict["gpt_context"] = gpt_context_string(metrics_dict)

        raw_data = process_raw_data(data)
        metrics_dict["raw_data"] = raw_data
        metrics_dict["embedding"] = get_embedding(metrics_dict["gpt_context"])

        client.table("timelog").insert([metrics_dict]).execute()

        return metrics_dict

    except Exception as e:
        print("extract_metrics:", e)


def get_embedding(gpt_context):
    response = openai.Embedding.create(
        input=gpt_context, model="text-embedding-ada-002"
    )
    return response["data"][0]["embedding"]


def gpt_context_string(metrics_dict):
    # capitalise the first letter of each key and replace _ with spaces and use hours_to_time on all values except date and day
    output = []

    for key, value in metrics_dict.items():
        if key in ("date", "day"):
            output.append(f"{key.replace('_', ' ').capitalize()}: {value}")
        elif key == "categories":
            categories = ", ".join(
                [f"{item['name']}: {hours_to_time(item['time'])}" for item in value]
            )
            output.append(f"{key.capitalize()}: [{categories}]")
        else:
            output.append(
                f"{key.replace('_', ' ').capitalize()}: {hours_to_time(value)}"
            )

    result = ", ".join(output)
    return result


def process_raw_data(data):
    start_index = data.find("Did you know")
    if start_index != -1:
        # Remove everything from start_index onwards
        text = data[:start_index]
    return text


def get_categories(data):
    try:
        categories_pattern = r"Categories\s*-+\s*\r\n\r\n((?:[\w\s]+\s*(?:\r\n|\n)+\d+%\s*\r\n[\d hr min]+\s*(?:\r\n|\n)+)+)-+"
        categories_text = re.search(categories_pattern, data)

        categories = []

        if categories_text:
            category_info = re.findall(
                r"([\w\s]+)\s*(?:\r\n|\n)+\d+%[\s-]*\r\n([\d hr min]+)",
                categories_text.group(1),
            )

            for category in category_info:
                category_name = re.sub(
                    r"\b(?:Percent|Total Time|\d+%)\b", "", category[0]
                ).strip()

                category_time = time_to_hours(category[1])

                categories.append({"name": category_name, "time": category_time})

        return categories
    except Exception as e:
        print("get_categories:", e)


def get_categories2(data):
    try:
        # remove all the text before the word "Categories"
        data = re.sub(r".*Categories", "Categories", data, flags=re.DOTALL)
        data = re.sub(r"\b(?:Percent|Total Time|\d+%)\b", "", data).strip()
        data = re.sub(r"<", "", data)

        # get all the words before the word Sessions appears
        categories_text = re.search(r"(.*?)Sessions", data, flags=re.DOTALL)
        categories = re.findall(
            r"([\w\s]+)\s*(?:\r\n|\n)+\d+%[\s-]*\r\n([\d hr min]+)",
            categories_text.group(1),
        )
        # strip the category name and time
        categories = [
            {"name": category[0].strip(), "time": time_to_hours(category[1].strip())}
            for category in categories
        ]

        return categories

    except Exception as e:
        print("get_categories2:", e)


def time_to_hours(time_str):
    time_parts = re.findall(r"\d+", time_str)
    if len(time_parts) == 2:
        hours, minutes = map(int, time_parts)
    else:
        hours, minutes = 0, int(time_parts[0])

    # Convert hours and minutes to total hours but only till 4 decimal places
    total_hours = round(hours + minutes / 60, 4)

    return total_hours


def hours_to_time(total_hours):
    # Calculate the hours and minutes
    hours = int(total_hours)
    minutes = round((total_hours - hours) * 60)

    # Format the time string
    if hours == 0:
        time_str = f"{minutes} min"
    elif minutes == 0:
        time_str = f"{hours} hr"
    else:
        time_str = f"{hours} hr {minutes} min"

    return time_str


def getDate(text, date):
    # get the date from date string
    dateMatch = re.search(r"(\d+)", date).group(1)
    dateObj = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %z")
    date = dateObj.strftime("%Y-%m-%d")
    # Define the regular expression pattern to extract day, month, and date information
    pattern = r"Your Daily Report for (\w+), (\w+) (\d+)"

    # Use regular expression to extract the day, month, and date from the text
    match = re.match(pattern, text)
    day = match.group(1)

    if int(dateMatch) != int(match.group(3)):
        date = dateObj - timedelta(days=1)

    return date, day


def getEmails():
    # Variable creds will store the user access token.
    # If no valid token found, we will create one.
    creds = None

    # The file token.pickle contains the user access token.
    # Check if it exists
    if os.path.exists("token.pickle"):
        print("Loading Credentials From File...")
        # Read the token from the file and store it in the variable creds
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # If credentials are not available or are invalid, ask the user to log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the access token in token.pickle file for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    # Connect to the Gmail API
    service = build("gmail", "v1", credentials=creds)

    # Request a list of last 10 messages from 'rize'
    result = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=f"from:{RIZE_MAIL_ID} subject:Your Daily Report",
            maxResults=max_results,
        )
        .execute()
    )

    messages = result.get("messages")

    # Iterate through the last 10 messages
    for msg in messages:
        # Get the message from its id
        txt = service.users().messages().get(userId="me", id=msg["id"]).execute()

        # Use try-except to avoid any Errors
        try:
            # Get value of 'payload' from dictionary 'txt'
            payload = txt["payload"]
            headers = payload["headers"]

            # Look for Subject and Sender Email in the headers
            for d in headers:
                if d["name"] == "Subject":
                    subject = d["value"]
                if d["name"] == "From":
                    sender = d["value"]
                # get date of email
                if d["name"] == "Date":
                    date = d["value"]

            # The Body of the message is in Encrypted format. So, we have to decode it.
            # Get the data and decode it with base 64 decoder.
            parts = payload.get("parts")[0]
            data = parts["body"]["data"]
            data = data.replace("-", "+").replace("_", "/")
            decoded_data = base64.b64decode(data).decode("utf-8")  # Decode the data

            # Extract the metrics from the email body
            extract_metrics(decoded_data, subject, date)
        except:
            pass


getEmails()
