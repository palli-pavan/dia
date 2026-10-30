import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import shap
import joblib
import os
from data_processing import load_data, prepare_ml_dataset

def train_and_evaluate_model(data_dir="data", model_dir="models"):
    print("Loading data...")
    datasets = load_data(data_dir)
    df = prepare_ml_dataset(datasets)
    
    # Define features and target
    # We use building_damage, minor_damage, major_damage, destroyed_buildings, population_density, magnitude
    features = [
        'building_damage', 'minor_damage', 'major_damage', 'destroyed_buildings',
        'population_density', 'magnitude'
    ]
    target = 'damage_severity'
    
    X = df[features]
    y = df[target]
    
    # Ensure no missing values in features
    X = X.fillna(0)
    
    print("\nClass Distribution:")
    print(y.value_counts())
    
    # Train-test split
    # Note: Since the synthetic dataset is very small, we might get errors if stratify tries to split classes with 1 sample. 
    # For robust demonstration, we won't stratify here, or we'll wrap it.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("\nTraining Random Forest Classifier...")
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    rf_model.fit(X_train, y_train)
    
    # Evaluation
    y_pred = rf_model.predict(X_test)
    
    # Use zero_division=0 to handle cases where a class might not be present in the test set predictions
    print("\nModel Evaluation:")
    print(f"Accuracy:  {accuracy_score(y_test, y_pred):.4f}")
    print(f"Precision: {precision_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    print(f"Recall:    {recall_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    print(f"F1-Score:  {f1_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    
    print("\nConfusion Matrix:")
    labels = rf_model.classes_
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)
    print(cm_df)
    
    # Save the model
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "damage_model.pkl")
    joblib.dump(rf_model, model_path)
    print(f"\nModel successfully saved to {model_path}")
    
    # SHAP Explainability
    print("\nCalculating SHAP values for explainability...")
    explainer = shap.TreeExplainer(rf_model)
    # We save the explainer for the frontend to use later
    explainer_path = os.path.join(model_dir, "shap_explainer.pkl")
    joblib.dump(explainer, explainer_path)
    print(f"SHAP Explainer successfully saved to {explainer_path}")
    
    return rf_model, explainer

if __name__ == "__main__":
    train_and_evaluate_model(data_dir="data", model_dir="models")
