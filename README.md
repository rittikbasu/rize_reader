# rize-reader

This is the companion python script for [frize](https://github.com/rittikbasu/frize). It collects data from your email and stores it in a Supabase database.

## Prerequisites

Before you begin, ensure you have the following:

- **Python:** The script requires Python to be installed on your machine. You can download it from [python.org](https://www.python.org/downloads/).
- **Gmail API Credentials:** Follow the instructions in the [Gmail API Python Quickstart Guide](https://developers.google.com/gmail/api/quickstart/python) to set up your Google Cloud project and obtain the credentials.
- **Supabase Account:** Sign up for a Supabase account to create a database and obtain the `SUPABASE_URL` and `SUPABASE_API_KEY` for API access.
- **OpenAI API Key:** Obtain an API key from OpenAI as we will use it to generate embeddings for our data.

## Installation

1. Clone this repository on your local machine
   ```bash
   git clone https://github.com/rittikbasu/rize_reader.git
   ```
2. Navigate to the project directory
   ```bash
    cd rize_reader
   ```
3. Create a virtual environment
   ```bash
   python3 -m venv venv
   ```
4. Install the dependencies
   ```bash
   pip3 install -r requirements.txt
   ```
5. Activate the virtual environment
   - for macOS/Linux:
     ```bash
     source venv/bin/activate
     ```
   - for Windows:
     ```bash
     venv\Scripts\activate
     ```
6. Export the required environment variables in your terminal
   ```bash
   export SUPABASE_URL=YOUR_SUPABASE_URL SUPABASE_API_KEY=YOUR_SUPABASE_API_KEY OPENAI_API_KEY=YOUR_OPENAI_API_KEY RIZE_MAIL_ID=YOUR_RIZE_MAIL_ID
   ```
   Note: Put the mail address you recieve your rize emails from in `RIZE_MAIL_ID`.
7. Save your Gmail API credentials in the same directory as `main.py` and rename it to `credentials.json`.
8. Run the script
   ```bash
   python3 main.py
   ```
9. You will be prompted to authorize the script to access your Gmail account. You might need to add a redirect_uri to your OAuth consent screen. You can do this by adding the required redirect_uri to the list of Authorized redirect URIs in the OAuth consent screen in the Google Cloud Console.
10. The script will start collecting data from your email and storing it in your Supabase database. You can view the data in your Supabase dashboard.

Note: If you've already been using Rize for a while then go to your Gmail account and search for rize and get the total number of emails. Then go to `main.py` and change the value of `max_results` to the total number of emails you have. This will ensure that the script collects all your previous data as well. Once the script has finished running you can change the value of `max_results` back to 1.

## Automation

You can automate the script to run at regular intervals using a cron job. I personally run it on a cloud server but you can also run it on your local machine. To do this follow the steps below:

1. Open your terminal and type `crontab -e` to open the cron table.
2. Get the path to the python3 executable in your virtual environment by running `which python3` in your terminal and copy it.
3. Add the following line to the cron table:
   ```bash
    00 00 * * * /path/to/venv/bin/python3 /path/to/rize_reader/main.py
   ```
   This will run the script every day at 12:00 AM.
4. Use an absolute path for the `credentials.json` file in `main.py` as cron jobs do not have access to the current working directory.

### Note

- Replace `/path/to/rize_reader` with the path to the rize_reader directory and `/path/to/venv/bin/python3` with the path to the python3 executable in your virtual environment.
- If you get an error where it cannot find the environment variables then declare the variables at the top of the cron table.

## Contributing

Contributions are always welcome! Feel free to open an issue or submit a pull request if you have any ideas or suggestions.
