import os
from pymongo import MongoClient, errors

# --- MongoDB Configuration ---
# All scripts connecting to MongoDB should import these constants.
MONGO_URI = "mongodb://localhost:27017/" 
DATABASE_NAME = "JobMatchDB"
COLLECTION_NAME = "dice_jobs"
# -----------------------------

def connect_to_mongodb():
    """
    Establishes a connection to MongoDB using predefined constants.
    
    Returns:
        tuple: (MongoClient, Database) objects, or (None, None) on failure.
    """
    client = None
    try:
        # Connect to the MongoDB client
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Attempt to confirm connection by calling server_info()
        client.admin.command('ping')
        
        db = client[DATABASE_NAME]
        print(f"Successfully connected to MongoDB and database '{DATABASE_NAME}'.")
        # We return the client so it can be closed in the calling function's finally block
        return client, db
    except errors.ConnectionFailure:
        print(f"FATAL ERROR: Could not connect to MongoDB at {MONGO_URI}. Is the server running?")
        if client:
            client.close()
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred during connection: {e}")
        if client:
            client.close()
        return None, None
