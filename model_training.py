"""
PHASE 2 & 3: MODEL TRAINING & EVALUATION
This script loads the pre-processed data matrices created by
'feature_engineering.py' and trains/evaluates our models
as outlined in the 'ml_modeling_plan.md'.

This script does NOT connect to MongoDB.

Required libraries:
- numpy
- scikit-learn
- scipy (for loading sparse matrices)

Install:
pip install numpy scikit-learn scipy
"""

import numpy as np
import joblib
from scipy.sparse import load_npz
from time import time

# sklearn imports
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# --- CONFIGURATION ---
# These must match the output file names from feature_engineering.py
X_TRAIN_FILE = "X_train_transformed.npz"
X_VAL_FILE = "X_val_transformed.npz"
Y_TRAIN_FILE = "y_train.npy"
Y_VAL_FILE = "y_val.npy"

# Model-specific settings
RANDOM_STATE = 42 # For reproducibility
N_JOBS = -1 # Use all available CPU cores
# --- END CONFIGURATION ---


def load_feature_data():
    """
    Loads the transformed feature matrices and target vectors from disk.
    """
    print("Loading pre-processed data from disk...")
    try:
        X_train = load_npz(X_TRAIN_FILE)
        X_val = load_npz(X_VAL_FILE)
        y_train = np.load(Y_TRAIN_FILE)
        y_val = np.load(Y_VAL_FILE)
        
        print(f"  > Loaded X_train: {X_train.shape}")
        print(f"  > Loaded y_train: {y_train.shape}")
        print(f"  > Loaded X_val:   {X_val.shape}")
        print(f"  > Loaded y_val:   {y_val.shape}")
        
        return X_train, X_val, y_train, y_val

    except FileNotFoundError as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"Error: Could not find data file '{e.filename}'.")
        print("Please ensure 'feature_engineering.py' was run successfully first.")
        return None, None, None, None
    except Exception as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"An unexpected error occurred while loading data: {e}")
        return None, None, None, None


def evaluate_model(model_name, y_val, y_pred):
    """
    Calculates and prints evaluation metrics for a model.
    """
    mae = mean_absolute_error(y_val, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    
    print(f"\n--- Results for: {model_name} ---")
    print(f"  Mean Absolute Error (MAE): {mae:.4f}")
    print(f"  Root Mean Squared Error (RMSE): {rmse:.4f}")
    print(f"  (MAE means the model's predictions are, on average, +/- {mae:.2f} points from your true score)")


def main():
    # 1. Load the data
    X_train, X_val, y_train, y_val = load_feature_data()
    if X_train is None:
        return # Error message already printed

    # 2. Train and evaluate the BASELINE model (Ridge Regression)
    print("\nTraining Baseline Model (Ridge Regression)...")
    
    # Initialize the model
    # Ridge is great for sparse data and is very fast
    ridge_model = Ridge(alpha=1.0) 
    
    # Train the model
    start_time = time()
    ridge_model.fit(X_train, y_train)
    end_time = time()
    print(f"  > Training complete in {end_time - start_time:.2f} seconds.")

    # Make predictions on the validation set
    y_pred_ridge = ridge_model.predict(X_val)
    
    # Evaluate
    evaluate_model("Ridge Regression (Baseline)", y_val, y_pred_ridge)


    # 3. Train and evaluate the ADVANCED model (Random Forest)
    print("\nTraining Advanced Model (Random Forest Regressor)...")
    
    # Initialize the model
    # n_estimators=100 is a good default
    # n_jobs=-1 uses all your CPU cores to speed up training
    rf_model = RandomForestRegressor(
        n_estimators=100, 
        random_state=RANDOM_STATE, 
        n_jobs=N_JOBS
    )
    
    # Train the model
    start_time = time()
    rf_model.fit(X_train, y_train)
    end_time = time()
    print(f"  > Training complete in {end_time - start_time:.2f} seconds.")

    # Make predictions on the validation set
    y_pred_rf = rf_model.predict(X_val)
    
    # Evaluate
    evaluate_model("Random Forest Regressor (Advanced)", y_val, y_pred_rf)
    
    print("\n--- Model Comparison Complete! ---")
    

if __name__ == "__main__":
    main()
