import random
import uuid
from datetime import datetime, timedelta
from typing import Tuple
from models import Transaction, Currency
from config import settings

DESCRIPTIONS = [
    "SaaS Subscription", "API Credits", "Cloud Storage", "Support Plan",
    "Enterprise License", "Data Export", "Custom Integration", "Training Credits",
]

def _rand_date(base: datetime, spread_days: int = 30) -> str:
    delta = random.randint(0, spread_days)
    return (base - timedelta(days=delta)).strftime("%Y-%m-%d")

def generate_datasets(num: int = 50, seed: int = None) -> Tuple[list[Transaction], list[Transaction]]:
    if seed is not None:
        random.seed(seed)

    base_date = datetime.now()
    platform_txns: list[Transaction] = []
    bank_txns: list[Transaction] = []

    for i in range(num):
        ref = f"TXN-{random.randbytes(4).hex().upper()}"
        amount_inr = round(random.uniform(500, 50000), 2)
        currency = random.choice([Currency.INR, Currency.USD])
        if currency == Currency.USD:
            amount = round(amount_inr / settings.INR_TO_USD_RATE, 2)
        else:
            amount = amount_inr
        date = _rand_date(base_date)
        desc = random.choice(DESCRIPTIONS)
        is_refund = random.random() < 0.08

        p_txn = Transaction(
            id=f"P-{ref}", amount=amount, currency=currency,
            date=date, description=desc, reference=ref, is_refund=is_refund
        )
        platform_txns.append(p_txn)

        roll = random.random()

        if roll < 0.70:  # Normal match
            b_amount = amount
            b_currency = currency
            # Occasional rounding diff
            if random.random() < 0.15:
                b_amount = round(amount + random.uniform(-0.01, 0.01), 2)
            # Occasional currency mismatch (INR stored as USD or vice-versa)
            if random.random() < 0.08:
                b_currency = Currency.USD if currency == Currency.INR else Currency.INR
            b_date = date
            # Delayed settlement (different month)
            if random.random() < 0.10:
                delay = random.randint(28, 45)
                b_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=delay)).strftime("%Y-%m-%d")
            bank_txns.append(Transaction(
                id=f"B-{ref}", amount=b_amount, currency=b_currency,
                date=b_date, description=desc, reference=ref, is_refund=is_refund
            ))

        elif roll < 0.80:  # Missing in bank — skip adding to bank
            pass

        elif roll < 0.87:  # Extra in bank (no platform counterpart)
            extra_ref = f"EXT-{random.randbytes(4).hex().upper()}"
            bank_txns.append(Transaction(
                id=f"B-{extra_ref}", amount=round(random.uniform(100, 5000), 2),
                currency=random.choice([Currency.INR, Currency.USD]),
                date=date, description="Unknown Credit", reference=extra_ref
            ))
            bank_txns.append(Transaction(
                id=f"B-{ref}", amount=amount, currency=currency,
                date=date, description=desc, reference=ref, is_refund=is_refund
            ))

        elif roll < 0.93:  # Duplicate in bank
            for j in range(2):
                bank_txns.append(Transaction(
                    id=f"B-{ref}-{j}", amount=amount, currency=currency,
                    date=date, description=desc, reference=ref, is_refund=is_refund
                ))

        else:  # Amount mismatch (significant)
            mismatch_amount = round(amount * random.uniform(0.85, 1.15), 2)
            bank_txns.append(Transaction(
                id=f"B-{ref}", amount=mismatch_amount, currency=currency,
                date=date, description=desc, reference=ref, is_refund=is_refund
            ))

    # Add a few unmatched refunds in bank
    for _ in range(max(1, num // 20)):
        r_ref = f"REF-{random.randbytes(4).hex().upper()}"
        bank_txns.append(Transaction(
            id=f"B-{r_ref}", amount=round(random.uniform(200, 3000), 2),
            currency=Currency.INR, date=_rand_date(base_date),
            description="Refund", reference=r_ref, is_refund=True
        ))

    return platform_txns, bank_txns
