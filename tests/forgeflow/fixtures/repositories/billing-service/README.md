# billing-service

A minimal fixture repository used by ForgeFlow tests to exercise the
planning adapter (M1). It contains a payment module with an idempotency
bug and a test that currently fails.

## Layout

- `payment.py` — `charge(order_id, amount)`, no idempotency guard
- `tests/test_payment.py` — test suite (one test fails on the bug)
