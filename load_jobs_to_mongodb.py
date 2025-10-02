import json
import os
from pymongo import MongoClient, errors

# --- MongoDB Configuration ---
# NOTE: You MUST replace the placeholder USERNAME and PASSWORD below 
# with the credentials you set up during your local MongoDB installation.
# The default local port is 27017.
# 
# IMPORTANT: If your password contains special characters like '@', ':', or '/', 
# you may need to URL-encode them.
MONGO_URI = "mongodb://localhost:27017/" 
# If you did NOT set up authentication (less common), you can try: "mongodb://localhost:27017/"
DATABASE_NAME = "JobMatchDB"
COLLECTION_NAME = "dice_jobs"
# -----------------------------

# File path from the scoring script
DICE_DATA_FILE = "dice_job_data.json"


def connect_to_mongodb(uri, db_name):
    """Establishes a connection to MongoDB and returns the database object."""
    try:
        # Connect to the MongoDB client
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Attempt to confirm connection by calling server_info()
        client.admin.command('ping')
        
        db = client[db_name]
        print(f"Successfully connected to MongoDB and database '{db_name}'.")
        return db
    except errors.ConnectionFailure as e:
        print(f"FATAL ERROR: Could not connect to MongoDB at {uri}. Please check your MONGO_URI and ensure the server is running.")
        print(f"Details: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during connection: {e}")
        return None


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
    # We will use insert_many() but first remove the MongoDB _id if it exists 
    # from a previous save (which it shouldn't in this case, but good practice).
    
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
        # Use bulk write operation to handle inserts efficiently.
        # This approach is simple but doesn't handle updates. For this initial load, 
        # we assume it's a fresh collection. If run again, it might fail on duplicates.
        
        # NOTE: A more complex `bulk_write` with `UpdateOne` would be needed to handle 
        # updates of existing documents based on 'url', but `insert_many` is simpler 
        # for a first-time migration.
        
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

    # 2. Connect to DB
    db = connect_to_mongodb(MONGO_URI, DATABASE_NAME)
    if db is None:
        return
    
    # 3. Insert/Update data
    bulk_insert_jobs(db, jobs_data, COLLECTION_NAME)

    print("\nMongoDB data migration complete.")


if __name__ == '__main__':
    main()