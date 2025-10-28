"""
PHASE 1.5: PRE-COMPUTATION OF SEMANTIC SCORES

This script performs the computationally expensive task of generating semantic
highlight scores for ALL jobs in the database and saves them back to the
database. This is a one-time operation (or run whenever highlights change)
to dramatically speed up subsequent feature engineering and prediction runs.

This script:
1. Connects to MongoDB.
2. Loads all job descriptions from the 'dice_jobs' collection.
3. Loads all highlights from the 'training_highlights' collection.
4. Initializes the 'SemanticHighlightScorer' with the sentence transformer model.
5. Generates four semantic scores for each job.
6. Saves these scores back into each job document in the 'dice_jobs' collection.
"""

import sys
import pandas as pd
from pymongo.operations import UpdateOne

# Import custom functions and constants
from mongodb_functions import connect_to_mongodb, DATABASE_NAME
from custom_transformers import SemanticHighlightScorer

# --- CONFIGURATION ---
DICE_JOBS_COLLECTION = "dice_jobs"
HIGHLIGHTS_COLLECTION = "training_highlights"
SEMANTIC_MODEL_NAME = 'all-MiniLM-L6-v2'

# Set to a number (e.g., 100) to test on a subset, or None to run on all jobs.
DEBUG_LIMIT = None
# --- END CONFIGURATION ---

def main():
    """
    Main function to run the pre-computation.
    """
    client, db = connect_to_mongodb()
    if db is None:
        sys.exit(1)

    try:
        # 1. Load job descriptions for RATED jobs that have been segmented
        print("Loading segmented job descriptions from MongoDB...")
        # This query targets only the ~400 jobs you've processed.
        find_query = db[DICE_JOBS_COLLECTION].find(
            {"very_important_text": {"$exists": True}}, 
            {"_id": 1, "very_important_text": 1, "important_text": 1, "other_text": 1, "description": 1}
        )

        if DEBUG_LIMIT:
            print(f"--- DEBUG MODE: Limiting to {DEBUG_LIMIT} jobs. ---")
            find_query = find_query.limit(DEBUG_LIMIT)

        jobs_cursor = find_query
        jobs_df = pd.DataFrame(list(jobs_cursor)).set_index('_id')
        if jobs_df.empty:
            print("No jobs found with segmented text fields. Please run 'process_highlights.py' first.")
            return
        print(f"Loaded {len(jobs_df)} jobs with segmented text.")
        # If 'other_text' is empty, fall back to the original description.
        jobs_df['other_text'] = jobs_df['other_text'].fillna(jobs_df['description'])

        # 2. Load highlights
        highlights_df = pd.DataFrame(list(db[HIGHLIGHTS_COLLECTION].find()))
        if highlights_df.empty:
            print("Warning: No highlights found. Semantic scores will all be zero.")

        # 3. Initialize and fit the scorer
        # This loads the heavy sentence-transformer model
        scorer = SemanticHighlightScorer(highlights_df=highlights_df, model_name=SEMANTIC_MODEL_NAME)
        scorer.fit(None) # Fit doesn't require X data

        # 4. Generate semantic scores for EACH text segment
        print("\nGenerating semantic scores for 'very_important_text'...")
        vi_scores = scorer.transform(jobs_df['very_important_text'].fillna(''))

        print("Generating semantic scores for 'important_text'...")
        i_scores = scorer.transform(jobs_df['important_text'].fillna(''))

        print("Generating semantic scores for 'other_text'...")
        o_scores = scorer.transform(jobs_df['other_text'].fillna(''))

        # 5. Prepare scores for database update
        print("\nPreparing scores for database update...")
        # These are the generic names we'll use inside each sub-document
        score_keys = ['max_liked', 'mean_liked', 'max_disliked', 'mean_disliked']

        def create_scores_dict(scores_matrix, index):
            return {key: float(val) for key, val in zip(score_keys, scores_matrix[index])}

        # 6. Save scores back to MongoDB
        print("Saving pre-computed scores back to MongoDB...")
        
        bulk_operations = []
        # Convert sparse matrices to dense arrays for easier iteration
        vi_scores_dense = vi_scores.toarray()
        i_scores_dense = i_scores.toarray()
        o_scores_dense = o_scores.toarray()

        for i, job_id in enumerate(jobs_df.index):
            update_payload = {
                "very_important_scores": create_scores_dict(vi_scores_dense, i),
                "important_scores": create_scores_dict(i_scores_dense, i),
                "other_scores": create_scores_dict(o_scores_dense, i)
            }

            bulk_operations.append(
                UpdateOne(
                    {"_id": job_id},
                    {"$set": update_payload}
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
            print(f"\nTotal jobs updated with pre-computed scores: {total_modified}")
        else:
            print("  > No scores to save.")

        print("\n--- Pre-computation of Semantic Scores Complete! ---")

    finally:
        if client:
            client.close()
            print("\nMongoDB connection closed.")

if __name__ == "__main__":
    main()
