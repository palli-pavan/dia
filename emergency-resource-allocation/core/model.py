"""ML Model training, stratified evaluation, cross-validation, selection, and inference.

This module implements Module 1 of the Emergency Decision Support System:
- Trains 3 distinct models:
    1. Logistic Regression (Baseline linear model with standard scaling)
    2. Random Forest Classifier (Non-linear ensemble)
    3. XGBoost Classifier (Gradient boosted trees)
- Uses Stratified train/test split and 5-fold Stratified Cross-Validation.
- Computes comprehensive metrics: Accuracy, Precision, Recall, F1 (macro & weighted),
  ROC-AUC (OvR), PR-AUC (OvR), and Confusion Matrix.
- Selects the best performing model based on F1-macro.
- Generates and exports SHAP TreeExplainer and models/metrics.json.
- Provides robust prediction wrapper with predict_proba check.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    precision_recall_curve,
    auc,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

import sys

# Ensure parent directory is in sys.path when running as a standalone script
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.data import (
    ML_FEATURE_COLS,
    TARGET_COL,
    SEVERITY_CLASSES,
    generate_historical_training_data,
)


def compute_multiclass_pr_auc(
    y_true_binary: np.ndarray, y_proba: np.ndarray
) -> float:
    """Computes macro-averaged Precision-Recall AUC (PR-AUC) across multiclass outputs.

    Args:
        y_true_binary: One-hot encoded ground truth array of shape (n_samples, n_classes).
        y_proba: Predicted probability matrix of shape (n_samples, n_classes).

    Returns:
        Macro-averaged PR-AUC score as a float.
    """
    pr_aucs: List[float] = []
    n_classes = y_true_binary.shape[1]
    for c in range(n_classes):
        precision, recall, _ = precision_recall_curve(y_true_binary[:, c], y_proba[:, c])
        pr_aucs.append(float(auc(recall, precision)))
    return float(np.mean(pr_aucs)) if pr_aucs else 0.0


def evaluate_classifier(
    model: BaseEstimator,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    class_names: List[str],
    cv_folds: int = 5,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Evaluates a trained classifier with test metrics and 5-fold cross-validation.

    Args:
        model: Trained scikit-learn or XGBoost classifier.
        X_train: Training feature set.
        y_train: Training labels (integer-encoded).
        X_test: Test feature set.
        y_test: Test labels (integer-encoded).
        class_names: List of human-readable class names.
        cv_folds: Number of stratified folds.
        random_state: Seed for fold shuffling.

    Returns:
        Dictionary of performance metrics.
    """
    y_pred = model.predict(X_test)
    has_proba = hasattr(model, "predict_proba")
    y_proba = model.predict_proba(X_test) if has_proba else None

    # One-hot encode ground truth for ROC-AUC and PR-AUC
    n_classes = len(class_names)
    y_test_onehot = np.eye(n_classes)[y_test]

    # Test set metrics
    acc = float(accuracy_score(y_test, y_pred))
    prec_macro = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
    prec_weighted = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
    rec_macro = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
    rec_weighted = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
    f1_mac = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    f1_wt = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))

    roc_auc_val: Optional[float] = None
    pr_auc_val: Optional[float] = None
    if y_proba is not None and len(np.unique(y_test)) > 1:
        try:
            roc_auc_val = float(roc_auc_score(y_test_onehot, y_proba, multi_class="ovr", average="macro"))
        except Exception:
            roc_auc_val = None
        try:
            pr_auc_val = compute_multiclass_pr_auc(y_test_onehot, y_proba)
        except Exception:
            pr_auc_val = None

    cm = confusion_matrix(y_test, y_pred, labels=list(range(n_classes))).tolist()

    # Stratified 5-Fold Cross Validation on entire training partition
    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    cv_f1_scores = cross_val_score(model, X_train, y_train, cv=skf, scoring="f1_macro")
    cv_acc_scores = cross_val_score(model, X_train, y_train, cv=skf, scoring="accuracy")

    return {
        "accuracy": round(acc, 4),
        "precision_macro": round(prec_macro, 4),
        "precision_weighted": round(prec_weighted, 4),
        "recall_macro": round(rec_macro, 4),
        "recall_weighted": round(rec_weighted, 4),
        "f1_macro": round(f1_mac, 4),
        "f1_weighted": round(f1_wt, 4),
        "roc_auc_ovr_macro": round(roc_auc_val, 4) if roc_auc_val is not None else None,
        "pr_auc_ovr_macro": round(pr_auc_val, 4) if pr_auc_val is not None else None,
        "has_predict_proba": bool(has_proba),
        "confusion_matrix": cm,
        "class_labels": class_names,
        "cv_5fold_f1_macro_mean": round(float(np.mean(cv_f1_scores)), 4),
        "cv_5fold_f1_macro_std": round(float(np.std(cv_f1_scores)), 4),
        "cv_5fold_accuracy_mean": round(float(np.mean(cv_acc_scores)), 4),
        "cv_5fold_accuracy_std": round(float(np.std(cv_acc_scores)), 4),
    }


