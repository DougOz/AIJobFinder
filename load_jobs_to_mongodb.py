import json
import os
# Import necessary components from the new functions file
from pymongo import errors
from mongodb_functions import connect_to_mongodb, COLLECTION_NAME

# File path from the scoring script
DICE_DATA_FILE = "dice_job_data.json"


def load_data_from_json(filepath):
    """Loads the job data from the local JSON file."""
    if not os.path.exists(filepath):
        print(f"FATAL ERROR: Input file '{filepath}' not found.")
        return []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} job records from JSON file.")
        return data
    except json.JSONDecodeError as e:
        print(f"FATAL ERROR: Failed to decode JSON from {filepath}. Check file integrity.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while loading JSON data: {e}")
        return []


def bulk_insert_jobs(db, job_data, collection_name):
    """
    Inserts or updates job documents into the specified MongoDB collection.
    It uses the job 'url' as a unique identifier to prevent duplicate entries.
    """
    collection = db[collection_name]
    
    # Create an index on the 'url' field for quick lookups and uniqueness
    collection.create_index("url", unique=True)
    
    # Prepare documents for bulk operation
    documents_to_insert = []
    
    # MongoDB typically expects '_id' and 'url' is the unique field for upserts.
    
    for job in job_data:
        # Ensure job has a 'url' to be used as a key
        if job.get('url'):
            # The job document is already in the ideal document structure
            documents_to_insert.append(job)

    if not documents_to_insert:
        print("No valid documents found for insertion.")
        return

    print(f"Attempting to insert/update {len(documents_to_insert)} documents...")

    try:
        # Use insert_many() for bulk operation
        result = collection.insert_many(documents_to_insert, ordered=False) 
        print(f"Successfully inserted {len(result.inserted_ids)} new documents.")
        
    except errors.BulkWriteError as bwe:
        # This often happens when re-running and 'url' index prevents duplicates
        inserted_count = len(bwe.details.get('nInserted', 0))
        write_errors = len(bwe.details.get('writeErrors', []))
        print(f"Bulk insert completed with errors (likely duplicates):")
        print(f" -> Inserted documents: {inserted_count}")
        print(f" -> Documents skipped (duplicates): {write_errors}")
    except Exception as e:
        print(f"An unexpected error occurred during bulk insertion: {e}")


def main():
    """Coordinates the loading of data from JSON to MongoDB."""
    
    # 1. Load data
    jobs_data = load_data_from_json(DICE_DATA_FILE)
    if not jobs_data:
        return

    # 2. Connect to DB (Uses connect_to_mongodb imported from mongodb_functions)
    client, db = connect_to_mongodb()
    if db is None:
        return
    
    # 3. Insert/Update data
    bulk_insert_jobs(db, jobs_data, COLLECTION_NAME)

    print("\nMongoDB data migration complete.")


if __name__ == '__main__':
    main()
