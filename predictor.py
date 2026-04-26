"""
Lightweight ML module: trains a RandomForest on reconciliation features
to predict the likely status of new/unseen transactions.
"""
import numpy as np
from typing import List, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from models import Transaction, ReconciliationRecord, TransactionStatus, Currency
from config import settings

_model: Optional[RandomForestClassifier] = None
_label_enc: Optional[LabelEncoder] = None


def _extract_features(p: Transaction, b: Optional[Transaction] = None) -> list:
    """Extract numeric features from a (platform, bank) pair."""
    p_inr = p.amount if p.currency == Currency.INR else p.amount * settings.INR_TO_USD_RATE
    b_inr = (b.amount if b.currency == Currency.INR else b.amount * settings.INR_TO_USD_RATE) if b else p_inr
    diff = abs(p_inr - b_inr)
    same_currency = int(b.currency == p.currency) if b else 1
    is_refund = int(p.is_refund)
    has_bank = int(b is not None)
    p_month = int(p.date[:7].replace("-", "")) if p.date else 0
    b_month = int(b.date[:7].replace("-", "")) if (b and b.date) else p_month
    month_diff = abs(p_month - b_month)
    return [p_inr, b_inr, diff, same_currency, is_refund, has_bank, month_diff]


def _record_to_features(rec: ReconciliationRecord) -> list:
    p_inr = rec.platform_amount or 0
    b_inr = rec.bank_amount or p_inr
    if rec.platform_currency == Currency.USD:
        p_inr *= settings.INR_TO_USD_RATE
    if rec.bank_currency == Currency.USD:
        b_inr *= settings.INR_TO_USD_RATE
    diff = abs(p_inr - b_inr)
    same_currency = int(rec.platform_currency == rec.bank_currency) if (rec.platform_currency and rec.bank_currency) else 1
    is_refund = 0
    has_bank = int(rec.bank_id is not None)
    p_month = int(rec.platform_date[:7].replace("-", "")) if rec.platform_date else 0
    b_month = int(rec.bank_date[:7].replace("-", "")) if rec.bank_date else p_month
    month_diff = abs(p_month - b_month)
    return [p_inr, b_inr, diff, same_currency, is_refund, has_bank, month_diff]


def train(records: List[ReconciliationRecord]) -> dict:
    global _model, _label_enc
    X = [_record_to_features(r) for r in records]
    y = [r.status.value for r in records]
    _label_enc = LabelEncoder()
    y_enc = _label_enc.fit_transform(y)
    _model = RandomForestClassifier(n_estimators=50, random_state=42)
    _model.fit(X, y_enc)
    return {"trained_on": len(records), "classes": list(_label_enc.classes_)}


def predict(transactions: List[Transaction]) -> List[dict]:
    if _model is None or _label_enc is None:
        raise ValueError("Model not trained. Call /reconcile first to auto-train.")
    results = []
    for t in transactions:
        feats = _extract_features(t)
        proba = _model.predict_proba([feats])[0]
        idx = int(np.argmax(proba))
        label = _label_enc.inverse_transform([idx])[0]
        results.append({
            "transaction_id": t.id,
            "predicted_status": label,
            "confidence": round(float(proba[idx]), 3),
            "features": {
                "amount_inr": feats[0],
                "diff": feats[2],
                "same_currency": bool(feats[3]),
                "is_refund": bool(feats[4]),
            }
        })
    return results
