"""
PHASE 1: FEATURE ENGINEERING
This script loads raw data from multiple MongoDB collections, processes it
according to the 'ml_modeling_plan.md', and saves the final feature matrices 
and the fitted transformation pipeline.

This version fetches:
- Base ratings from 'job_ratings'
- Description, skills, and title from 'dice_jobs'
- Skill ratings from 'skills_proficiency'
- Title ratings from 'title_ratings'
- Highlights from 'training_highlights'

Required libraries:
- pandas
- numpy
- scikit-learn
- joblib
- pymongo (for mongodb_functions)
- scipy (for saving sparse matrices)
- sentence-transformers (for semantic matching)
- torch

Install:
pip install pandas numpy scikit-learn joblib pymongo scipy sentence-transformers torch
"""

import pandas as pd
import numpy as np
import joblib
from scipy.sparse import save_npz, hstack, csr_matrix
from pymongo import MongoClient
from mongodb_functions import connect_to_mongodb, DATABASE_NAME
from bson.objectid import ObjectId # <-- Import ObjectId
from bson.errors import InvalidId

# sklearn imports
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer

# --- Custom Transformers ---
# Import our custom classes from their own file
from custom_transformers import TitleRatingTransformer, SkillFeaturesTransformer, SemanticScoreV2Transformer, PrecomputedSegmentScoresTransformer


# --- CONFIGURATION ---
JOB_RATINGS_COLLECTION = "job_ratings"
DICE_JOBS_COLLECTION = "dice_jobs"
SKILLS_PROFICIENCY_COLLECTION = "skills_proficiency"
TITLE_RATINGS_COLLECTION = "title_ratings"
HIGHLIGHTS_COLLECTION = "training_highlights"

# Output file names
PIPELINE_FILE = "job_rating_pipeline.joblib"
TRANSFORMER_LIST_FILE = "transformer_list.joblib" # <-- NEW
X_TRAIN_FILE = "X_train_transformed.npz"
X_VAL_FILE = "X_val_transformed.npz"
X_TEST_FILE = "X_test_transformed.npz"
Y_TRAIN_FILE = "y_train.npy"
Y_VAL_FILE = "y_val.npy"
Y_TEST_FILE = "y_test.npy"
# --- END CONFIGURATION ---

# --- ABLATION STUDY CONFIGURATION ---
# Set this to the name of the feature group you want to exclude, or None to run with all features.
# Options: 'title', 'skills', 'vi_tfidf', 'i_tfidf', 'other_tfidf', 'segment_scores'
EXCLUDE_GROUP_FOR_ABLATION = 'vi_tfidf'
# ------------------------------------


