"""
UTILITY SCRIPT: INSPECT PIPELINE FEATURES

This script loads the pre-trained scikit-learn pipeline created by
'feature_engineering.py' and prints out the names of all the features
it generates. This is useful for debugging and understanding the model's inputs.
"""

import joblib
import sys

# This import is crucial! Even if not called directly, it makes the class
# definitions available to joblib when it un-pickles the pipeline.
# Without this, joblib.load() will fail with an AttributeError.
try:
    from custom_transformers import (
        TitleRatingTransformer, 
        SkillFeaturesTransformer, 
        PrecomputedSegmentScoresTransformer,
        # Also include others that might be in older pipeline versions for safety
        SemanticScoreV2Transformer,
        SemanticHighlightScorer,
        PrecomputedHighlightTransformer
    )
except ImportError as e:
    print(f"FATAL ERROR: Could not import custom transformers. {e}")
    print("Please ensure 'custom_transformers.py' is in the same directory.")
    sys.exit(1)


PIPELINE_FILE = "job_rating_pipeline.joblib"

def inspect_features():
    """
    Loads the saved scikit-learn pipeline and prints out the feature names.
    """
    print(f"Loading pipeline from: {PIPELINE_FILE}")
    try:
        pipeline = joblib.load(PIPELINE_FILE)
    except FileNotFoundError:
        print(f"FATAL ERROR: Pipeline file not found at '{PIPELINE_FILE}'.")
        print("Please run 'feature_engineering.py' first to create the pipeline file.")
        return
    except Exception as e:
        print(f"An error occurred while loading the pipeline: {e}")
        return

    try:
        # The preprocessor is the first (and only) step in our pipeline
        preprocessor = pipeline.named_steps['preprocessor']
        feature_names = preprocessor.get_feature_names_out()

        print(f"\n--- Pipeline Feature Inspection ---")
        print(f"Total number of features: {len(feature_names)}")
        
        print("\n--- Sample of Feature Names ---")
        print("First 20 features:")
        for name in feature_names[:20]:
            print(f"  - {name}")
            
        print("\nLast 20 features:")
        for name in feature_names[-20:]:
            print(f"  - {name}")

    except Exception as e:
        print(f"\nAn error occurred while extracting feature names: {e}")

if __name__ == "__main__":
    inspect_features()