from cart import apply_discount, total


def test_total() -> None:
    assert total([(100, 2), (50, 1)]) == 250


def test_discount() -> None:
    assert apply_discount(200, 10) == 180
