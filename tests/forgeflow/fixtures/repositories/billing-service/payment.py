"""Payment processing with an idempotency bug."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentRecord:
    id: str
    order_id: str
    amount: int


_charges: dict[str, PaymentRecord] = {}


def charges_for(order_id: str) -> list[PaymentRecord]:
    """Return all recorded charges for an order."""
    return [record for record in _charges.values() if record.order_id == order_id]


def charge(order_id: str, amount: int) -> PaymentRecord:
    """Charge an order.

    BUG: no idempotency guard — a retried call for the same order creates a
    second payment record.
    """
    record = PaymentRecord(id=uuid.uuid4().hex, order_id=order_id, amount=amount)
    _charges[record.id] = record
    return record
