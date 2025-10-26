"""
PHASE 4: BATCH PREDICTION
This script uses the trained model and pipeline to predict scores for all
jobs in the database that have not been manually rated.

This script:
1. Loads the pre-fitted feature engineering pipeline and the best trained model.
2. Connects to MongoDB to find all jobs without a manual rating.
3. Fetches the required raw data for these jobs.
4. Prepares the data in the same way as the training script.
5. Transforms the data using the pipeline.
6. Makes predictions using the best model (handles blended models).
7. Saves the predictions back to the 'dice_jobs' collection in a new field.

Required libraries:
- pandas
- numpy
- scikit-learn
- joblib
- pymongo
"""

import sys
import pandas as pd
import numpy as np
import joblib
from pymongo.operations import UpdateOne
from bson.objectid import ObjectId

# Import custom functions and constants
from mongodb_functions import connect_to_mongodb, DATABASE_NAME
# This import is crucial! It makes the custom transformer classes available to joblib.
from custom_transformers import TitleRatingTransformer, SkillFeaturesTransformer, SemanticHighlightScorer, SemanticScoreV2Transformer, PrecomputedHighlightTransformer

# --- CONFIGURATION ---
DICE_JOBS_COLLECTION = "dice_jobs"
JOB_RATINGS_COLLECTION = "job_ratings"
TITLE_RATINGS_COLLECTION = "title_ratings"
SKILLS_PROFICIENCY_COLLECTION = "skills_proficiency"

PIPELINE_FILE = "job_rating_pipeline.joblib"
BEST_MODEL_FILE = "best_model.joblib"
PREDICTION_FIELD_NAME = "model1_prediction"
# --- END CONFIGURATION ---

def load_prediction_assets():
    """Loads the fitted pipeline and the best model from disk."""
    print("Loading prediction assets...")
    try:
        pipeline = joblib.load(PIPELINE_FILE)
        model = joblib.load(BEST_MODEL_FILE)
        print(f"  > Loaded pipeline from: {PIPELINE_FILE}")
        print(f"  > Loaded model from: {BEST_MODEL_FILE}")
        return pipeline, model
    except FileNotFoundError as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"Error: Could not find asset file '{e.filename}'.")
        print("Please ensure 'feature_engineering.py' and 'model_training.py' were run successfully first.")
        sys.exit(1)

def get_unrated_jobs_data(db):
    """
    Fetches and prepares data for all jobs that have not been manually rated.
    This mirrors the data preparation logic from feature_engineering.py.
    """
    print("\nFetching data for unrated jobs...")

    # 1. Get IDs of all manually rated jobs to exclude them
    rated_job_ids_cursor = db[JOB_RATINGS_COLLECTION].find({}, {"job_id": 1})
    rated_job_ids = {ObjectId(doc['job_id']) for doc in rated_job_ids_cursor if 'job_id' in doc}
    print(f"Found {len(rated_job_ids)} manually rated jobs to exclude.")

    # 2. Load lookups for skills and titles
    skill_ratings = {doc['skill_name'].lower(): doc['user_rating'] for doc in db[SKILLS_PROFICIENCY_COLLECTION].find({}, {"skill_name": 1, "user_rating": 1})}
    title_ratings = {doc['title'].lower(): doc['rating'] for doc in db[TITLE_RATINGS_COLLECTION].find({}, {"title": 1, "rating": 1})}
    print(f"Loaded {len(skill_ratings)} skill proficiencies and {len(title_ratings)} title ratings for feature creation.")

    # 3. Find all jobs that are NOT in the rated set
    unrated_jobs_cursor = db[DICE_JOBS_COLLECTION].find(
        {"_id": {"$nin": list(rated_job_ids)}},
        {
            "description": 1, 
            "skills": 1, 
            "title": 1, 
            "semantic_score_v2": 1,
            "semantic_max_liked": 1,
            "semantic_mean_liked": 1,
            "semantic_max_disliked": 1,
            "semantic_mean_disliked": 1
        }
    )

    prediction_data = []
    unrated_job_ids_for_update = []

    for job_doc in unrated_jobs_cursor:
        # Store the original _id for the final update step
        unrated_job_ids_for_update.append(job_doc['_id'])

        # --- Assemble features exactly as in feature_engineering.py ---
        job_title = job_doc.get('title')
        job_title_rating = title_ratings.get(job_title.lower()) if job_title else None

        job_skills_list = job_doc.get('skills', [])
        assembled_skills = []
        if isinstance(job_skills_list, list):
            for skill_name in job_skills_list:
                assembled_skills.append({
                    "skill": skill_name,
                    "rating": skill_ratings.get(skill_name.lower())
                })

        prediction_data.append({
            "job_description": job_doc.get('description', ''),
            "title_rating": job_title_rating,
            "skills": assembled_skills,
            "semantic_score_v2": job_doc.get('semantic_score_v2'),
            "semantic_max_liked": job_doc.get('semantic_max_liked'),
            "semantic_mean_liked": job_doc.get('semantic_mean_liked'),
            "semantic_max_disliked": job_doc.get('semantic_max_disliked'),
            "semantic_mean_disliked": job_doc.get('semantic_mean_disliked')
        })

    if not prediction_data:
        print("No unrated jobs found to predict.")
        return None, None

    print(f"Prepared {len(prediction_data)} unrated jobs for scoring.")
    return pd.DataFrame(prediction_data), unrated_job_ids_for_update