def train_and_evaluate_all_models(
    data_path: str = "data/historical_disaster_damage.csv",
    model_dir: str = "models",
    selection_metric: str = "f1_macro",
    random_state: int = 42,
) -> Dict[str, Any]:
    """Trains 3 candidate models, evaluates them, selects best, and saves artifacts.

    Models trained:
    1. Baseline: Logistic Regression (Pipeline with StandardScaler)
    2. Random Forest: RandomForestClassifier(100 trees, balanced weights)
    3. XGBoost: XGBClassifier(gradient boosted decision trees)

    Args:
        data_path: Path to historical dataset CSV.
        model_dir: Output folder for models and metrics.
        selection_metric: Metric key to select best model ('f1_macro' or 'f1_weighted').
        random_state: Random seed for reproducibility.

    Returns:
        Dictionary containing all evaluation results, comparisons, and best model metadata.
    """
    os.makedirs(model_dir, exist_ok=True)

    if not os.path.exists(data_path):
        print(f"[DATA] '{data_path}' not found. Generating synthetic historical training data...")
        df_all = generate_historical_training_data(output_path=data_path, n_samples=800, random_state=random_state)
    else:
        df_all = pd.read_csv(data_path)

    # Features and labels
    X = df_all[ML_FEATURE_COLS].copy().fillna(0)
    y_raw = df_all[TARGET_COL].astype(str)

    # Enforce standard severity class order
    present_classes = [c for c in SEVERITY_CLASSES if c in y_raw.unique()]
    label_encoder = LabelEncoder()
    label_encoder.fit(present_classes)
    y = label_encoder.transform(y_raw)
    class_names = list(label_encoder.classes_)

    # Stratified Train/Test split (80% train, 20% test)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=random_state, stratify=y
    )

    models: Dict[str, BaseEstimator] = {
        "Logistic_Regression_Baseline": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=random_state, class_weight="balanced"))
        ]),
        "Random_Forest": RandomForestClassifier(
            n_estimators=100, max_depth=6, random_state=random_state, class_weight="balanced"
        ),
        "XGBoost": XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            eval_metric="mlogloss",
            random_state=random_state,
        )
    }

    metrics_results: Dict[str, Any] = {}
    trained_instances: Dict[str, BaseEstimator] = {}

    print("\n" + "=" * 60)
    print("STARTING MODEL TRAINING & STRATIFIED EVALUATION")
    print("=" * 60)

    for name, clf in models.items():
        print(f"\n[TRAINING] {name}...")
        clf.fit(X_train, y_train)
        trained_instances[name] = clf

        eval_res = evaluate_classifier(
            clf, X_train, y_train, X_test, y_test,
            class_names=class_names, cv_folds=5, random_state=random_state
        )
        metrics_results[name] = eval_res

        print(f" -> Accuracy:       {eval_res['accuracy']:.4f}")
        print(f" -> F1 Macro:       {eval_res['f1_macro']:.4f}")
        print(f" -> F1 Weighted:    {eval_res['f1_weighted']:.4f}")
        print(f" -> ROC-AUC (OvR):  {eval_res['roc_auc_ovr_macro']}")
        print(f" -> PR-AUC (OvR):   {eval_res['pr_auc_ovr_macro']}")
        print(f" -> 5-Fold CV F1:   {eval_res['cv_5fold_f1_macro_mean']:.4f} +/- {eval_res['cv_5fold_f1_macro_std']:.4f}")

    # Model selection based on stated metric
    best_model_name = max(
        metrics_results.keys(),
        key=lambda k: metrics_results[k].get(selection_metric, 0.0)
    )
    best_model_instance = trained_instances[best_model_name]
    best_score = metrics_results[best_model_name][selection_metric]

    print("\n" + "=" * 60)
    print(f"MODEL SELECTION DECISION: Best model is '{best_model_name}'")
    print(f"Selection Metric: {selection_metric} = {best_score:.4f}")
    print("=" * 60)

    # SHAP Explainer Generation
    # If the best model is a Pipeline (Logistic), we use the underlying tree model for SHAP TreeExplainer
    tree_model = trained_instances["Random_Forest"]
    if "XGBoost" in trained_instances and best_model_name == "XGBoost":
        tree_model = trained_instances["XGBoost"]

    print("\n[EXPLAIN] Fitting SHAP TreeExplainer...")
    explainer = shap.TreeExplainer(tree_model)
    shap_path = os.path.join(model_dir, "shap_explainer.pkl")
    joblib.dump(explainer, shap_path)
    print(f"[SAVE] SHAP Explainer saved to {shap_path}")

    # Save Models
    best_model_path = os.path.join(model_dir, "best_model.pkl")
    damage_model_path = os.path.join(model_dir, "damage_model.pkl")
    encoder_path = os.path.join(model_dir, "label_encoder.pkl")

    joblib.dump(best_model_instance, best_model_path)
    # Also save as damage_model.pkl for backwards compatibility
    joblib.dump(best_model_instance, damage_model_path)
    joblib.dump(label_encoder, encoder_path)

    # Save metrics.json
    summary_payload: Dict[str, Any] = {
        "metadata": {
            "training_samples_total": len(df_all),
            "train_set_size": len(X_train),
            "test_set_size": len(X_test),
            "feature_columns": ML_FEATURE_COLS,
            "target_column": TARGET_COL,
            "classes": class_names,
            "random_state": random_state,
            "selection_metric": selection_metric,
            "best_model_name": best_model_name,
            "best_model_score": best_score,
            "data_source": "SYNTHETIC_HISTORICAL"
        },
        "models": metrics_results,
        "feature_importances": {}
    }

    # Extract feature importances if available
    if hasattr(best_model_instance, "feature_importances_"):
        summary_payload["feature_importances"][best_model_name] = dict(
            zip(ML_FEATURE_COLS, [round(float(v), 4) for v in best_model_instance.feature_importances_])
        )
    elif hasattr(trained_instances["Random_Forest"], "feature_importances_"):
        summary_payload["feature_importances"]["Random_Forest"] = dict(
            zip(ML_FEATURE_COLS, [round(float(v), 4) for v in trained_instances["Random_Forest"].feature_importances_])
        )

    metrics_json_path = os.path.join(model_dir, "metrics.json")
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    print(f"[SAVE] Model metrics saved to {metrics_json_path}")
    print(f"[SAVE] Best model saved to {best_model_path} and {damage_model_path}")

    return summary_payload


