import os
import time
from bson.objectid import ObjectId
import requests
from bs4 import BeautifulSoup

# Import the custom connection utility from your project
from mongodb_functions import connect_to_mongodb, DATABASE_NAME


def scrape_dice_description(url: str) -> str | None:
    """
    Fetches a Dice.com job page and extracts the job description HTML. 

    Args:
        url: The URL of the Dice.com job posting.

    Returns:
        A tuple containing a status string ('success', 'gone', 'error')
        and the HTML content or None.
    """
    if not url:
        print("  - Skipping: No URL provided for this job record.")
        return 'error', None

    try:
        # Set a user-agent to mimic a real browser and a timeout
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)

        # Handle cases where the job is gone or not found
        if response.status_code in [404, 410]:
            print(f"  - Info: Job listing not available at {url} (Status: {response.status_code}).")
            return 'gone', None

        response.raise_for_status()  # Raise an exception for other bad status codes (e.g., 500, 403)

        soup = BeautifulSoup(response.content, 'html.parser')
        job_description_div = soup.find('div', id='jobDescription')

        if job_description_div is None:
            print(f"  - Error: Could not find the job description section on page {url}.")
            return 'error', None

        return 'success', str(job_description_div)

    except requests.exceptions.RequestException as e:
        print(f"  - Error connecting to {url}: {e}")
        # Check if the error is a 4xx/5xx client/server error that wasn't a 404/410
        if e.response is not None and e.response.status_code >= 400:
            return 'gone', None # Treat other client/server errors as 'gone'
        return 'error', None
    except Exception as e:
        print(f"  - An unexpected error occurred during scraping of {url}: {e}")
        return 'error', None

def main():
    """
    Main function to connect to MongoDB, find jobs without HTML descriptions,
    scrape them, and update the database.
    """
    MONGO_CLIENT, db = connect_to_mongodb()
    if db is None:
        print("FATAL: Could not connect to the database. Exiting.")
        return

    jobs_collection = db.dice_jobs
    print(f"Connected to MongoDB database: {DATABASE_NAME}")

    # Find the first 100 jobs that do NOT have an 'html_description' field yet.
    jobs_to_scrape = list(jobs_collection.find({"is_active": {"$exists": False}}))

    if not jobs_to_scrape:
        print("No jobs found that require scraping. All records seem to be up-to-date.")
        return

    print(f"Found {len(jobs_to_scrape)} jobs to scrape...")

    for i, job in enumerate(jobs_to_scrape):
        job_id = job['_id']
       
        dice_url = job.get('url')
        print(f"\n[{i+1}/{len(jobs_to_scrape)}] Processing job ID: {job_id}")

        status, html_content = scrape_dice_description(dice_url)

        if status == 'success':
            update_payload = {
                "$set": {"html_description": html_content, "is_active": True}
            }
            jobs_collection.update_one({"_id": job_id}, update_payload)
            print(f"  - Success: Saved HTML description for job {job_id}.")
        elif status == 'gone':
            # The job is no longer active on Dice.com
            jobs_collection.update_one({"_id": job_id}, {"$set": {"is_active": False}})
            print(f"  - Inactive: Marked job {job_id} as inactive.")
        
        time.sleep(1) # Be polite to the server

    MONGO_CLIENT.close()
    print("\nScript finished. MongoDB connection closed.")

if __name__ == '__main__':
    main()
