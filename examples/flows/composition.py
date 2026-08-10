"""Compose flows and inspect their parent-child run hierarchy."""

from dataclasses import dataclass

from autodef import flow, step


@dataclass(frozen=True)
class Invoice:
    subtotal: float
    tax: float
    total: float


@flow
def calculate_subtotal(prices: list[float]) -> float:
    return step(lambda: sum(prices), name="sum_prices")


@flow
def create_invoice(prices: list[float], tax_rate: float) -> Invoice:
    subtotal = step(lambda: calculate_subtotal(prices), name="subtotal_flow")
    tax = step(lambda: round(subtotal * tax_rate, 2), name="calculate_tax")
    return Invoice(subtotal=subtotal, tax=tax, total=round(subtotal + tax, 2))


if __name__ == "__main__":
    run = create_invoice([12.50, 3.25, 8.00], 0.2)
    child_run = run.steps[0].child_run

    print(run.result())
    print(f"Parent step: {run.steps[0].name}")
    print(f"Child steps: {[record.name for record in child_run.steps] if child_run else []}")
