from collections.abc import Awaitable
from typing import assert_type

from autodef import FlowRun, RetryPolicy, flow, retry, step
from autodef.flows import AsyncFlowRun, SyncFlowRun


def _typing_examples() -> None:
    @flow
    def child(value: int) -> str:
        return str(value)

    @flow
    def parent(value: int, *, prefix: str) -> str:
        child_result = step(lambda: child(value))
        assert_type(child_result, str)
        return retry(RetryPolicy(), lambda: prefix + child_result)

    sync_run = parent(1, prefix="value=")
    assert_type(sync_run, SyncFlowRun[str])
    flow_run: FlowRun[str] = sync_run
    assert_type(flow_run, FlowRun[str])
    assert_type(sync_run.result(), str)

    async def transform(value: int) -> str:
        return str(value)

    @flow
    async def async_parent(value: int) -> str:
        pending = step(lambda: transform(value))
        assert_type(pending, Awaitable[str])
        return await pending

    async def check_async_call() -> None:
        async_run = await async_parent(1)
        assert_type(async_run, AsyncFlowRun[str])
        flow_run: FlowRun[str] = async_run
        assert_type(flow_run, FlowRun[str])
