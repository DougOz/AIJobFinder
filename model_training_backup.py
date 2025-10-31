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
- lightgbm (for LGBMRegressor)
- xgboost (for XGBRegressor)
- matplotlib (for plotting)

Install:
pip install numpy scikit-learn scipy lightgbm xgboost matplotlib pandas
"""

import numpy as np
import joblib
import pandas as pd
import sys
from scipy.sparse import load_npz, vstack
from itertools import combinations # <-- NEW: For creating blends
from time import time

# sklearn imports
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import LinearSVR
from sklearn.ensemble import ExtraTreesRegressor # <-- NEW: Replacing RandomForest
from sklearn.model_selection import GridSearchCV # <-- ADDED: For hyperparameter tuning
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, median_absolute_error # <-- ADDED: More metrics

# --- Custom Transformers ---
# This import is crucial! Even if not called directly, it makes the class
# definitions available to joblib when it un-pickles the pipeline.
from custom_transformers import (
    TitleRatingTransformer, 
    SkillFeaturesTransformer, 
    PrecomputedSegmentScoresTransformer,
    # Also include others that might be in older pipeline versions for safety
    SemanticScoreV2Transformer,
    SemanticHighlightScorer,
    PrecomputedHighlightTransformer
)

# 3rd party model imports
try:
    from lightgbm import LGBMRegressor, early_stopping # <-- MODIFIED: Import early_stopping
    LGBM_INSTALLED = True
except ImportError:
    LGBM_INSTALLED = False
    print("Warning: 'lightgbm' not found. Skipping LGBMRegressor model.")
    print("To install, run: pip install lightgbm")

try:
    import xgboost as xgb # <-- ADDED: XGBoost
    XGBOOST_INSTALLED = True
except ImportError:
    XGBOOST_INSTALLED = False
    print("Warning: 'xgboost' not found. Skipping XGBRegressor model.")
    print("To install, run: pip install xgboost")

try:
    from xgboost import XGBRegressor
    XGBOOST_INSTALLED = True
except ImportError:
    XGBOOST_INSTALLED = False
    print("Warning: 'xgboost' not found. Skipping XGBRegressor model.")
    
try:
    import matplotlib.pyplot as plt # <-- ADDED: Matplotlib for plotting
    MATPLOTLIB_INSTALLED = True
except ImportError:
    MATPLOTLIB_INSTALLED = False
    print("Warning: 'matplotlib' not found. Skipping visualization.")
    print("To install, run: pip install matplotlib")


# --- CONFIGURATION ---
# These must match the output file names from feature_engineering.py
X_TRAIN_FILE = "X_train_transformed.npz"
Y_TRAIN_FILE = "y_train.npy"
X_VAL_FILE = "X_val_transformed.npz"
Y_VAL_FILE = "y_val.npy"
X_TEST_FILE = "X_test_transformed.npz" # <-- ADDED
Y_TEST_FILE = "y_test.npy"             # <-- ADDED
PIPELINE_FILE = "job_rating_pipeline.joblib" # <-- ADDED: Need this for feature names

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
        X_test = load_npz(X_TEST_FILE) # <-- ADDED
        y_test = np.load(Y_TEST_FILE)   # <-- ADDED
        
        print(f"  > Loaded X_train: {X_train.shape}")
        print(f"  > Loaded y_train: {y_train.shape}")
        print(f"  > Loaded X_val:   {X_val.shape}")
        print(f"  > Loaded y_val:   {y_val.shape}")
        print(f"  > Loaded X_test:  {X_test.shape}") # <-- ADDED
        print(f"  > Loaded y_test:  {y_test.shape}")   # <-- ADDED
        
        return X_train, X_val, y_train, y_val, X_test, y_test

    except FileNotFoundError as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"Error: Could not find data file '{e.filename}'.")
        print("Please ensure 'feature_engineering.py' was run successfully before this script.")
        sys.exit(1) # Exit the script with an error code
    except Exception as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"An unexpected error occurred while loading data: {e}")
        sys.exit(1) # Exit the script with an error code


def evaluate_model(model_name, y_val, y_pred):
    """
    Calculates and prints evaluation metrics for a model.
    """
    mae = mean_absolute_error(y_val, y_pred)
    medae = median_absolute_error(y_val, y_pred) # <-- ADDED
    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    r2 = r2_score(y_val, y_pred) # <-- ADDED
    
    print(f"\n--- Results for: {model_name} ---")
    print(f"  R-squared (R²):               {r2:.4f}")
    print(f"  Mean Absolute Error (MAE):    {mae:.4f}")
    print(f"  Median Absolute Error (MedAE): {medae:.4f}") # <-- ADDED
    print(f"  Root Mean Squared Error (RMSE): {rmse:.4f}")
    print(f"  (MAE means the model's predictions are, on average, +/- {mae:.2f} points from your true score)")

    return r2 # Return R-squared for comparison
def plot_diagnostics(y_val, y_pred, model_name):
    """
    Generates and saves diagnostic plots:
    1. Histogram of actual ratings
    2. Scatter plot of Predictions vs. Actuals
    3. Residuals Plot (Errors vs. Predicted Values)
    """
    print(f"\nGenerating diagnostic plots for {model_name}...")
    
    plt.figure(figsize=(18, 6))
    
    # 1. Histogram of actual ratings
    plt.subplot(1, 3, 1)
    plt.hist(y_val, bins=np.arange(0.5, 9.5, 1), edgecolor='black')
    plt.title('Distribution of Your Ratings (Validation Set)')
    plt.xlabel('Actual Rating')
    plt.ylabel('Count of Jobs')
    plt.xticks(range(1, 9))
    plt.grid(axis='y', alpha=0.5)
    
    # 2. Scatter plot of Predictions vs. Actuals
    plt.subplot(1, 3, 2)
    plt.scatter(y_val, y_pred, alpha=0.5)
    
    # Add a 1:1 line (perfect prediction)
    min_val = min(y_val.min(), y_pred.min())
    max_val = max(y_val.max(), y_pred.max())
    plt.plot([min_val, max_val], [min_val, max_val], 'r--', label='Perfect Prediction')
    
    plt.title(f'{model_name}: Predictions vs. Actual Ratings')
    plt.xlabel('Actual Rating')
    plt.ylabel('Predicted Rating')
    plt.legend()
    plt.grid(True)
    
    # 3. Residuals Plot
    plt.subplot(1, 3, 3)
    residuals = y_val - y_pred
    plt.scatter(y_pred, residuals, alpha=0.5)
    plt.axhline(y=0, color='r', linestyle='--')
    plt.title(f'{model_name}: Residuals Plot')
    plt.xlabel('Predicted Rating')
    plt.ylabel('Prediction Error (Actual - Predicted)')
    plt.grid(True)
    
    plt.tight_layout()
    
    # Save the figure
    filename = 'diagnostic_plots.png'
    plt.savefig(filename)
    print(f"  > Diagnostic plots saved to: {filename}")
    plt.close()


def plot_feature_importances(pipeline, model, model_name):
    """
    Generates and saves a plot of the Top 20 most important features
    for a given tree-based model (like RandomForest or XGBoost).
    """
    print(f"\nGenerating feature importance plot for {model_name}...")
    
    # Check if the model supports feature_importances_
    if not hasattr(model, 'feature_importances_'):
        print(f"  > Skipping: {model_name} does not have 'feature_importances_' attribute.")
        return
        
    try:
        # Get feature names from the preprocessor pipeline
        feature_names = pipeline.named_steps['preprocessor'].get_feature_names_out()
        
        # Create a pandas Series for easy plotting
        importances = model.feature_importances_
        feat_imp_series = pd.Series(importances, index=feature_names)
        
        # Get Top 20
        top_20 = feat_imp_series.nlargest(20)
        
        # Plot
        plt.figure(figsize=(10, 8))
        top_20.sort_values().plot(kind='barh') # Horizontal bar chart
        plt.title(f'Top 20 Most Important Features ({model_name})')
        plt.xlabel('Importance')
        plt.tight_layout()
        
        # Save the figure
        filename = f'{model_name.lower().replace(" ", "_")}_feature_importances.png'
        plt.savefig(filename)
        print(f"  > Feature importance plot saved to: {filename}")
        plt.close()

    except Exception as e:
        print(f"  > ERROR: Could not generate feature importance plot: {e}")


def main():
    # 1. Load the data
    X_train, X_val, y_train, y_val, X_test, y_test = load_feature_data()
    # The load function now exits on its own if data is not found,
    # so we don't need to check for None here.

    # --- Model Tracking ---
    # Dictionary to store trained models and their validation scores
    trained_models = {}
    
    # --- V2.2: Revert to full feature set (remove SelectKBest) ---
    # No changes needed here, as SelectKBest was removed in the previous step.

    if LGBM_INSTALLED:
        print("\nTraining Advanced Model (LightGBM Regressor)...")

        # --- Two-Stage Hyperparameter Tuning ---
        
        # V2.2: Slightly more regularization than last run
        lgbm_param_grid = {
            'learning_rate': [0.05, 0.1], # Keep learning rate in the grid
            'num_leaves': [15, 20, 31], # Constrain tree complexity
            'reg_alpha': [0.1, 0.5, 1], # L1 regularization - slightly increased max
            'reg_lambda': [0.1, 0.5, 1]  # L2 regularization - slightly increased max
        }
        # STAGE 1: Find the optimal number of estimators using early stopping
        print("  > Stage 1: Finding optimal n_estimators with early stopping...")
        lgbm_temp = LGBMRegressor(n_estimators=2000, learning_rate=0.05, random_state=RANDOM_STATE, n_jobs=N_JOBS)
        
        lgbm_temp.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            eval_metric='mae',
            callbacks=[early_stopping(100, verbose=False)] # Stop if MAE doesn't improve for 100 rounds
        )
        
        optimal_n_estimators = lgbm_temp.best_iteration_
        if optimal_n_estimators is None or optimal_n_estimators == 0:
            print("  > Warning: Early stopping did not find an optimal iteration. Defaulting to 100.")
            optimal_n_estimators = 100
        else:
             # Add a small buffer
            optimal_n_estimators = int(optimal_n_estimators * 1.1)

        print(f"  > Optimal n_estimators found: {optimal_n_estimators}")

        # STAGE 2: Tune other hyperparameters with GridSearchCV using the optimal n_estimators
        print("  > Stage 2: Tuning other hyperparameters with GridSearchCV...")
        
        lgbm_estimator = LGBMRegressor(
            n_estimators=optimal_n_estimators,
            random_state=RANDOM_STATE,
            n_jobs=N_JOBS
        )

        grid_search = GridSearchCV(
            estimator=lgbm_estimator,
            param_grid=lgbm_param_grid,
            scoring='neg_mean_absolute_error', # We want to minimize MAE
            cv=3, # 3-fold cross-validation
            n_jobs=N_JOBS,
            verbose=1,
            refit=True
        )

        # Revert to the simpler fit method that was performing better,
        # without the early stopping callback inside the grid search.
        grid_search.fit(X_train, y_train)
        # --- FIX: Pass early stopping params via fit_params to GridSearchCV ---
        fit_params = {
            'eval_set': [(X_val, y_val)],
            'callbacks': [early_stopping(100, verbose=False)]
        }
        grid_search.fit(X_train, y_train)

        print(f"  > GridSearchCV complete. Best params: {grid_search.best_params_}")
        lgbm_model = grid_search.best_estimator_ # This is the best model found
        
        print(f"  > Best model is already trained from GridSearchCV.")
        
        # Make predictions on the validation set
        y_pred_lgbm = lgbm_model.predict(X_val)
        
        # Evaluate on training set
        y_pred_lgbm_train = lgbm_model.predict(X_train)
        evaluate_model("LGBM Regressor (Advanced) - Training", y_train, y_pred_lgbm_train)

        # Evaluate on validation set and capture the R-squared score
        # Make predictions on the validation set
        y_pred_lgbm = lgbm_model.predict(X_val)

        # Evaluate
        r2_lgbm = evaluate_model("LGBM Regressor (Advanced)", y_val, y_pred_lgbm)

        trained_models['lgbm'] = {'model': lgbm_model, 'r2_val': r2_lgbm, 'y_pred_val': y_pred_lgbm}

    # 2. Train and evaluate the BASELINE model (Ridge Regression)
    print("\n\n--- Training Baseline Models ---")
    print("Training Baseline Model (Ridge Regression)...")
      # Initialize the model
    ridge_model = Ridge(alpha=1.0)

    # Train the model
    start_time = time()
    ridge_model.fit(X_train, y_train)
    end_time = time()
    print(f"  > Training complete in {end_time - start_time:.2f} seconds.")

    # Make predictions on the validation set
    y_pred_ridge = ridge_model.predict(X_val)

    # Evaluate on training set
    y_pred_ridge_train = ridge_model.predict(X_train)
    evaluate_model("Ridge Regression (Baseline) - Training", y_train, y_pred_ridge_train)

    # Evaluate
    r2_ridge = evaluate_model("Ridge Regression (Baseline)", y_val, y_pred_ridge)
    trained_models['ridge'] = {'model': ridge_model, 'r2_val': r2_ridge, 'y_pred_val': y_pred_ridge}

    # --- V2.2: Add XGBoost ---
    if XGBOOST_INSTALLED:
        print("\nTraining Advanced Model (XGBoost Regressor)...")
        # --- Two-Stage Hyperparameter Tuning for XGBoost ---
        xgb_param_grid = {
            'learning_rate': [0.05, 0.1],
            'max_depth': [3, 5, 7],
            'gamma': [0, 0.1, 0.2],
            'subsample': [0.7, 0.9],
            'colsample_bytree': [0.7, 0.9],
            'reg_alpha': [0.1, 1, 5],
            'reg_lambda': [0.1, 1, 5]
        }

        # STAGE 1: Find optimal n_estimators with early stopping
        print("  > Stage 1: Finding optimal n_estimators with early stopping for XGBoost...")
        xgb_temp = XGBRegressor(
            n_estimators=2000,
            learning_rate=0.05,
            random_state=RANDOM_STATE,
            n_jobs=N_JOBS,
            # Initial regularization for early stopping



            max_depth=5, gamma=0.1, subsample=0.8, colsample_bytree=0.8,
            early_stopping_rounds=100 # Pass early stopping here
        )
        xgb_temp.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        optimal_n_estimators_xgb = xgb_temp.best_iteration
        if optimal_n_estimators_xgb is None or optimal_n_estimators_xgb == 0:
            print("  > Warning: XGBoost early stopping did not find an optimal iteration. Defaulting to 100.")
            optimal_n_estimators_xgb = 100
        else:
            optimal_n_estimators_xgb = int(optimal_n_estimators_xgb * 1.1) # Add a small buffer
        print(f"  > Optimal n_estimators found for XGBoost: {optimal_n_estimators_xgb}")

        # STAGE 2: Tune other hyperparameters with GridSearchCV
        print("  > Stage 2: Tuning other hyperparameters with GridSearchCV for XGBoost...")
        xgb_estimator = XGBRegressor(
            n_estimators=optimal_n_estimators_xgb,
            random_state=RANDOM_STATE,
            n_jobs=N_JOBS,
            early_stopping_rounds=100 # Pass early stopping to the estimator for grid search
        )
        xgb_grid_search = GridSearchCV(
            estimator=xgb_estimator,
            param_grid=xgb_param_grid,
            scoring='neg_mean_absolute_error',
            cv=3,
            n_jobs=N_JOBS,
            verbose=1,
            refit=True
        )
        start_time = time()
        # --- FIX: Pass early stopping params via fit_params to GridSearchCV for XGBoost ---
        xgb_fit_params = {
            'eval_set': [(X_val, y_val)],
            'verbose': False
        }
        xgb_grid_search.fit(
            X_train, y_train, **xgb_fit_params
        )
        end_time = time()
        print(f"  > GridSearchCV complete. Best params for XGBoost: {xgb_grid_search.best_params_}")
        xgb_model = xgb_grid_search.best_estimator_

        y_pred_xgb = xgb_model.predict(X_val)
        y_pred_xgb_train = xgb_model.predict(X_train)
        evaluate_model("XGBoost Regressor - Training", y_train, y_pred_xgb_train)
        r2_xgb = evaluate_model("XGBoost Regressor", y_val, y_pred_xgb)
        trained_models['xgb'] = {'model': xgb_model, 'r2_val': r2_xgb, 'y_pred_val': y_pred_xgb}
    
    # --- NEW: Add ExtraTreesRegressor ---
    print("\nTraining Ensemble Model (ExtraTrees Regressor)...")
    et_model = ExtraTreesRegressor(
        n_estimators=150, # More estimators can be better, but slower
        random_state=RANDOM_STATE,
        n_jobs=N_JOBS,
        max_depth=15, # Limit depth to prevent overfitting
        min_samples_leaf=5, # Ensure each leaf has at least 5 samples
        bootstrap=True, # Use bootstrap samples
        oob_score=True # Use out-of-bag samples to estimate R^2 on unseen data
    )
    start_time = time()
    et_model.fit(X_train, y_train)
    end_time = time()
    print(f"  > Training complete in {end_time - start_time:.2f} seconds.")
    if et_model.oob_score_:
        print(f"  > Out-of-Bag R² Score Estimate: {et_model.oob_score_:.4f}")

    y_pred_et = et_model.predict(X_val)
    y_pred_et_train = et_model.predict(X_train)
    evaluate_model("ExtraTrees Regressor - Training", y_train, y_pred_et_train)
    r2_et = evaluate_model("ExtraTrees Regressor", y_val, y_pred_et)
    trained_models['et'] = {'model': et_model, 'r2_val': r2_et, 'y_pred_val': y_pred_et}

    # --- Comprehensive Blending ---
    print("\n\n--- Creating and Evaluating All Model Blends ---")
    model_names_for_blending = [name for name in trained_models.keys() if name != 'blended'] # Exclude previous blends

    # Loop through all combination sizes (2-way, 3-way, etc.)
    for r in range(2, len(model_names_for_blending) + 1):
        # Get all combinations of models of size 'r'
        for model_combo in combinations(model_names_for_blending, r):
            num_models = len(model_combo)
            blend_name = f"blend_{'_'.join(model_combo)}"
            
            # Calculate the blended prediction by averaging
            y_pred_blend = np.zeros_like(y_val)
            for model_name in model_combo:
                y_pred_blend += trained_models[model_name]['y_pred_val']
            y_pred_blend /= num_models

            # Evaluate the blend
            combo_name_str = ' + '.join([name.upper() for name in model_combo])
            r2_blend = evaluate_model(f"Blend: {combo_name_str}", y_val, y_pred_blend)

            # Store the blend as a "model"
            blend_model_obj = {
                'component_models': {name: trained_models[name]['model'] for name in model_combo},
                'weights': {name: 1/num_models for name in model_combo}
            }
            trained_models[blend_name] = {
                'model': blend_model_obj,
                'r2_val': r2_blend,
                'y_pred_val': y_pred_blend # Store its predictions for later use
            }


    # 3. Train and evaluate LinearSVR
    print("\nTraining Second Linear-Style Model (LinearSVR)...")
    svr_model = LinearSVR(random_state=RANDOM_STATE, dual="auto", max_iter=10000)
    # Train the model
    start_time = time()
    svr_model.fit(X_train, y_train)
    end_time = time()
    print(f"  > Training complete in {end_time - start_time:.2f} seconds.")

    # Make predictions on the validation set
    y_pred_svr = svr_model.predict(X_val)
    
    # Evaluate on training set
    y_pred_svr_train = svr_model.predict(X_train)
    evaluate_model("LinearSVR - Training", y_train, y_pred_svr_train)

    # Evaluate
    r2_svr = evaluate_model("LinearSVR", y_val, y_pred_svr)
    trained_models['svr'] = {'model': svr_model, 'r2_val': r2_svr, 'y_pred_val': y_pred_svr}


    print("\n--- Model Comparison Complete! ---")
    
    # 4. Save the best model
    if trained_models:
        # Find the model with the highest validation R-squared
        best_model_name = max(trained_models, key=lambda k: trained_models[k]['r2_val'])
        best_model_data = trained_models[best_model_name]
        best_model_obj = best_model_data['model']
        
        best_model_filename = "best_model.joblib"
        joblib.dump(best_model_obj, best_model_filename)
        
        print(f"\n--- Best Model Selection ---")
        print(f"Best performing model on validation set: '{best_model_name.upper()}' (R²: {best_model_data['r2_val']:.4f})")
        print(f"  > Best model saved to: {best_model_filename}")

        # --- NEW: Final evaluation on combined validation + test set ---
        print("\n--- Final Evaluation on Combined Validation + Test Set (150 samples) ---")
        
        # Get feature names to prevent UserWarning
        try:
            feature_names = joblib.load(PIPELINE_FILE).named_steps['preprocessor'].get_feature_names_out()
        except Exception:
            feature_names = None # Fallback if it fails

        # Combine the validation and test sets for a more robust evaluation
        X_combined_sparse = vstack([X_val, X_test]) # Combine sparse matrices
        y_combined = np.concatenate([y_val, y_test])

        # Get predictions from the best model on this combined set
        # --- FIX: Predict directly on the sparse matrix, not a DataFrame ---
        if best_model_name.startswith('blend_'):
            component_models = best_model_obj['component_models']
            
            # Generate predictions from each component model in the blend
            preds = {name: model.predict(X_combined_sparse) for name, model in component_models.items()}

            weights = best_model_obj['weights']
            # Sum the weighted predictions
            y_pred_combined = sum(preds[name] * weights[name] for name in component_models.keys())
        else:
            y_pred_combined = best_model_obj.predict(X_combined_sparse)

        # Evaluate and print the results
        evaluate_model(
            f"Final '{best_model_name.upper()}' on Combined Val+Test Set",
            y_combined,
            y_pred_combined
        )
    
    # 5. Generate visualizations for the best model
    if MATPLOTLIB_INSTALLED:
        print("\n--- Generating Visualizations ---")
        try:
            # Load the fitted pipeline to get feature names
            full_pipeline = joblib.load(PIPELINE_FILE)
            
            # Get the predictions for the best model
            if best_model_name.startswith('blend_'):
                y_pred_best = best_model_data['y_pred_val']
            else:
                y_pred_best = best_model_obj.predict(X_val)
            
            # Plot diagnostics for the best model
            plot_diagnostics(y_val, y_pred_best, f"Best Model: {best_model_name.upper()}")
            
            # Plot feature importances for the most complex part of the best model
            if best_model_name.startswith('blend_'):
                # For a blend, show importances of the most complex model (LGBM)
                if 'lgbm' in best_model_obj['component_models']:
                    plot_feature_importances(full_pipeline, best_model_obj['component_models']['lgbm'], "LightGBM (from Blend)")
            elif hasattr(best_model_obj, 'feature_importances_'):
                plot_feature_importances(full_pipeline, best_model_obj, best_model_name.upper())

        except FileNotFoundError:
            print(f"ERROR: Could not load '{PIPELINE_FILE}' to generate feature names.")
            print("Please ensure 'feature_engineering.py' was run successfully.")
        except Exception as e:
            print(f"An error occurred during visualization: {e}")

    

if __name__ == "__main__":
    main()
