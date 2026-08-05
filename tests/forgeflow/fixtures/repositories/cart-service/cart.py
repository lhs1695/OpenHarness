"""Simple cart pricing."""


def total(items: list[tuple[int, int]]) -> int:
    """Sum of (price, quantity) pairs."""
    return sum(price * quantity for price, quantity in items)


def apply_discount(total_amount: int, discount_percent: int) -> int:
    """Apply a whole-percent discount."""
    return total_amount * (100 - discount_percent) // 100
