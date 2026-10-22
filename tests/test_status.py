import pytest

from app.models import Order, OrderStatus
from app.services.orders import InvalidTransition, change_status

S = OrderStatus


def test_happy_path_sets_timestamps():
    order = Order(status=S.created)
    for status in (S.paid, S.assigned, S.picked_up, S.delivered):
        change_status(order, status)
        assert order.status == status
        assert getattr(order, f"{status}_at") is not None


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (S.created, S.assigned),
        (S.picked_up, S.cancelled),
        (S.delivered, S.cancelled),
        (S.cancelled, S.paid),
    ],
)
def test_forbidden_transitions(current, new):
    order = Order(status=current)
    with pytest.raises(InvalidTransition):
        change_status(order, new)
    assert order.status == current
