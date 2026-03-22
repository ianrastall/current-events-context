import requests
import yaml
import json
import argparse
import time  # Built-in module, no pip install needed!
from datetime import datetime, timedelta

def fetch_gdelt_events(target_date_str):
    """
    Fetches top global news events from the GDELT 2.0 API for a specific date.
    target_date_str should be in 'YYYY-MM-DD' format.
    """
    clean_date = target_date_str.replace("-", "")
    start_time = f"{clean_date}000000"
    end_time = f"{clean_date}235959"
    
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": 'sourcelang:eng (theme:TAX_FNCACT OR theme:CRISISLEX_CONFLICT OR theme:LEGISLATION)',
        "mode": "artlist",
        "maxrecords": "50",
        "format": "json",
        "startdatetime": start_time,
        "enddatetime": end_time,
        "sort": "ToneDesc"
    }
    
    # Add a custom User-Agent to prevent immediate bot-throttling
    headers = {
        "User-Agent": "CurrentEventsYAMLBuilder/1.0 (Contact: your_email@example.com)"
    }
    
    print(f"Querying GDELT for {target_date_str}...")
    
    max_retries = 3
    for attempt in range(max_retries):
        response = requests.get(url, params=params, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('articles', [])
        elif response.status_code == 429:
            wait_time = 5 * (attempt + 1) # Wait 5s, then 10s, then 15s
            print(f"Rate limited (429). Waiting {wait_time} seconds before retrying... (Attempt {attempt+1}/{max_retries})")
            time.sleep(wait_time)
        else:
            print(f"Failed to fetch data: HTTP {response.status_code}")
            return []
            
    print("Exceeded maximum retries. Please try again later.")
    return []

if __name__ == "__main__":
    # This is the missing block that actually executes the script
    parser = argparse.ArgumentParser(description="Fetch GDELT events for a specific date.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    articles = fetch_gdelt_events(args.date)
    
    if articles:
        print(f"\nSuccessfully retrieved {len(articles)} articles!")
        # Optional: Print the title of the first article to confirm it worked
        print(f"First article title: {articles[0].get('title', 'No title')}")
    else:
        print("\nNo articles were returned.")