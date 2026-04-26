from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"


class TransactionStatus(str, Enum):
    MATCHED = "matched"
    MISSING_IN_BANK = "missing_in_bank"
    EXTRA_IN_BANK = "extra_in_bank"
    DUPLICATE = "duplicate"
    DELAYED = "delayed"
    ROUNDING_DIFF = "rounding_diff"
    AMOUNT_MISMATCH = "amount_mismatch"
    UNMATCHED_REFUND = "unmatched_refund"
    CURRENCY_MISMATCH = "currency_mismatch"


class Transaction(BaseModel):
    id: str
    amount: float
    currency: Currency
    date: str
    description: str
    reference: Optional[str] = None
    is_refund: bool = False


class ReconciliationRecord(BaseModel):
    platform_id: Optional[str]
    bank_id: Optional[str]
    platform_amount: Optional[float]
    bank_amount: Optional[float]
    platform_currency: Optional[str]
    bank_currency: Optional[str]
    platform_date: Optional[str]
    bank_date: Optional[str]
    status: TransactionStatus
    discrepancy: Optional[float] = None
    note: Optional[str] = None


class ReconciliationReport(BaseModel):
    total_platform: int
    total_bank: int
    matched: int
    discrepancies: int
    summary: dict
    records: List[ReconciliationRecord]


class PredictionResult(BaseModel):
    transaction_id: str
    predicted_status: str
    confidence: float
    features: dict


class GenerateRequest(BaseModel):
    num_transactions: int = 50
    seed: Optional[int] = None


class PredictRequest(BaseModel):
    transactions: List[Transaction]
