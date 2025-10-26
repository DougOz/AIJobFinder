"""
A script to train a model on existing rated job titles and predict ratings
for all remaining unrated titles.

This script:
1. Connects to MongoDB.
2. Loads all human-rated titles from the 'title_ratings' collection.
3. Trains and evaluates multiple text classification models to find the best one.
4. Evaluates the model's accuracy on a held-out test set.
5. Finds all unrated titles in the 'dice_jobs' collection.
6. Predicts ratings for these unrated titles using the best-performing model.
7. Saves the new, predicted ratings back to the 'title_ratings' collection
   with a 'source' field to distinguish them from human ratings.
"""

import sys
import pandas as pd
from pymongo.operations import UpdateOne
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

# Scikit-learn imports
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, f1_score

# --- CONFIGURATION ---
DICE_JOBS_COLLECTION = "dice_jobs"
TITLE_RATINGS_COLLECTION = "title_ratings"
RANDOM_STATE = 42
# --- END CONFIGURATION ---

def get_unrated_titles(db, rated_titles_set):
    """
    Finds all job titles in the jobs collection that do not have a rating.
    """
    print("\nFinding all unrated job titles...")
    pipeline = [
        {
            "$project": {
                "lower_title": {"$toLower": "$title"}
            }
        },
        {
            "$match": {
                "lower_title": {"$nin": list(rated_titles_set)}
            }
        },
        {
            "$group": {
                "_id": "$lower_title"
            }
        }
    ]
    cursor = db[DICE_JOBS_COLLECTION].aggregate(pipeline)
    unrated_titles = [doc['_id'] for doc in cursor if doc['_id']]
    print(f"Found {len(unrated_titles)} unique unrated titles to predict.")
    return unrated_titles

def main():
    """
    Main function to run the title rating prediction.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("FATAL: Could not connect to MongoDB. Exiting.", file=sys.stderr)
        sys.exit(1)

    try:
        # 1. Load human-rated titles for training
        print("Loading human-rated titles for training...")
        ratings_col = db[TITLE_RATINGS_COLLECTION]
        
        # --- NEW: Clear all previously predicted ratings to ensure a fresh run ---
        print("\nClearing all previously predicted title ratings...")
        delete_result = ratings_col.delete_many({"source": "predicted"})
        print(f"  > Removed {delete_result.deleted_count} old predicted ratings.")
        # --- END NEW ---
        
        # We only want to train on human-rated data
        query = {"source": {"$ne": "predicted"}}
        rated_docs = list(ratings_col.find(query, {"title": 1, "rating": 1}))
        
        if len(rated_docs) < 50:
            print(f"FATAL: Not enough rated titles ({len(rated_docs)}) to train a model. Please rate more titles first.")
            return
            
        rated_df = pd.DataFrame(rated_docs)
        print(f"Loaded {len(rated_df)} human-rated titles.")

        # 2. Prepare data and split for evaluation
        X = rated_df['title']
        y = rated_df['rating']
        
        # Stratify ensures the class distribution is the same in train and test sets
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
        )

        # 3. Define classifiers to test
        # We use class_weight='balanced' to combat the low recall for class 3
        # Let's try a manual weight to find a balance between precision and recall.
        # This makes mistakes on class '3' 1.5x more costly than on class '2'.
        tuned_class_weight = {1: 2, 2: 1, 3: 2}

        classifiers = {
            "Logistic Regression": LogisticRegression(
                random_state=RANDOM_STATE, class_weight=tuned_class_weight
            ),
            "Random Forest": RandomForestClassifier(
                random_state=RANDOM_STATE, n_estimators=150, class_weight=tuned_class_weight
            )
        }

        best_model_pipeline = None
        best_model_name = ""
        best_f1_score = -1

        # 4. Train and evaluate each classifier
        print("\n--- Training and Evaluating Title Classification Models ---")
        for name, clf in classifiers.items():
            print(f"\n--- Testing Model: {name} ---")
            pipeline = Pipeline([
                ('tfidf', TfidfVectorizer(ngram_range=(1, 3), stop_words='english', min_df=2)),
                ('clf', clf)
            ])
            
            pipeline.fit(X_train, y_train)
            y_pred = pipeline.predict(X_test)
            
            print(classification_report(y_test, y_pred))
            
            # Check if this is the best model based on macro avg f1-score
            current_f1 = f1_score(y_test, y_pred, average='macro')
            if current_f1 > best_f1_score:
                best_f1_score = current_f1
                best_model_pipeline = pipeline
                best_model_name = name

        print("\n--- Model Selection ---")
        print(f"Best model selected: '{best_model_name}' (Macro Avg F1-Score: {best_f1_score:.4f})")

        # 5. Get all unrated titles
        # Create a set of ALL known titles (human-rated AND predicted) for efficient lookup
        print("\nFetching all existing title ratings (human & predicted) for exclusion...")
        all_rated_titles_set = {doc['title'].lower() for doc in ratings_col.find({}, {"title": 1})}
        unrated_titles_list = get_unrated_titles(db, all_rated_titles_set)

        if not unrated_titles_list:
            print("\nExcellent! No unrated titles found.")
            return

        # 6. Predict ratings for the unrated titles using the best model
        print(f"\nPredicting ratings for {len(unrated_titles_list)} titles using '{best_model_name}'...")
        predicted_ratings = best_model_pipeline.predict(unrated_titles_list)

        # 7. Prepare and save the new ratings to MongoDB
        print("Saving new predicted ratings to MongoDB...")
        
        bulk_operations = []
        for title, rating in zip(unrated_titles_list, predicted_ratings):
            bulk_operations.append(
                UpdateOne(
                    {'title': title},
                    {'$set': {
                        'rating': int(rating),
                        'source': 'predicted' # Mark as machine-generated
                    }},
                    upsert=True
                )
            )
        
        if bulk_operations:
            # Process in batches to avoid overwhelming the server
            batch_size = 500
            total_written = 0
            for i in range(0, len(bulk_operations), batch_size):
                batch = bulk_operations[i:i + batch_size]
                result = ratings_col.bulk_write(batch)
                written_count = result.upserted_count + result.modified_count
                total_written += written_count
                print(f"  > Wrote batch {i//batch_size + 1}. Added/updated {written_count} ratings.")
            print(f"\nTotal predicted ratings saved: {total_written}")
        else:
            print("  > No new ratings to save.")

        print("\n--- Title Rating Prediction Complete! ---")

    finally:
        if client:
            client.close()
            print("\nMongoDB connection closed.")


if __name__ == "__main__":
    main()
