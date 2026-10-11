from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence


def _to_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _xnpv(rate: float, cash_flows: Sequence[float], dates: Sequence[datetime]) -> float:
    start_date = dates[0]
    return sum(
        amount / ((1 + rate) ** (((current_date - start_date).days) / 365.0))
        for amount, current_date in zip(cash_flows, dates)
    )


def _xnpv_derivative(rate: float, cash_flows: Sequence[float], dates: Sequence[datetime]) -> float:
    start_date = dates[0]
    derivative = 0.0
    for amount, current_date in zip(cash_flows, dates):
        years = ((current_date - start_date).days) / 365.0
        derivative -= (years * amount) / ((1 + rate) ** (years + 1))
    return derivative


def xirr(
    cash_flows: Iterable[float],
    dates: Iterable[datetime | str],
    guess: float = 0.1,
    tolerance: float = 1e-7,
    max_iterations: int = 200,
) -> float:
    cash_flow_list = list(cash_flows)
    date_list = [_to_datetime(item) for item in dates]

    if len(cash_flow_list) != len(date_list):
        raise ValueError("Cash flows and dates must have the same length.")
    if not any(value < 0 for value in cash_flow_list) or not any(value > 0 for value in cash_flow_list):
        raise ValueError("XIRR requires at least one negative and one positive cash flow.")

    rate = guess
    for _ in range(max_iterations):
        value = _xnpv(rate, cash_flow_list, date_list)
        if abs(value) < tolerance:
            return rate
        derivative = _xnpv_derivative(rate, cash_flow_list, date_list)
        if abs(derivative) < tolerance:
            break
        next_rate = rate - value / derivative
        if next_rate <= -0.999999:
            break
        if abs(next_rate - rate) < tolerance:
            return next_rate
        rate = next_rate

    low, high = -0.9999, 10.0
    low_value = _xnpv(low, cash_flow_list, date_list)
    high_value = _xnpv(high, cash_flow_list, date_list)
    if low_value * high_value > 0:
        raise ValueError("Unable to bracket a valid XIRR solution.")

    for _ in range(max_iterations):
        mid = (low + high) / 2
        mid_value = _xnpv(mid, cash_flow_list, date_list)
        if abs(mid_value) < tolerance:
            return mid
        if low_value * mid_value < 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value

    return (low + high) / 2
