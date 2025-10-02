import firebase_admin
from firebase_admin import credentials, firestore
# Import the common MongoDB functions file
import mongodb_functions 
import os
from pymongo import errors

# --- FIREBASE CONFIGURATION ---
# IMPORTANT: This path is a raw string (r'...') to avoid Windows escape sequence issues.
SERVICE_ACCOUNT_PATH = r'F:\AIJobFinder\aijobfinder-9dd90-firebase-adminsdk-fbsvc-084881796c.json' 

# IMPORTANT: This MUST match the APP_ID in your SkillRater_Local_Runner.html
APP_ID = 'local-skill-rater-id'

# --- FIRESTORE PATH CONFIGURATION (FIXED) ---
# The path must alternate Collection / Document / Collection / Document...
# Target Path: /artifacts/{APP_ID}/public/all_skills
# This path matches your security rule: match /artifacts/{appId}/public/{document=**}

ROOT_COLLECTION = 'artifacts' # Collection 1
APP_DOCUMENT = APP_ID         # Document 1 (named after the app)
PUBLIC_COLLECTION = 'public'  # Collection 2 (public data pool)
SKILL_LIST_DOCUMENT = 'all_skills' # Document 2 (the actual list document)


def get_master_skills_from_mongo():
    """
    Connects to MongoDB, performs an aggregation on the main job collection to 
    count and sort skills, and returns the list of skill names.
    """
    client = None
    db = None
    
    try:
        # Connect to MongoDB using the shared function
        client, db = mongodb_functions.connect_to_mongodb()
        
        # Explicitly check against None as required by PyMongo
        if db is None:
            # Connection failed, error message already printed by connect_to_mongodb
            return []

        # Get the collection reference
        collection_name = mongodb_functions.COLLECTION_NAME 
        collection = db[collection_name]
        
        print(f"Successfully targeted collection '{collection_name}'.")

        # Check if the collection has any documents
        if collection.count_documents({}) == 0:
             print(f"ERROR: Job collection '{collection_name}' is empty. Run your scraper first.")
             return []

        # Aggregation pipeline to count and sort skills
        pipeline = [
            {'$match': {'skills': {'$exists': True, '$ne': []}}},
            {'$unwind': '$skills'},
            {'$group': {
                '_id': '$skills',
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}}
        ]

        # Execute the aggregation pipeline
        results = list(collection.aggregate(pipeline))
        
        # Extract just the skill names
        skill_list = [doc['_id'] for doc in results]
        
        print(f"Found {len(skill_list)} unique skills via aggregation.")
        return skill_list

    except Exception as e:
        print(f"An unexpected error occurred during MongoDB access/aggregation: {e}")
        return []
    finally:
        # Ensure the MongoDB connection is closed
        if client:
            client.close()


def upload_skills_to_firestore(skill_list):
    """
    Initializes Firebase Admin SDK and uploads the skill list to a public Firestore document.
    """
    try:
        # Initialize Firebase Admin SDK
        print(f"Initializing Firebase using service account...")
        
        if not os.path.exists(SERVICE_ACCOUNT_PATH):
             print(f"FATAL ERROR: Firebase Service Account JSON not found at: {SERVICE_ACCOUNT_PATH}")
             return

        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        # Initialize the app only if it hasn't been initialized already
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            
        db = firestore.client()
        
        # --- FIX: Explicitly build the document path using chained calls ---
        # Path: /artifacts/{APP_ID}/public/all_skills
        doc_ref = (
            db.collection(ROOT_COLLECTION)
            .document(APP_DOCUMENT)
            .collection(PUBLIC_COLLECTION)
            .document(SKILL_LIST_DOCUMENT)
        )
        # ------------------------------------------------------------------
        
        data = {
            'list': skill_list,
            'lastUpdated': firestore.SERVER_TIMESTAMP
        }
        
        print(f"Uploading {len(skill_list)} skills to Firestore path: /{ROOT_COLLECTION}/{APP_DOCUMENT}/{PUBLIC_COLLECTION}/{SKILL_LIST_DOCUMENT}")
        doc_ref.set(data)
        
        print("Upload successful!")

    except Exception as e:
        print(f"Error during Firebase operation: {e}")

if __name__ == '__main__':
    # 1. Get skills from MongoDB
    skills_to_upload = get_master_skills_from_mongo()

    if not skills_to_upload:
        print("No skills retrieved. Aborting upload.")
    else:
        # 2. Upload list to Firestore
        upload_skills_to_firestore(skills_to_upload)
