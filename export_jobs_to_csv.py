import csv
import os

# Import MongoDB functions and constants
from mongodb_functions import connect_to_mongodb, COLLECTION_NAME
# Import the newly extracted utility function
from file_utilities import get_unique_filename 

# Define the base output file name
BASE_OUTPUT_CSV_FILE = "scored_jobs_summary_v2.csv"
# The actual file name will be determined dynamically in main()

# Define the field names for the scores (consistent with the scorer script)
SEMANTIC_SCORE_FIELD = 'semantic_score_v2'
SKILLS_SCORE_FIELD = 'skills_intersection_score'
MATCHED_SKILLS_COUNT_FIELD = 'matched_skills_count'
OLD_SCORE_FIELD = 'resume_score' # Keeping for reference/backward compatibility check only

# --- NEW COMBINED SCORE PARAMETERS ---
COMBINED_SCORE_FIELD = 'combined_score'
SEMANTIC_WEIGHT = 0.7   # Weighted 70%
SKILLS_WEIGHT = 0.3     # Weighted 30%


def export_data_to_csv(data_list, output_csv_file):
    """
    Transforms the list of job dictionaries into a list of simplified rows,
    calculates the combined score, sorts them, and exports them to a CSV file.
    The output_csv_file is the dynamically generated unique filename.
    """
    if not data_list:
        print("No scored data found to export.")
        return

    # Define the fields for the CSV header, including the new matched skills count
    csv_fields = [
        'job_title', 
        'url', 
        COMBINED_SCORE_FIELD,
        SEMANTIC_SCORE_FIELD, 
        SKILLS_SCORE_FIELD, 
        MATCHED_SKILLS_COUNT_FIELD, # New field included
        'is_remote',
        'job_types' # Added job_types for completeness
    ]
    
    output_rows = []

    for job in data_list:
        # Calculate 'is_remote' flag and get job types
        job_types = job.get('job_types', [])
        is_remote = any('Remote' in jt for jt in job_types)

        # Get the individual scores (defaulting to 0.0 if not found)
        sem_score = job.get(SEMANTIC_SCORE_FIELD, 0.0)
        skills_score = job.get(SKILLS_SCORE_FIELD, 0.0)
        match_count = job.get(MATCHED_SKILLS_COUNT_FIELD, 0)
        
        # NOTE: OLD_SCORE_FIELD is no longer calculated but kept for historical context if it exists.
        old_score = job.get(OLD_SCORE_FIELD, 0.0) 

        # Calculate the new combined score
        combined_score = round(
            (sem_score * SEMANTIC_WEIGHT) + (skills_score * SKILLS_WEIGHT), 
            4
        )

        # Create a simplified dictionary for the CSV row
        row = {
            'job_title': job.get('title', 'N/A'),
            'url': job.get('url', 'N/A'),
            SEMANTIC_SCORE_FIELD: sem_score,
            SKILLS_SCORE_FIELD: skills_score,
            MATCHED_SKILLS_COUNT_FIELD: match_count,
            COMBINED_SCORE_FIELD: combined_score,
            'is_remote': is_remote,
            'job_types': ", ".join(job_types)
        }
        output_rows.append(row)

    # Sort the list: prioritize the new combined score, then semantic score (descending)
    # This places the best overall matches at the top of the CSV.
    output_rows.sort(key=lambda x: (x[COMBINED_SCORE_FIELD], x[SEMANTIC_SCORE_FIELD]), reverse=True)

    print(f"Exporting {len(output_rows)} records to {output_csv_file}...")
    
    try:
        with open(output_csv_file, 'w', newline='', encoding='utf-8') as csvfile:
            # Use DictWriter to easily map dictionary keys to field names
            writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"Successfully exported data to {output_csv_file}")
    except Exception as e:
        print(f"An error occurred during CSV writing: {e}")


def main():
    """Connects to MongoDB, retrieves scored data, and initiates the CSV export."""
    
    # Check for unique filename first, using the imported utility function
    unique_output_filename = get_unique_filename(BASE_OUTPUT_CSV_FILE)

    print("--- Connecting to MongoDB ---")
    client, db = connect_to_mongodb()
    if db is None:
        print("FATAL ERROR: Failed to connect to MongoDB. Exiting.")
        return

    job_collection = db[COLLECTION_NAME]
    
    print(f"--- Loading job data from MongoDB collection: {COLLECTION_NAME} ---")
    try:
        # Only fetch documents that have been scored (i.e., contain the semantic score field)
        query = {SEMANTIC_SCORE_FIELD: {'$exists': True}}
        # Fetch all fields except the internal MongoDB '_id'
        jobs_data = list(job_collection.find(query, {'_id': 0})) 
        print(f"Loaded {len(jobs_data)} scored jobs from MongoDB.")
    except Exception as e:
        print(f"An unexpected error occurred while loading job data from MongoDB: {e}")
        return

    if not jobs_data:
        print("No scored job data found to process. Exiting.")
        return

    export_data_to_csv(jobs_data, unique_output_filename) # Pass the unique filename

if __name__ == '__main__':
    main()