def predict_damage_severity(
    model: BaseEstimator,
    df_features: pd.DataFrame,
    label_encoder: Optional[LabelEncoder] = None,
    return_proba: bool = True
) -> Tuple[np.ndarray, Optional[np.ndarray], List[str]]:
    """Generates severity predictions and probabilities with fallback handling.

    Args:
        model: Trained classifier model.
        df_features: Input DataFrame containing required feature columns.
        label_encoder: Fitted LabelEncoder for class names, if applicable.
        return_proba: Whether to compute and return class probabilities.

    Returns:
        Tuple of (predicted_class_labels, probability_matrix_or_None, class_names).
    """
    X = df_features[ML_FEATURE_COLS].copy().fillna(0)
    raw_preds = model.predict(X)

    # Convert numeric predictions to class strings if encoder provided
    if label_encoder is not None:
        try:
            preds = label_encoder.inverse_transform(raw_preds)
            classes = list(label_encoder.classes_)
        except Exception:
            preds = raw_preds
            classes = list(getattr(model, "classes_", []))
    else:
        preds = raw_preds
        classes = list(getattr(model, "classes_", []))

    proba = None
    if return_proba and hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(X)
        except Exception:
            proba = None

    return preds, proba, [str(c) for c in classes]


if __name__ == "__main__":
    train_and_evaluate_all_models()
