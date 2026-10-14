"""Training + loading of the crop model, and per-crop statistics."""
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "Crop_recommendation.csv"
MODEL_PATH = ROOT / "backend" / "model.joblib"
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]


def train():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found. Put Crop_recommendation.csv at {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    df.columns = [c.strip() for c in df.columns]
    df["label"] = df["label"].str.strip().str.lower()
    X, y = df[FEATURES], df["label"]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)
    accuracy = float(model.score(X_te, y_te))
    model.fit(X, y)  # refit on all rows for production use
    g = df.groupby("label")[FEATURES]
    bundle = {
        "model": model,
        "means": g.mean().round(2).to_dict("index"),
        "stds": g.std().replace(0, 1e-6).fillna(1.0).to_dict("index"),
        "accuracy": accuracy,
        "rows": int(len(df)),
    }
    joblib.dump(bundle, MODEL_PATH)
    return bundle


def load_or_train():
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    return train()
