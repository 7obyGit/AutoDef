"""Inspect a failed run and restart the whole flow with its original arguments."""

from autodef import RunStatus, flow, step

invocations = 0


@flow
def temporarily_broken(value: int) -> int:
    global invocations
    invocations += 1
    if invocations == 1:
        raise RuntimeError("the first flow invocation fails")
    return step(lambda: value * 2, name="double")


if __name__ == "__main__":
    failed = temporarily_broken(21)
    assert failed.status is RunStatus.FAILED
    print(f"First run: {failed.status} ({failed.error})")

    replacement = failed.retry()
    print(f"Replacement run: {replacement.status} ({replacement.result()})")
    print(f"Linked to failed run: {replacement.retry_of is failed}")
