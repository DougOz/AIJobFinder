"""
This script connects to a MongoDB database, finds all job ratings
in the 'training' set, and processes their 'highlights' field.

It aggregates these highlights into a new 'training_highlights'
collection, maintaing a count for each unique highlight
(based on its text and type).

Required libraries:
- pymongo: pip install pymongo
- mongodb_functions (your custom module)
"""

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, BulkWriteError
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

# --- CONFIGURATION ---
JOB_RATINGS_COLLECTION = "job_ratings"
HIGHLIGHTS_COLLECTION = "training_highlights"
# --- END CONFIGURATION ---

def extract_and_aggregate_highlights():
    """
    Connects to MongoDB, processes highlights from the training set,
    and aggregates them into a new collection.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("FATAL ERROR: Failed to connect to MongoDB. Exiting.")
        return

    try:
        # 1. Get collections
        source_col = db[JOB_RATINGS_COLLECTION]
        target_col = db[HIGHLIGHTS_COLLECTION]

        print(f"Connected to MongoDB. Using DB: '{DATABASE_NAME}'")
        
        # 2. Create a unique index on the target collection
        # This ensures we don't have duplicate entries and speeds up upserts.
        try:
            target_col.create_index([("text", 1), ("type", 1)], unique=True)
            print(f"Ensured unique index exists on '{HIGHLIGHTS_COLLECTION}'.")
        except OperationFailure as e:
            print(f"Warning: Could not create index (it might already exist in a different form): {e}")


        # 3. Find all documents in the training set that have highlights
        print(f"Finding training jobs with highlights in '{JOB_RATINGS_COLLECTION}'...")
        query = {
            "data_set": "training",
            "highlights": {"$exists": True, "$not": {"$size": 0}}
        }
        projection = {"highlights": 1} # Only fetch the highlights field
        
        cursor = source_col.find(query, projection)
        
        jobs_with_highlights = list(cursor)
        job_count = len(jobs_with_highlights)

        if job_count == 0:
            print("No documents found in the 'training' set with highlights. Exiting.")
            return

        print(f"Found {job_count} training jobs with highlights to process.")
        
        # 4. Process highlights and upsert into the aggregate collection
        processed_count = 0
        
        # Using bulk_write for much greater efficiency than one update at a time
        from pymongo import UpdateOne
        bulk_operations = []

        for doc in jobs_with_highlights:
            for highlight in doc.get('highlights', []):
                # Ensure highlight has text and type
                if 'text' in highlight and 'type' in highlight:
                    # Normalize text: remove leading/trailing whitespace and lowercase
                    # This prevents "Python " and "python" from being two entries
                    normalized_text = highlight['text'].strip().lower()
                    
                    if normalized_text: # Ignore empty highlights
                        bulk_operations.append(
                            UpdateOne(
                                {"text": normalized_text, "type": highlight['type']},
                                {"$inc": {"count": 1}},
                                upsert=True
                            )
                        )
                        processed_count += 1

        if not bulk_operations:
            print("No valid highlights found to process. Exiting.")
            return

        print(f"Aggregated {processed_count} total highlight instances. Writing to DB...")

        # 5. Execute the bulk write
        try:
            result = target_col.bulk_write(bulk_operations, ordered=False)
            print("\n--- Bulk Write Summary ---")
            print(f"  Documents created (upserted): {result.upserted_count}")
            print(f"  Documents modified (incremented): {result.modified_count}")
            
            unique_highlights = target_col.count_documents({})
            print(f"\nTotal unique highlights in collection: {unique_highlights}")

        except BulkWriteError as bwe:
            print("\n--- ERROR DURING BULK WRITE ---")
            print(f"  {len(bwe.details.get('writeErrors', []))} errors occurred.")
            # This can happen if two concurrent operations try to create the same doc
            # In our case, it's not critical, but good to know.
            print(f"Partial results: {bwe.details}")


        print("\n--- Process Finished Successfully! ---")

    except ConnectionFailure:
        print("\n--- ERROR ---")
        print("Failed to connect to MongoDB.")
    except OperationFailure as e:
        print(f"\n--- ERROR ---")
        print(f"An error occurred during a database operation: {e}")
    except Exception as e:
        print(f"\n--- AN UNEXPECTED ERROR OCCURRED ---")
        print(f"{e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed.")

if __name__ == "__main__":
    extract_and_aggregate_highlights()
