"""Apply an explicit retry policy to one unreliable operation."""

from autodef import RetryPolicy, flow, retry

attempt_count = 0


def occasionally_unavailable() -> str:
    global attempt_count
    attempt_count += 1
    if attempt_count < 3:
        raise ConnectionError(f"temporary failure on attempt {attempt_count}")
    return "service response"


@flow
def fetch_data() -> str:
    return retry(
        RetryPolicy(
            attempts=3,
            delay=0.1,
            backoff=2,
            exceptions=(ConnectionError,),
        ),
        occasionally_unavailable,
        name="fetch_service",
    )


if __name__ == "__main__":
    run = fetch_data()
    recorded_step = run.steps[0]

    print(run.result())
    print(f"Step status: {recorded_step.status}")
    for attempt in recorded_step.attempts:
        print(f"Attempt {attempt.number}: {attempt.status} ({attempt.error or attempt.result})")
