from payment import charge, charges_for


def test_charge_records_payment() -> None:
    record = charge("order-1", 100)
    assert record.amount == 100
    assert len(charges_for("order-1")) == 1


def test_same_order_is_charged_once() -> None:
    # Fails until the idempotency bug in payment.charge is fixed.
    charge("order-2", 50)
    charge("order-2", 50)
    assert len(charges_for("order-2")) == 1
