from typing import List
from collections import defaultdict
from datetime import datetime
from models import Transaction, ReconciliationRecord, ReconciliationReport, TransactionStatus, Currency
from config import settings


def _to_inr(amount: float, currency: str) -> float:
    if currency == Currency.USD:
        return round(amount * settings.INR_TO_USD_RATE, 2)
    return amount


def _month(date_str: str) -> str:
    return date_str[:7]  # "YYYY-MM"


def reconcile(platform: List[Transaction], bank: List[Transaction]) -> ReconciliationReport:
    records: List[ReconciliationRecord] = []
    status_counts = defaultdict(int)

    # Index bank by reference
    bank_by_ref: dict[str, list[Transaction]] = defaultdict(list)
    for b in bank:
        if b.reference:
            bank_by_ref[b.reference].append(b)

    matched_bank_ids: set[str] = set()

    for p in platform:
        ref = p.reference
        candidates = bank_by_ref.get(ref, [])

        if not candidates:
            # Missing in bank
            status = TransactionStatus.UNMATCHED_REFUND if p.is_refund else TransactionStatus.MISSING_IN_BANK
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=None,
                platform_amount=p.amount, bank_amount=None,
                platform_currency=p.currency, bank_currency=None,
                platform_date=p.date, bank_date=None,
                status=status,
                note="No bank entry found for this reference"
            ))
            status_counts[status] += 1
            continue

        if len(candidates) > 1:
            # Duplicate in bank
            for b in candidates:
                matched_bank_ids.add(b.id)
            b = candidates[0]
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=b.id,
                platform_amount=p.amount, bank_amount=b.amount,
                platform_currency=p.currency, bank_currency=b.currency,
                platform_date=p.date, bank_date=b.date,
                status=TransactionStatus.DUPLICATE,
                note=f"{len(candidates)} bank entries found"
            ))
            status_counts[TransactionStatus.DUPLICATE] += 1
            continue

        b = candidates[0]
        matched_bank_ids.add(b.id)

        p_inr = _to_inr(p.amount, p.currency)
        b_inr = _to_inr(b.amount, b.currency)
        diff = abs(p_inr - b_inr)

        # Currency mismatch
        if p.currency != b.currency:
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=b.id,
                platform_amount=p.amount, bank_amount=b.amount,
                platform_currency=p.currency, bank_currency=b.currency,
                platform_date=p.date, bank_date=b.date,
                status=TransactionStatus.CURRENCY_MISMATCH,
                discrepancy=diff,
                note=f"Currency: {p.currency} vs {b.currency}"
            ))
            status_counts[TransactionStatus.CURRENCY_MISMATCH] += 1
            continue

        # Delayed (different month)
        if _month(p.date) != _month(b.date):
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=b.id,
                platform_amount=p.amount, bank_amount=b.amount,
                platform_currency=p.currency, bank_currency=b.currency,
                platform_date=p.date, bank_date=b.date,
                status=TransactionStatus.DELAYED,
                note=f"Month mismatch: {_month(p.date)} vs {_month(b.date)}"
            ))
            status_counts[TransactionStatus.DELAYED] += 1
            continue

        # Rounding difference
        if 0 < diff <= settings.ROUNDING_TOLERANCE * settings.INR_TO_USD_RATE:
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=b.id,
                platform_amount=p.amount, bank_amount=b.amount,
                platform_currency=p.currency, bank_currency=b.currency,
                platform_date=p.date, bank_date=b.date,
                status=TransactionStatus.ROUNDING_DIFF,
                discrepancy=diff,
                note=f"Diff ₹{diff:.4f} within tolerance"
            ))
            status_counts[TransactionStatus.ROUNDING_DIFF] += 1
            continue

        # Amount mismatch (significant)
        if diff > settings.ROUNDING_TOLERANCE * settings.INR_TO_USD_RATE:
            records.append(ReconciliationRecord(
                platform_id=p.id, bank_id=b.id,
                platform_amount=p.amount, bank_amount=b.amount,
                platform_currency=p.currency, bank_currency=b.currency,
                platform_date=p.date, bank_date=b.date,
                status=TransactionStatus.AMOUNT_MISMATCH,
                discrepancy=diff,
                note=f"Diff ₹{diff:.2f} exceeds tolerance"
            ))
            status_counts[TransactionStatus.AMOUNT_MISMATCH] += 1
            continue

        # Matched
        records.append(ReconciliationRecord(
            platform_id=p.id, bank_id=b.id,
            platform_amount=p.amount, bank_amount=b.amount,
            platform_currency=p.currency, bank_currency=b.currency,
            platform_date=p.date, bank_date=b.date,
            status=TransactionStatus.MATCHED
        ))
        status_counts[TransactionStatus.MATCHED] += 1

    # Extra in bank (unmatched bank entries)
    for b in bank:
        if b.id not in matched_bank_ids:
            status = TransactionStatus.UNMATCHED_REFUND if b.is_refund else TransactionStatus.EXTRA_IN_BANK
            records.append(ReconciliationRecord(
                platform_id=None, bank_id=b.id,
                platform_amount=None, bank_amount=b.amount,
                platform_currency=None, bank_currency=b.currency,
                platform_date=None, bank_date=b.date,
                status=status,
                note="Bank entry with no platform counterpart"
            ))
            status_counts[status] += 1

    matched = status_counts[TransactionStatus.MATCHED]
    discrepancies = sum(v for k, v in status_counts.items() if k != TransactionStatus.MATCHED)

    return ReconciliationReport(
        total_platform=len(platform),
        total_bank=len(bank),
        matched=matched,
        discrepancies=discrepancies,
        summary={k.value: v for k, v in status_counts.items()},
        records=records,
    )