def load_data():
    """
    Loads data from all collections and assembles the final
    training, validation, and test DataFrames.
    """
    client, db = connect_to_mongodb()
    if db is None:
        raise ConnectionError("Failed to connect to MongoDB.")
    
    print("Loading data from MongoDB...")
    
    try:
        # 1. Access collections
        ratings_col = db[JOB_RATINGS_COLLECTION]
        jobs_col = db[DICE_JOBS_COLLECTION]
        skills_col = db[SKILLS_PROFICIENCY_COLLECTION]
        titles_col = db[TITLE_RATINGS_COLLECTION]
        highlights_col = db[HIGHLIGHTS_COLLECTION]

        # 2. Load lookups into memory (as dictionaries for speed)
        
        # Load highlights
        highlights_df = pd.DataFrame(list(highlights_col.find()))
        print(f"Loaded {len(highlights_df)} unique highlights.")
        
        # Load skill proficiencies
        # ASSUMPTION: 'skill_name' (str, lowercase) and 'rating' (int)
        skill_ratings = {}
        for doc in skills_col.find({}, {"skill_name": 1, "user_rating": 1}):
            if 'skill_name' in doc and 'user_rating' in doc:
                skill_ratings[doc['skill_name'].lower()] = doc['user_rating']
        print(f"Loaded {len(skill_ratings)} skill proficiency ratings.")
        
        # Load title ratings
        # ASSUMPTION: 'title' (str, lowercase) and 'rating' (int)
        title_ratings = {}
        for doc in titles_col.find({}, {"title": 1, "rating": 1}):
            if 'title' in doc and 'rating' in doc:
                title_ratings[doc['title'].lower()] = doc['rating']
        print(f"Loaded {len(title_ratings)} title ratings.")

        # 3. Load and merge job ratings with job descriptions
        print("Loading and merging all job data...")
        
        # Filter out 0-rated jobs
        query = {"overall_score": {"$gt": 0}}
        
        ratings_cursor = ratings_col.find(query)
        
        train_data = []
        val_data = []
        test_data = []
        
        orphaned_ratings = 0
        missing_skills_count = 0

        for rating_doc in ratings_cursor:
            # ASSUMPTION: 'job_id' field in 'job_ratings' links to '_id' in 'dice_jobs'
            job_id_str = rating_doc.get('job_id') 
            if not job_id_str:
                print(f"Warning: Rating doc {rating_doc['_id']} missing 'job_id'. Skipping.")
                orphaned_ratings += 1
                continue

            # --- FIX: Convert string 'job_id' to ObjectId ---
            try:
                job_object_id = ObjectId(job_id_str)
            except InvalidId:
                print(f"Warning: 'job_id' {job_id_str} is not a valid ObjectId. Skipping rating {rating_doc['_id']}.")
                invalid_job_id_count += 1
                continue
            # --- END FIX ---

            # Fetch the corresponding job data from 'dice_jobs'
            job_doc = jobs_col.find_one(
                {"_id": job_object_id}, # <-- Use the ObjectId here
                # --- V2: Fetch new segmented text and score fields ---
                {
                    "title": 1, "skills": 1, "description": 1,
                    "very_important_text": 1,
                    "important_text": 1,
                    "other_text": 1,
                    "very_important_scores": 1,
                    "important_scores": 1,
                    "other_scores": 1,
                }
            )
            
            if not job_doc:
                print(f"Warning: No job found in '{DICE_JOBS_COLLECTION}' for job_id {job_id}. Skipping rating {rating_doc['_id']}.")
                orphaned_ratings += 1
                continue
                
            # --- Assemble the Merged Document ---
            
            # 1. Get title and its rating
            job_title = job_doc.get('title')
            job_title_rating = None
            if job_title:
                job_title_rating = title_ratings.get(job_title.lower())
                
            # 2. Get skills and their ratings
            job_skills_list = job_doc.get('skills') # This is a list of strings
            assembled_skills = [] # This will be a list of objects
            
            if isinstance(job_skills_list, list):
                for skill_name in job_skills_list:
                    skill_rating = skill_ratings.get(skill_name.lower())
                    assembled_skills.append({
                        "skill": skill_name,
                        "rating": skill_rating # Will be None if not rated, which is correct
                    })
            else:
                missing_skills_count += 1
                
            # 3. Create the final document for the DataFrame
            merged_doc = {
                "_id": rating_doc['_id'],
                "overall_score": rating_doc['overall_score'],
                "data_set": rating_doc.get('data_set'),
                "title_rating": job_title_rating, # This is the rated value (or None)
                "skills": assembled_skills, # This is the new list of skill objects
                # --- V2: Add new fields to the DataFrame ---
                "very_important_text": job_doc.get('very_important_text'),
                "important_text": job_doc.get('important_text'),
                "other_text": job_doc.get('other_text', job_doc.get('description')), # Fallback
                "very_important_scores": job_doc.get('very_important_scores'),
                "important_scores": job_doc.get('important_scores'),
                "other_scores": job_doc.get('other_scores'),
            }

            # Append to the correct list
            data_set = merged_doc.get('data_set')
            if data_set == 'training':
                train_data.append(merged_doc)
            elif data_set == 'validation':
                val_data.append(merged_doc)
            elif data_set == 'test':
                test_data.append(merged_doc)
            # else: it's a job that wasn't split, we ignore it

        if orphaned_ratings > 0:
            print(f"Warning: {orphaned_ratings} ratings were skipped due to missing 'job_id' or no matching 'dice_jobs' doc.")
        if missing_skills_count > 0:
            print(f"Warning: {missing_skills_count} matched jobs had a missing or invalid 'skills' field.")

        # 4. Convert to DataFrames
        train_df = pd.DataFrame(train_data)
        val_df = pd.DataFrame(val_data)
        test_df = pd.DataFrame(test_data)
        
        print(f"Loaded {len(train_df)} training, {len(val_df)} validation, and {len(test_df)} test documents.")
        
        if train_df.empty:
            raise ValueError("No training data found. Check 'data_set' fields in 'job_ratings' and 'job_id' links.")
        
        return train_df, val_df, test_df, highlights_df

    finally:
        if client:
            client.close()
            print("MongoDB connection closed.")


