import os
from pymongo import MongoClient, errors

# --- MongoDB Configuration ---
# NOTE: Replace the placeholder USERNAME and PASSWORD 
# with the credentials you set up during your local MongoDB installation.
# This file is the central hub for your MongoDB connection settings.
MONGO_URI = "mongodb://localhost:27017/" 
DATABASE_NAME = "JobMatchDB"
COLLECTION_NAME = "dice_jobs"
# -----------------------------

def connect_to_mongodb():
    """
    Establishes a connection to MongoDB using predefined constants from this file.
    Returns the database object or None on failure.
    """
    try:
        # Connect to the MongoDB client
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Attempt to confirm connection by calling server_info()
        client.admin.command('ping')
        
        db = client[DATABASE_NAME]
        print(f"Successfully connected to MongoDB and database '{DATABASE_NAME}'.")
        return db
    except errors.ConnectionFailure as e:
        print(f"FATAL ERROR: Could not connect to MongoDB at {MONGO_URI}. Please check your MONGO_URI and ensure the server is running.")
        print(f"Details: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during connection: {e}")
        return None
