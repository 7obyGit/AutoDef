import asyncio
import logging
import threading
from functools import partial

import pytest

from autodef import (
    FlowStoppedError,
    RetryPolicy,
    RunStatus,
    flow,
    retry,
    step,
)


def _double(value: int) -> int:
    return value * 2


def test_sync_flow_records_steps_and_python_control_flow() -> None:
    @flow
    def calculate(values: list[int], include_total: bool) -> int:
        doubled: list[int] = [
            step(partial(_double, value), name=f"double_{index}") for index, value in enumerate(values)
        ]
        if include_total:
            return step(lambda: sum(doubled), name="total")
        return doubled[-1]

    run = calculate([1, 2, 3], True)

    assert run.status is RunStatus.SUCCEEDED
    assert run.result() == 12
    assert [record.name for record in run.steps] == [
        "double_0",
        "double_1",
        "double_2",
        "total",
    ]
    assert all(record.status is RunStatus.SUCCEEDED for record in run.steps)
    assert run.steps[-1].result == 12
    assert run.duration is not None


def test_flow_logs_lifecycle_and_progress_is_opt_in(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    @flow
    def quiet() -> int:
        return step(lambda: 1, name="work")

    caplog.set_level(logging.INFO, logger="autodef.flows")
    quiet_run = quiet()

    assert quiet_run.result() == 1
    assert capsys.readouterr().out == ""
    assert any("[quiet] started" in record.message for record in caplog.records)
    assert any("work: succeeded" in record.message for record in caplog.records)

    @flow(progress=True)
    def tracked() -> int:
        return step(lambda: 2, name="work")

    tracked_run = tracked()

    assert tracked_run.result() == 2
    output = capsys.readouterr().out
    assert "[tracked] started" in output
    assert "[tracked] work: succeeded" in output
    assert "[tracked] succeeded" in output


def test_step_uses_function_name_and_lambda_fallback() -> None:
    def named_operation() -> int:
        return 1

    @flow
    def names() -> int:
        step(named_operation)
        return step(lambda: 2)

    run = names()

    assert [record.name for record in run.steps] == ["named_operation", "step_2"]


def test_steps_require_an_active_flow() -> None:
    with pytest.raises(RuntimeError, match="active flow"):
        step(lambda: 1)

    with pytest.raises(RuntimeError, match="active flow"):
        retry(RetryPolicy(), lambda: 1)


def test_flow_captures_failure_and_can_restart() -> None:
    calls = 0

    @flow
    def eventually_succeeds() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("not yet")
        return "ready"

    failed = eventually_succeeds()

    assert failed.status is RunStatus.FAILED
    assert isinstance(failed.error, ValueError)
    with pytest.raises(ValueError, match="not yet"):
        failed.result()

    retried = failed.retry()

    assert retried.result() == "ready"
    assert retried.retry_of is failed
    with pytest.raises(RuntimeError, match="failed or stopped"):
        retried.retry()


def test_explicit_retry_records_each_attempt() -> None:
    calls = 0

    def unstable() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("temporary")
        return "done"

    @flow
    def workflow() -> str:
        return retry(
            RetryPolicy(attempts=3, delay=0.001, backoff=2, exceptions=(OSError,)),
            unstable,
        )

    run = workflow()

    assert run.result() == "done"
    assert calls == 3
    assert len(run.steps) == 1
    assert [attempt.status for attempt in run.steps[0].attempts] == [
        RunStatus.FAILED,
        RunStatus.FAILED,
        RunStatus.SUCCEEDED,
    ]


def test_retry_does_not_catch_excluded_exception() -> None:
    @flow
    def workflow() -> None:
        retry(
            RetryPolicy(attempts=3, exceptions=(OSError,)),
            lambda: (_ for _ in ()).throw(ValueError("invalid")),
        )

    run = workflow()

    assert run.status is RunStatus.FAILED
    assert len(run.steps[0].attempts) == 1
    with pytest.raises(ValueError, match="invalid"):
        run.result()


def test_nested_flow_is_unwrapped_and_retained() -> None:
    @flow
    def child(value: int) -> int:
        return step(lambda: value * 2, name="double")

    @flow
    def parent(value: int) -> int:
        child_result = step(lambda: child(value), name="child")
        return child_result + 1

    run = parent(4)

    assert run.result() == 9
    child_run = run.steps[0].child_run
    assert child_run is not None
    assert child_run.result() == 8
    assert child_run.steps[0].name == "double"


def test_background_sync_flow_can_be_stopped_cooperatively() -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocking_operation() -> int:
        entered.set()
        release.wait(timeout=2)
        return 1

    @flow
    def workflow() -> int:
        return step(blocking_operation)

    run = workflow.start()
    assert entered.wait(timeout=1)

    assert run.stop()
    assert not run.stop()
    release.set()

    with pytest.raises(FlowStoppedError):
        run.result(timeout=1)
    assert run.status is RunStatus.STOPPED


def test_background_sync_flow_can_stop_during_retry_delay() -> None:
    attempted = threading.Event()

    def unavailable() -> None:
        attempted.set()
        raise OSError("offline")

    @flow
    def workflow() -> None:
        retry(RetryPolicy(attempts=2, delay=10), unavailable)

    run = workflow.start()
    assert attempted.wait(timeout=1)
    assert run.stop()

    with pytest.raises(FlowStoppedError):
        run.result(timeout=1)
    assert run.steps[0].status is RunStatus.STOPPED


def test_retry_policy_validation() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RetryPolicy(attempts=0)
    with pytest.raises(ValueError, match="negative"):
        RetryPolicy(delay=-1)
    with pytest.raises(ValueError, match="negative"):
        RetryPolicy(backoff=-1)
    with pytest.raises(ValueError, match="at least one"):
        RetryPolicy(exceptions=())


def test_async_flow_supports_sync_and_async_steps() -> None:
    async def double(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    @flow
    async def workflow(value: int) -> int:
        incremented = step(lambda: value + 1, name="increment")
        return await step(lambda: double(incremented), name="double")

    async def run_workflow() -> None:
        run = await workflow(2)
        assert run.status is RunStatus.SUCCEEDED
        assert run.result() == 6
        assert await run == 6
        assert [record.name for record in run.steps] == ["increment", "double"]

    asyncio.run(run_workflow())


def test_async_flow_composes_an_async_child() -> None:
    @flow
    async def child(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    @flow
    async def parent(value: int) -> int:
        child_result = await step(lambda: child(value), name="child")
        return child_result + 1

    async def run_workflow() -> None:
        run = await parent(4)
        assert run.result() == 9
        assert run.steps[0].child_run is not None
        assert run.steps[0].child_run.result() == 8

    asyncio.run(run_workflow())


def test_async_background_flow_is_awaitable_and_stoppable() -> None:
    entered = asyncio.Event()

    @flow
    async def workflow() -> int:
        entered.set()
        await asyncio.sleep(10)
        return 1

    async def run_workflow() -> None:
        run = workflow.start()
        await entered.wait()
        with pytest.raises(RuntimeError, match="await the run"):
            run.result()
        assert run.stop()
        with pytest.raises(FlowStoppedError):
            await run
        assert run.status is RunStatus.STOPPED

    asyncio.run(run_workflow())


def test_async_flow_can_stop_during_retry_delay() -> None:
    attempted = asyncio.Event()

    async def unavailable() -> None:
        attempted.set()
        raise OSError("offline")

    @flow
    async def workflow() -> None:
        await retry(RetryPolicy(attempts=2, delay=10), unavailable)

    async def run_workflow() -> None:
        run = workflow.start()
        await attempted.wait()
        await asyncio.sleep(0)
        assert run.stop()
        with pytest.raises(FlowStoppedError):
            await run
        assert run.steps[0].status is RunStatus.STOPPED

    asyncio.run(run_workflow())


def test_async_retry_restarts_entire_flow() -> None:
    calls = 0

    @flow
    async def workflow() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        if calls == 1:
            raise ValueError("first run")
        return "ok"

    async def run_workflow() -> None:
        failed = await workflow()
        retried = await failed.retry()
        assert retried.result() == "ok"
        assert retried.retry_of is failed

    asyncio.run(run_workflow())