# --- MAIN EXECUTION ---
def main():
    excluded_group = EXCLUDE_GROUP_FOR_ABLATION
    # 1. Load Data
    try:
        train_df, val_df, test_df, highlights_df = load_data()
    except (ConnectionError, ValueError) as e:
        print(f"FATAL ERROR: {e}")
        return

    # 2. Separate features (X) and target (y)
    target_column = 'overall_score'
    
    X_train = train_df.drop(columns=[target_column])
    y_train = train_df[target_column].astype(float)
    
    X_val = val_df.drop(columns=[target_column])
    y_val = val_df[target_column].astype(float)
    
    X_test = test_df.drop(columns=[target_column])
    y_test = test_df[target_column].astype(float)

    # 3. Define the full feature engineering pipeline
    print("Defining feature engineering pipeline...")

    # --- Define Preprocessing Steps ---
    
    # --- V2: Define TF-IDF Vectorizers for each text segment ---
    # We fill missing text with '' so the vectorizer can handle it.
    X_train['very_important_text'] = X_train['very_important_text'].fillna('')
    X_val['very_important_text'] = X_val['very_important_text'].fillna('')
    X_test['very_important_text'] = X_test['very_important_text'].fillna('')

    X_train['important_text'] = X_train['important_text'].fillna('')
    X_val['important_text'] = X_val['important_text'].fillna('')
    X_test['important_text'] = X_test['important_text'].fillna('')

    X_train['other_text'] = X_train['other_text'].fillna('')
    X_val['other_text'] = X_val['other_text'].fillna('')
    X_test['other_text'] = X_test['other_text'].fillna('')

    vi_tfidf = TfidfVectorizer(stop_words='english', max_features=2000, ngram_range=(1, 2))
    i_tfidf = TfidfVectorizer(stop_words='english', max_features=2000, ngram_range=(1, 2))
    other_tfidf = TfidfVectorizer(
        stop_words='english',
        max_features=3000, # Give 'other' text more features
        ngram_range=(1, 2)
    )
    
    # --- V2: Define the full preprocessor with new segmented features ---
    # Define the list of transformers to be used. We will save this list
    # so the training script can modify it for the ablation study.
    transformer_list = [
        # (name, transformer_object, columns_to_apply_to)
        ('title', TitleRatingTransformer(), ['title_rating']),
        ('skills', SkillFeaturesTransformer(), ['skills']),
        
        # TF-IDF features for each text segment
        ('vi_tfidf', vi_tfidf, 'very_important_text'),
        ('i_tfidf', i_tfidf, 'important_text'),
        ('other_tfidf', other_tfidf, 'other_text'),
        
        # Pre-computed semantic scores for each segment
        ('segment_scores', PrecomputedSegmentScoresTransformer(
            segment_columns=['very_important_scores', 'important_scores', 'other_scores'],
            score_keys=['max_liked', 'mean_liked', 'max_disliked', 'mean_disliked'],
            prefixes=['vi_', 'i_', 'o_']
        ), ['very_important_scores', 'important_scores', 'other_scores'])
    ]

    # --- NEW: Dynamically modify the transformer list for the ablation study ---
    if excluded_group:
        print(f"\n--- RUNNING ABLATION STUDY: EXCLUDING '{excluded_group}' ---")
        transformer_list = [t for t in transformer_list if t[0] != excluded_group]
    else:
        print("\n--- RUNNING FULL-FEATURE MODEL ---")
    # --- END NEW ---

    preprocessor = ColumnTransformer(
        transformers=transformer_list,
        remainder='drop',
        n_jobs=None, # Keep parallel processing off for stability
        # Force the output to be a sparse matrix, even if density > 0.3
        # This is the key to fixing the save_npz error.
        sparse_threshold=1.0
    )

    # Note: For now, the pipeline *is* the preprocessor.
    # Later, we can add a model to this pipeline.
    full_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor)
    ])

    # 4. Fit the pipeline on training data and transform all sets
    print("Fitting pipeline on training data...")
    X_train_transformed = full_pipeline.fit_transform(X_train, y_train)
    print("...Training data transformed.")

    print("Transforming validation data...")
    X_val_transformed = full_pipeline.transform(X_val)
    print("...Validation data transformed.")

    print("Transforming test data...")
    X_test_transformed = full_pipeline.transform(X_test)
    print("...Test data transformed.")

    print("\n--- Transformation Summary ---")
    print(f"Original training shape: {X_train.shape}")
    print(f"Transformed training shape: {X_train_transformed.shape}")
    print(f"Original validation shape: {X_val.shape}")
    print(f"Transformed validation shape: {X_val_transformed.shape}")

    # 5. Save the pipeline and the transformed data
    print("\nSaving pipeline and processed data to disk...")

    # Save the fitted pipeline
    joblib.dump(full_pipeline, PIPELINE_FILE)
    print(f"  > Fitted pipeline saved to: {PIPELINE_FILE}")

    # --- NEW: Save the list of transformers for the ablation study ---
    joblib.dump(transformer_list, TRANSFORMER_LIST_FILE)
    print(f"  > Transformer list saved to: {TRANSFORMER_LIST_FILE}")

    # Save the transformed sparse matrices
    save_npz(X_TRAIN_FILE, X_train_transformed)
    print(f"  > Transformed training features saved to: {X_TRAIN_FILE}")
    save_npz(X_VAL_FILE, X_val_transformed)
    print(f"  > Transformed validation features saved to: {X_VAL_FILE}")
    save_npz(X_TEST_FILE, X_test_transformed)
    print(f"  > Transformed test features saved to: {X_TEST_FILE}")

    # Save the target arrays
    np.save(Y_TRAIN_FILE, y_train.values)
    print(f"  > Training target saved to: {Y_TRAIN_FILE}")
    np.save(Y_VAL_FILE, y_val.values)
    print(f"  > Validation target saved to: {Y_VAL_FILE}")
    np.save(Y_TEST_FILE, y_test.values)
    print(f"  > Test target saved to: {Y_TEST_FILE}")

    print("\n--- Phase 1: Feature Engineering Complete! ---")


if __name__ == "__main__":
    main()
