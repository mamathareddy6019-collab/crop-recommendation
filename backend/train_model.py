"""Run once (or whenever the CSV changes):  python backend/train_model.py"""
from model import train

b = train()
print(f"Trained on {b['rows']} rows, {len(b['means'])} crops, "
      f"hold-out accuracy {b['accuracy']:.3f}")
