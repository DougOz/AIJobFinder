import json
import csv
import os

# Define the input and output file names
INPUT_JSON_FILE = "dice_job_data.json"
OUTPUT_CSV_FILE = "scored_jobs_summary_v2.csv"

# Define the field names for the scores (consistent with the scorer script)
SEMANTIC_SCORE_FIELD = 'semantic_score_v2'
SKILLS_SCORE_FIELD = 'skills_intersection_score'
OLD_SCORE_FIELD = 'resume_score'

# --- NEW COMBINED SCORE PARAMETERS ---
COMBINED_SCORE_FIELD = 'combined_score'
SEMANTIC_WEIGHT = 0.7  # Weighted 70%
SKILLS_WEIGHT = 0.3    # Weighted 30%


def export_data_to_csv(data_list):
    """
    Transforms the list of job dictionaries into a list of simplified rows,
    calculates the combined score, sorts them, and exports them to a CSV file.
    """
    if not data_list:
        print("No data found to export.")
        return

    # Define the fields for the CSV header
    csv_fields = [
        'job_title', 
        'url', 
        COMBINED_SCORE_FIELD,
        SEMANTIC_SCORE_FIELD, 
        SKILLS_SCORE_FIELD, 
        OLD_SCORE_FIELD,
        'is_remote'
    ]
    
    output_rows = []

    for job in data_list:
        # Calculate 'is_remote' flag
        job_types = job.get('job_types', [])
        is_remote = any('Remote' in jt for jt in job_types)

        # Get the individual scores (defaulting to 0.0 if not found)
        sem_score = job.get(SEMANTIC_SCORE_FIELD, 0.0)
        skills_score = job.get(SKILLS_SCORE_FIELD, 0.0)
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
            OLD_SCORE_FIELD: old_score,
            COMBINED_SCORE_FIELD: combined_score,
            'is_remote': is_remote
        }
        output_rows.append(row)

    # Sort the list: prioritize the new combined score, then semantic score (descending)
    # This places the best overall matches at the top of the CSV.
    output_rows.sort(key=lambda x: (x[COMBINED_SCORE_FIELD], x[SEMANTIC_SCORE_FIELD]), reverse=True)

    print(f"Exporting {len(output_rows)} records to {OUTPUT_CSV_FILE}...")
    
    try:
        with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"Successfully exported data to {OUTPUT_CSV_FILE}")
    except Exception as e:
        print(f"An error occurred during CSV writing: {e}")


def main():
    """Reads JSON data and initiates the CSV export."""
    if not os.path.exists(INPUT_JSON_FILE):
        print(f"FATAL ERROR: Input file '{INPUT_JSON_FILE}' not found. Please run the scorer first.")
        return

    try:
        with open(INPUT_JSON_FILE, 'r', encoding='utf-8') as f:
            jobs_data = json.load(f)
        
        print(f"Loaded {len(jobs_data)} jobs from JSON.")
        export_data_to_csv(jobs_data)

    except json.JSONDecodeError:
        print(f"FATAL ERROR: Failed to decode JSON from {INPUT_JSON_FILE}. Check file integrity.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    main()
