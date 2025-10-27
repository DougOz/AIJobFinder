"""
A simple utility to view the top-ranked jobs from the database
after running the full prediction pipeline.

This script:
1. Connects to MongoDB.
2. Queries the 'dice_jobs' collection.
3. Sorts the jobs by the 'model1_prediction' field in descending order.
4. Prints a clean, formatted list of the top N jobs.
"""

import sys
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

# --- CONFIGURATION ---
DICE_JOBS_COLLECTION = "dice_jobs"
PREDICTION_FIELD_NAME = "model1_prediction"
TOP_N = 100 # How many of the top jobs to display
# --- END CONFIGURATION ---

def view_top_jobs():
    """
    Connects to MongoDB and prints the top-ranked jobs.
    """
    client, db = connect_to_mongodb()
    if db is None:
        sys.exit(1)

    try:
        jobs_col = db[DICE_JOBS_COLLECTION]

        print(f"\n--- Fetching Top {TOP_N} Jobs from '{DATABASE_NAME}.{DICE_JOBS_COLLECTION}' ---")
        
        # Find jobs that have the prediction score, sort by it descending, and limit the results
        top_jobs_cursor = jobs_col.find(
            {PREDICTION_FIELD_NAME: {"$exists": True}},
            {"title": 1, "company": 1, PREDICTION_FIELD_NAME: 1, "url": 1}
        ).sort(PREDICTION_FIELD_NAME, -1).limit(TOP_N)

        top_jobs = list(top_jobs_cursor)

        if not top_jobs:
            print("\nNo jobs with prediction scores found.")
            print("Please ensure 'predict_unrated_jobs.py' has been run successfully.")
            return

        print(f"\n--- Top {len(top_jobs)} Job Matches ---")
        for i, job in enumerate(top_jobs):
            score = job.get(PREDICTION_FIELD_NAME, 0.0)
            title = job.get('title', 'N/A')
            company = job.get('company', 'N/A')
            print(f"{i+1:>2}. Score: {score:<6.4f} | {title} @ {company}")

    finally:
        if client:
            client.close()
            print("\nMongoDB connection closed.")


if __name__ == "__main__":
    view_top_jobs()