def main():
    """
    Main function to run the batch prediction pipeline.
    """
    # 1. Load assets
    pipeline, model = load_prediction_assets()

    # 2. Connect to DB and get data
    client, db = connect_to_mongodb()
    if db is None:
        sys.exit(1)

    try:
        unrated_df, job_ids_to_update = get_unrated_jobs_data(db)

        if unrated_df is None:
            return

        # 3. Transform the data using the loaded pipeline
        print("\nTransforming data using the feature engineering pipeline...")
        X_unrated = pipeline.transform(unrated_df)
        print(f"  > Data transformed into feature matrix of shape: {X_unrated.shape}")

        # 4. Make predictions
        print("\nMaking predictions with the best model...")
        
        # Check if the model is a blended model (dictionary) or a single estimator
        if isinstance(model, dict) and 'lgbm_model' in model:
            print("  > Blended model detected. Predicting with both components.")
            lgbm_preds = model['lgbm_model'].predict(X_unrated)
            ridge_preds = model['ridge_model'].predict(X_unrated)
            
            weights = model['weights']
            predictions = (lgbm_preds * weights['lgbm']) + (ridge_preds * weights['ridge'])
        else:
            print("  > Single model detected.")
            predictions = model.predict(X_unrated)
        
        print(f"  > Generated {len(predictions)} predictions.")

        # 5. Save predictions back to MongoDB
        print("\nSaving predictions to MongoDB...")
        
        bulk_operations = []
        for job_id, score in zip(job_ids_to_update, predictions):
            bulk_operations.append(
                UpdateOne(
                    {"_id": job_id},
                    {"$set": {PREDICTION_FIELD_NAME: float(score)}}
                )
            )

        if bulk_operations:
            batch_size = 500
            total_modified = 0
            for i in range(0, len(bulk_operations), batch_size):
                batch = bulk_operations[i:i + batch_size]
                result = db[DICE_JOBS_COLLECTION].bulk_write(batch)
                modified_count = result.modified_count
                total_modified += modified_count
                print(f"  > Wrote batch {i//batch_size + 1}. Updated {modified_count} documents.")
            print(f"\nTotal jobs updated with predictions: {total_modified}")
        else:
            print("  > No predictions to save.")

        print("\n--- Batch Prediction Complete! ---")

    finally:
        if client:
            client.close()
            print("\nMongoDB connection closed.")


if __name__ == "__main__":
    main()
