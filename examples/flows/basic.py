"""Use normal Python decisions and loops inside a typed flow."""

from dataclasses import dataclass
from functools import partial

from autodef import flow, step


@dataclass(frozen=True)
class NumberSummary:
    squares: list[int]
    total: int
    average: float | None


def square(value: int) -> int:
    return value**2


@flow
def summarize_numbers(values: list[int], *, include_average: bool = True) -> NumberSummary:
    cleaned = step(lambda: [value for value in values if value >= 0], name="remove_negatives")
    squares = [step(partial(square, value), name=f"square_{index}") for index, value in enumerate(cleaned)]
    total = step(lambda: sum(squares), name="total")

    average = None
    if include_average and squares:
        average = step(lambda: total / len(squares), name="average")

    return NumberSummary(squares=squares, total=total, average=average)


if __name__ == "__main__":
    run = summarize_numbers([2, -1, 3, 4])

    print(run.result())
    print(f"Status: {run.status}")
    print(f"Duration: {run.duration:.6f}s" if run.duration is not None else "No timing")
    print(f"Steps: {[record.name for record in run.steps]}")
