"""
This script connects to a MongoDB database, fetches all job ratings,
and performs a stratified split based on the 'rating' field.
It then updates each document with a 'data_set' field indicating
whether it belongs to the training, validation, or test set.

Required libraries:
- pymongo: pip install pymongo
- pandas: pip install pandas
- scikit-learn: pip install scikit-learn
- mongodb_functions (your custom module)
"""

import pandas as pd
from sklearn.model_selection import train_test_split
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

# --- CONFIGURATION ---
COLLECTION_NAME = "job_ratings"
# --- END CONFIGURATION ---

def split_and_update_data():
    """
    Connects to MongoDB, performs a stratified split, and updates documents.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("FATAL ERROR: Failed to connect to MongoDB. Exiting.")
        return

    try:
        # 1. Connect to MongoDB
        print(f"Connecting to MongoDB...")

        collection = db[COLLECTION_NAME]
        
        # Test connection
        client.admin.command('ping')
        print("MongoDB connection successful.")

        # 2. Fetch all job ratings (only _id and overall_score are needed for the split)
        # The first {} is the query (empty = all documents)
        # The second {} is the projection (only return _id and overall_score)
        print(f"Fetching job ratings from '{COLLECTION_NAME}' collection...")
        # MODIFICATION: Filter out documents with overall_score of 0 (or less) and use 'overall_score'
        cursor = collection.find({"overall_score": {"$gt": 0}}, {"_id": 1, "overall_score": 1})
        jobs_list = list(cursor)
        
        if not jobs_list:
            print("Error: No documents found in the collection. Aborting.")
            return

        print(f"Found {len(jobs_list)} total job ratings (ignoring scores of 0).")
        
        # 3. Load data into a pandas DataFrame
        df = pd.DataFrame.from_records(jobs_list)

        # Check for missing ratings, though this shouldn't be an issue
        if df['overall_score'].isnull().any():
            print("Warning: Some documents are missing an 'overall_score'. These will be ignored by stratification.")
            # Handle as needed, e.g., drop them for splitting
            df = df.dropna(subset=['overall_score'])

        # 4. Perform the stratified split (as per the plan)
        print("Performing stratified split...")
        
        # 'X' will be our document IDs, 'y' is the 'overall_score' we stratify on
        X = df['_id']
        y = df['overall_score']

        # 1. Split into training (250) and a temporary set (150)
        # 250 / 400 = 0.625 (so 1.0 - 0.625 = 0.375 for test_size)
        # The 'stratify=y' parameter ensures that each rating (1-8)
        # is split according to this percentage.
        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, 
            test_size=0.375, 
            random_state=42,  # For reproducibility
            stratify=y
        )

        # 2. Split the temporary set (150) into validation (75) and test (75)
        # 75 / 150 = 0.5
        # Stratify again to maintain the distribution in the new sets.
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, 
            test_size=0.5, 
            random_state=42,  # For reproducibility
            stratify=y_temp
        )

        # 5. Get the lists of MongoDB _id values
        train_ids = X_train.tolist()
        val_ids = X_val.tolist()
        test_ids = X_test.tolist()

        print("\nSplit complete:")
        print(f"  Training set size:   {len(train_ids)}")
        print(f"  Validation set size: {len(val_ids)}")
        print(f"  Test set size:       {len(test_ids)}")

        # 6. Update the documents in MongoDB
        print("\nUpdating documents in MongoDB with 'data_set' field...")

        # Update training documents
        result_train = collection.update_many(
            {"_id": {"$in": train_ids}},
            {"$set": {"data_set": "training"}}
        )
        print(f"  Updated {result_train.modified_count} documents to 'training'.")

        # Update validation documents
        result_val = collection.update_many(
            {"_id": {"$in": val_ids}},
            {"$set": {"data_set": "validation"}}
        )
        print(f"  Updated {result_val.modified_count} documents to 'validation'.")

        # Update test documents
        result_test = collection.update_many(
            {"_id": {"$in": test_ids}},
            {"$set": {"data_set": "test"}}
        )
        print(f"  Updated {result_test.modified_count} documents to 'test'.")

        print("\n--- Process Finished Successfully! ---")

    except ConnectionFailure:
        print("\n--- ERROR ---")
        print("Failed to connect to MongoDB. Please check your MONGO_CONNECTION_STRING.")
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
    split_and_update_data()
