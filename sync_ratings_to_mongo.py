import firebase_admin
from firebase_admin import credentials, firestore
from pymongo import MongoClient
import logging
import os
from datetime import datetime
# Import the connection function from the new utility file
from mongodb_functions import connect_to_mongodb

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- FIRESTORE CONFIGURATION ---
# NOTE: Update this path to your actual service account key file location.
SERVICE_ACCOUNT_PATH = r'F:\AIJobFinder\aijobfinder-9dd90-firebase-adminsdk-fbsvc-084881796c.json'
APP_ID = 'local-skill-rater-id'
ROOT_COLLECTION = 'artifacts'

# Target Path Structure: /artifacts/{APP_ID}/public/data/skill_ratings/{PROFILE_DOCUMENT_ID}
PUBLIC_COLLECTION = "public"
DATA_COLLECTION = "data"
RATINGS_COLLECTION = "skill_ratings"

# The unique name of the profile document (e.g., 'Doug', 'Jane', etc.)
PROFILE_DOCUMENT_ID = "Doug" 

# FIX #1: The field name inside the 'Doug' document that holds the MAP (dictionary) of rated skills.
FIRESTORE_SKILL_MAP_FIELD = "ratings"


# 2. MONGODB DESTINATION CONFIG (The connection URI and DB name are now in mongodb_functions.py)
MONGO_COLLECTION_NAME = "skills_proficiency"
# -----------------------------------------------

def initialize_firestore():
    """Initializes the Firebase Admin SDK and returns the Firestore client."""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_PATH):
            logging.error(f"FATAL ERROR: Firebase Service Account JSON not found at: {SERVICE_ACCOUNT_PATH}")
            return None

        # Check if app is already initialized (important when running the script multiple times)
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred)
        
        logging.info("Firebase Admin SDK initialized successfully.")
        return firestore.client()
    except Exception as e:
        logging.error(f"Error initializing Firebase: {e}")
        return None

def sync_skill_ratings():
    """Fetches skill ratings from a single Firestore document and syncs them to MongoDB."""
    db_firestore = initialize_firestore()
    
    # FIX #2: Use the imported function. This returns the client and the database object (db_mongo).
    client_mongo, db_mongo = connect_to_mongodb()

    # Check for initialization/connection failure
    # We check client_mongo specifically because the Pymongo Collection object doesn't support bool()
    if db_firestore is None or client_mongo is None:
        logging.error("Database initialization or connection failed. Aborting sync.")
        return

    # Get the target collection using the returned database object
    collection_mongo = db_mongo[MONGO_COLLECTION_NAME]
    logging.info(f"Targeting MongoDB collection: '{MONGO_COLLECTION_NAME}'")


    # Build the document reference for the specific profile
    doc_ref = (
        db_firestore.collection(ROOT_COLLECTION)
        .document(APP_ID)
        .collection(PUBLIC_COLLECTION)
        .document(DATA_COLLECTION)
        .collection(RATINGS_COLLECTION)
        .document(PROFILE_DOCUMENT_ID)
    )

    ratings_path = f"/{ROOT_COLLECTION}/{APP_ID}/{PUBLIC_COLLECTION}/{DATA_COLLECTION}/{RATINGS_COLLECTION}/{PROFILE_DOCUMENT_ID}"
    logging.info(f"Attempting to fetch ratings from Firestore document: {ratings_path}")

    try:
        doc = doc_ref.get()

        if not doc.exists:
            logging.error(f"Firestore document not found at path: {ratings_path}")
            return

        data = doc.to_dict()
        if data is None:
             logging.error(f"Data retrieved from Firestore document is None. Path: {ratings_path}")
             return

        # Use the corrected field name: "ratings"
        rated_skills_map = data.get(FIRESTORE_SKILL_MAP_FIELD, {})

        if not rated_skills_map:
            logging.warning(f"No skill ratings found in the field '{FIRESTORE_SKILL_MAP_FIELD}' within document '{PROFILE_DOCUMENT_ID}'.")
            return

        count = 0
        # Iterate over the map's items() to get key (skill_name) and value (rating) directly
        for skill_name, rating in rated_skills_map.items():

            if skill_name and rating is not None:
                # 1. Define the unique identifier using both skill name and profile name (composite key)
                filter_query = {
                    "skill_name": skill_name,
                    "profile_name": PROFILE_DOCUMENT_ID 
                }

                # 2. Define the data to be set/updated
                update_data = {
                    "$set": {
                        "skill_name": skill_name,
                        "profile_name": PROFILE_DOCUMENT_ID,
                        "user_rating": rating, 
                        "last_synced": datetime.utcnow() 
                    }
                }

                # 3. Upsert: Insert if not found, update if found
                result = collection_mongo.update_one(
                    filter_query,
                    update_data,
                    upsert=True
                )

                if result.upserted_id:
                    logging.debug(f"Inserted new skill rating for: {skill_name} ({PROFILE_DOCUMENT_ID})")
                elif result.modified_count > 0:
                    logging.debug(f"Updated skill rating for: {skill_name} ({PROFILE_DOCUMENT_ID}) to {rating}")

                count += 1
            else:
                logging.warning(f"Skipping malformed skill object. Missing skill or rating for entry: {skill_name} -> {rating}.")

        logging.info(f"Sync complete! Successfully processed and synced {count} skill ratings for profile '{PROFILE_DOCUMENT_ID}'.")

    except Exception as e:
        logging.error(f"An unexpected error occurred during data synchronization: {e}")
    finally:
        if client_mongo:
            client_mongo.close()
            logging.info("MongoDB connection closed.")

if __name__ == "__main__":
    sync_skill_ratings()
