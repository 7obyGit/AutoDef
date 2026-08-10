from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from functools import update_wrapper
from typing import Any, cast, overload


class RunStatus(StrEnum):
    """Lifecycle states shared by flow, step, and attempt records."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"


class FlowStoppedError(RuntimeError):
    """Raised when the result of a stopped flow is requested."""


class _StopFlow(BaseException):
    """Internal cooperative-cancellation signal that user Exception handlers do not swallow."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Controls retries for an explicitly retried operation."""

    attempts: int = 3
    delay: float = 0.0
    backoff: float = 1.0
    exceptions: tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.delay < 0:
            raise ValueError("delay must not be negative")
        if self.backoff < 0:
            raise ValueError("backoff must not be negative")
        if not self.exceptions:
            raise ValueError("exceptions must contain at least one exception type")
        if any(not issubclass(exception, Exception) for exception in self.exceptions):
            raise TypeError("exceptions must contain only Exception subclasses")


@dataclass(slots=True)
class AttemptRun:
    """In-memory record for one invocation of a step operation."""

    number: int
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: BaseException | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass(slots=True)
class StepRun:
    """In-memory record for an explicitly observed operation."""

    name: str
    operation: Callable[[], Any]
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: BaseException | None = None
    attempts: list[AttemptRun] = field(default_factory=list)
    child_run: FlowRun[Any] | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


_TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.STOPPED})
_current_run: ContextVar[FlowRun[Any] | None] = ContextVar("autodef_current_flow_run", default=None)


class FlowRun[R]:
    """A live or completed, inspectable execution of a flow."""

    def __init__(
        self,
        *,
        flow: SyncFlow[..., R] | AsyncFlow[..., R],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        is_async: bool,
        retry_of: FlowRun[R] | None = None,
    ) -> None:
        self._flow = flow
        self._args = args
        self._kwargs = kwargs
        self._is_async = is_async
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._result: Any = None
        self._task: asyncio.Task[None] | None = None
        self._task_loop: asyncio.AbstractEventLoop | None = None
        self.status = RunStatus.PENDING
        self.error: BaseException | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.retry_of = retry_of
        self._steps: list[StepRun] = []

    @property
    def steps(self) -> Sequence[StepRun]:
        """A snapshot of steps recorded so far."""
        with self._condition:
            return tuple(self._steps)

    @property
    def duration(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started_at

    def result(self, timeout: float | None = None) -> R:
        """Wait for completion and return the typed result, or raise the recorded failure."""
        if self.status not in _TERMINAL_STATUSES and self._task_loop is not None:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                if running_loop is self._task_loop:
                    raise RuntimeError("cannot block on an async flow in its event loop; await the run instead")

        with self._condition:
            completed = self._condition.wait_for(lambda: self.status in _TERMINAL_STATUSES, timeout=timeout)
            if not completed:
                raise TimeoutError("flow did not finish before the timeout")

            if self.status is RunStatus.STOPPED:
                raise FlowStoppedError("flow was stopped")
            if self.status is RunStatus.FAILED:
                if self.error is None:
                    raise RuntimeError("flow failed without recording an error")
                raise self.error
            return cast(R, self._result)

    async def _result_async(self) -> R:
        if self.status not in _TERMINAL_STATUSES:
            await asyncio.to_thread(self.result)
        return self.result()

    def __await__(self) -> Any:
        return self._result_async().__await__()

    def stop(self) -> bool:
        """Request cooperative cancellation, returning whether the request was accepted."""
        with self._condition:
            if self.status in _TERMINAL_STATUSES or self.status is RunStatus.STOP_REQUESTED:
                return False
            self._stop_event.set()
            self.status = RunStatus.STOP_REQUESTED
            self._condition.notify_all()
            task = self._task
            loop = self._task_loop

        if task is not None and loop is not None:
            loop.call_soon_threadsafe(task.cancel)
        return True

    def _check_stopped(self) -> None:
        if self._stop_event.is_set():
            raise _StopFlow

    def _start_running(self) -> None:
        with self._condition:
            self._check_stopped()
            self.status = RunStatus.RUNNING
            self.started_at = time.monotonic()
            self._condition.notify_all()

    def _succeed(self, result: R) -> None:
        with self._condition:
            if self._stop_event.is_set():
                self.status = RunStatus.STOPPED
            else:
                self._result = result
                self.status = RunStatus.SUCCEEDED
            self.finished_at = time.monotonic()
            self._condition.notify_all()

    def _fail(self, error: BaseException) -> None:
        with self._condition:
            self.error = error
            self.status = RunStatus.FAILED
            self.finished_at = time.monotonic()
            self._condition.notify_all()

    def _stopped(self) -> None:
        with self._condition:
            self.status = RunStatus.STOPPED
            self.finished_at = time.monotonic()
            self._condition.notify_all()

    def _add_step(self, step_run: StepRun) -> None:
        with self._condition:
            self._steps.append(step_run)
            self._condition.notify_all()


class SyncFlowRun[R](FlowRun[R]):
    """A run produced by a synchronous flow."""

    _flow: SyncFlow[..., R]

    def retry(self, *, background: bool = False) -> SyncFlowRun[R]:
        """Restart a failed or stopped flow with its original arguments."""
        if self.status not in {RunStatus.FAILED, RunStatus.STOPPED}:
            raise RuntimeError("only failed or stopped flows can be retried")
        return self._flow._invoke(self._args, self._kwargs, background=background, retry_of=self)


class AsyncFlowRun[R](FlowRun[R]):
    """A run produced by an asynchronous flow."""

    _flow: AsyncFlow[..., R]

    async def retry(self, *, background: bool = False) -> AsyncFlowRun[R]:
        """Restart a failed or stopped async flow with its original arguments."""
        if self.status not in {RunStatus.FAILED, RunStatus.STOPPED}:
            raise RuntimeError("only failed or stopped flows can be retried")
        if background:
            return self._flow._start(self._args, self._kwargs, retry_of=self)
        return await self._flow._invoke(self._args, self._kwargs, retry_of=self)


class SyncFlow[**P, R]:
    """Callable wrapper for a synchronous flow function."""

    def __init__(self, function: Callable[P, R]) -> None:
        self._function = function
        self._name = function.__name__
        update_wrapper(self, function)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> SyncFlowRun[R]:
        return self._invoke(args, kwargs)

    def start(self, *args: P.args, **kwargs: P.kwargs) -> SyncFlowRun[R]:
        """Start the flow on a background worker and return its live run."""
        return self._invoke(args, kwargs, background=True)

    def _invoke(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        background: bool = False,
        retry_of: FlowRun[R] | None = None,
    ) -> SyncFlowRun[R]:
        run = SyncFlowRun(
            flow=self,
            args=args,
            kwargs=kwargs,
            is_async=False,
            retry_of=retry_of,
        )
        if background:
            thread = threading.Thread(
                target=self._execute,
                args=(run, args, kwargs),
                name=f"autodef-flow-{self._name}",
                daemon=True,
            )
            thread.start()
        else:
            self._execute(run, args, kwargs)
        return run

    def _execute(self, run: SyncFlowRun[R], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        token = _current_run.set(run)
        try:
            run._start_running()
            result = self._function(*args, **kwargs)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("a synchronous flow cannot return an awaitable")
            run._succeed(result)
        except _StopFlow:
            run._stopped()
        except Exception as error:
            run._fail(error)
        finally:
            _current_run.reset(token)


class AsyncFlow[**P, R]:
    """Callable wrapper for an asynchronous flow function."""

    def __init__(self, function: Callable[P, Awaitable[R]]) -> None:
        self._function = function
        self._name = function.__name__
        update_wrapper(self, function)

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncFlowRun[R]:
        return await self._invoke(args, kwargs)

    def start(self, *args: P.args, **kwargs: P.kwargs) -> AsyncFlowRun[R]:
        """Schedule the flow in the current loop, or on a background loop if needed."""
        return self._start(args, kwargs)

    async def _invoke(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        retry_of: FlowRun[R] | None = None,
    ) -> AsyncFlowRun[R]:
        run = AsyncFlowRun(
            flow=self,
            args=args,
            kwargs=kwargs,
            is_async=True,
            retry_of=retry_of,
        )
        await self._execute(run, args, kwargs)
        return run

    def _start(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        retry_of: FlowRun[R] | None = None,
    ) -> AsyncFlowRun[R]:
        run = AsyncFlowRun(
            flow=self,
            args=args,
            kwargs=kwargs,
            is_async=True,
            retry_of=retry_of,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            thread = threading.Thread(
                target=lambda: asyncio.run(self._execute(run, args, kwargs)),
                name=f"autodef-flow-{self._name}",
                daemon=True,
            )
            thread.start()
        else:
            task = loop.create_task(self._execute(run, args, kwargs))
            run._task = task
            run._task_loop = loop
        return run

    async def _execute(self, run: AsyncFlowRun[R], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        run._task = asyncio.current_task()
        run._task_loop = asyncio.get_running_loop()
        token = _current_run.set(run)
        try:
            run._start_running()
            result = await self._function(*args, **kwargs)
            run._succeed(result)
        except (_StopFlow, asyncio.CancelledError):
            run._stopped()
        except Exception as error:
            run._fail(error)
        finally:
            _current_run.reset(token)


@overload
def flow[**P, R](  # type: ignore[overload-overlap]
    function: Callable[P, Awaitable[R]], /
) -> AsyncFlow[P, R]: ...


@overload
def flow[**P, R](function: Callable[P, R], /) -> SyncFlow[P, R]: ...


def flow[**P, R](function: Callable[P, R] | Callable[P, Awaitable[R]], /) -> SyncFlow[P, R] | AsyncFlow[P, R]:
    """Turn a typed function into an observable, callable flow."""
    if inspect.iscoroutinefunction(function):
        return AsyncFlow(cast(Callable[P, Awaitable[R]], function))
    return SyncFlow(cast(Callable[P, R], function))


def _active_run() -> FlowRun[Any]:
    run = _current_run.get()
    if run is None:
        raise RuntimeError("step() and retry() can only be used inside an active flow")
    run._check_stopped()
    return run


def _step_name(operation: Callable[[], Any], run: FlowRun[Any], prefix: str) -> str:
    operation_name = getattr(operation, "__name__", "")
    if operation_name and operation_name != "<lambda>":
        return operation_name
    return f"{prefix}_{len(run.steps) + 1}"


def _begin_step(operation: Callable[[], Any], name: str | None, prefix: str) -> tuple[FlowRun[Any], StepRun]:
    run = _active_run()
    step_run = StepRun(name=name or _step_name(operation, run, prefix), operation=operation)
    step_run.status = RunStatus.RUNNING
    step_run.started_at = time.monotonic()
    run._add_step(step_run)
    return run, step_run


def _begin_attempt(step_run: StepRun) -> AttemptRun:
    attempt = AttemptRun(number=len(step_run.attempts) + 1)
    attempt.status = RunStatus.RUNNING
    attempt.started_at = time.monotonic()
    step_run.attempts.append(attempt)
    return attempt


def _finish_attempt(attempt: AttemptRun, result: Any) -> None:
    attempt.result = result
    attempt.status = RunStatus.SUCCEEDED
    attempt.finished_at = time.monotonic()


def _fail_attempt(attempt: AttemptRun, error: BaseException) -> None:
    attempt.error = error
    attempt.status = RunStatus.FAILED
    attempt.finished_at = time.monotonic()


def _stop_attempt(attempt: AttemptRun, error: BaseException) -> None:
    attempt.error = error
    attempt.status = RunStatus.STOPPED
    attempt.finished_at = time.monotonic()


def _finish_step(step_run: StepRun, result: Any) -> Any:
    step_run.result = result
    step_run.status = RunStatus.SUCCEEDED
    step_run.finished_at = time.monotonic()
    return result


def _fail_step(step_run: StepRun, error: BaseException) -> None:
    step_run.error = error
    step_run.status = RunStatus.FAILED
    step_run.finished_at = time.monotonic()


def _stop_step(step_run: StepRun, error: BaseException) -> None:
    step_run.error = error
    step_run.status = RunStatus.STOPPED
    step_run.finished_at = time.monotonic()


def _unwrap_sync_result(result: Any, step_run: StepRun) -> Any:
    if isinstance(result, FlowRun):
        step_run.child_run = result
        return result.result()
    return result


async def _unwrap_async_result(result: Any, step_run: StepRun) -> Any:
    if isinstance(result, FlowRun):
        step_run.child_run = result
        return await result
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, FlowRun):
        step_run.child_run = result
        return await result
    return result


async def _complete_async_step(result: Awaitable[Any], step_run: StepRun, attempt: AttemptRun) -> Any:
    try:
        value = await _unwrap_async_result(result, step_run)
        _finish_attempt(attempt, value)
        return _finish_step(step_run, value)
    except BaseException as error:
        if isinstance(error, (_StopFlow, asyncio.CancelledError)):
            _stop_attempt(attempt, error)
            _stop_step(step_run, error)
        else:
            _fail_attempt(attempt, error)
            _fail_step(step_run, error)
        raise


@overload
def step[T](operation: Callable[[], FlowRun[T]], *, name: str | None = None) -> T: ...


@overload
def step[T](operation: Callable[[], Awaitable[FlowRun[T]]], *, name: str | None = None) -> Awaitable[T]: ...


@overload
def step[T](operation: Callable[[], Awaitable[T]], *, name: str | None = None) -> Awaitable[T]: ...


@overload
def step[T](operation: Callable[[], T], *, name: str | None = None) -> T: ...


def step(operation: Callable[[], Any], *, name: str | None = None) -> Any:
    """Execute and record one operation in the active flow."""
    run, step_run = _begin_step(operation, name, "step")
    attempt = _begin_attempt(step_run)
    try:
        result = operation()
        if isinstance(result, FlowRun):
            result = _unwrap_sync_result(result, step_run)
            _finish_attempt(attempt, result)
            return _finish_step(step_run, result)
        if inspect.isawaitable(result):
            if not run._is_async:
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("a synchronous flow cannot execute an async step")
            return _complete_async_step(result, step_run, attempt)
        result = _unwrap_sync_result(result, step_run)
        _finish_attempt(attempt, result)
        return _finish_step(step_run, result)
    except BaseException as error:
        if isinstance(error, (_StopFlow, asyncio.CancelledError)):
            _stop_attempt(attempt, error)
            _stop_step(step_run, error)
        else:
            _fail_attempt(attempt, error)
            _fail_step(step_run, error)
        raise


def _wait_for_retry(run: FlowRun[Any], delay: float) -> None:
    if delay > 0 and run._stop_event.wait(delay):
        raise _StopFlow
    run._check_stopped()


async def _wait_for_retry_async(run: FlowRun[Any], delay: float) -> None:
    if delay > 0:
        await asyncio.sleep(delay)
    run._check_stopped()


def _retry_sync(
    policy: RetryPolicy,
    operation: Callable[[], Any],
    run: FlowRun[Any],
    step_run: StepRun,
    first_result: Any,
    first_attempt: AttemptRun,
    first_error: Exception | None = None,
) -> Any:
    result = first_result
    attempt = first_attempt
    delay = policy.delay
    error_to_raise = first_error
    while True:
        try:
            if error_to_raise is not None:
                error = error_to_raise
                error_to_raise = None
                raise error
            if attempt.number > 1:
                result = operation()
            if isinstance(result, FlowRun):
                result = _unwrap_sync_result(result, step_run)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("a synchronous flow cannot execute an async retry operation")
            result = _unwrap_sync_result(result, step_run)
            _finish_attempt(attempt, result)
            return _finish_step(step_run, result)
        except policy.exceptions as error:
            _fail_attempt(attempt, error)
            if attempt.number == policy.attempts:
                _fail_step(step_run, error)
                raise
            try:
                _wait_for_retry(run, delay)
            except _StopFlow as stop_error:
                _stop_step(step_run, stop_error)
                raise
            delay *= policy.backoff
            attempt = _begin_attempt(step_run)
        except BaseException as error:
            if isinstance(error, (_StopFlow, asyncio.CancelledError)):
                _stop_attempt(attempt, error)
                _stop_step(step_run, error)
            else:
                _fail_attempt(attempt, error)
                _fail_step(step_run, error)
            raise


async def _retry_async(
    policy: RetryPolicy,
    operation: Callable[[], Any],
    run: FlowRun[Any],
    step_run: StepRun,
    first_result: Awaitable[Any],
    first_attempt: AttemptRun,
) -> Any:
    result: Any = first_result
    attempt = first_attempt
    delay = policy.delay
    while True:
        try:
            if attempt.number > 1:
                result = operation()
            result = await _unwrap_async_result(result, step_run)
            _finish_attempt(attempt, result)
            return _finish_step(step_run, result)
        except policy.exceptions as error:
            _fail_attempt(attempt, error)
            if attempt.number == policy.attempts:
                _fail_step(step_run, error)
                raise
            try:
                await _wait_for_retry_async(run, delay)
            except (_StopFlow, asyncio.CancelledError) as stop_error:
                _stop_step(step_run, stop_error)
                raise
            delay *= policy.backoff
            attempt = _begin_attempt(step_run)
        except BaseException as error:
            if isinstance(error, (_StopFlow, asyncio.CancelledError)):
                _stop_attempt(attempt, error)
                _stop_step(step_run, error)
            else:
                _fail_attempt(attempt, error)
                _fail_step(step_run, error)
            raise


@overload
def retry[T](
    policy: RetryPolicy,
    operation: Callable[[], FlowRun[T]],
    *,
    name: str | None = None,
) -> T: ...


@overload
def retry[T](
    policy: RetryPolicy,
    operation: Callable[[], Awaitable[FlowRun[T]]],
    *,
    name: str | None = None,
) -> Awaitable[T]: ...


@overload
def retry[T](
    policy: RetryPolicy,
    operation: Callable[[], Awaitable[T]],
    *,
    name: str | None = None,
) -> Awaitable[T]: ...


@overload
def retry[T](policy: RetryPolicy, operation: Callable[[], T], *, name: str | None = None) -> T: ...


def retry(policy: RetryPolicy, operation: Callable[[], Any], *, name: str | None = None) -> Any:
    """Execute an operation with an explicit retry policy and record every attempt."""
    run, step_run = _begin_step(operation, name, "retry")
    attempt = _begin_attempt(step_run)
    try:
        result = operation()
    except policy.exceptions as error:
        return _retry_sync(policy, operation, run, step_run, None, attempt, first_error=error)
    except BaseException as error:
        _fail_attempt(attempt, error)
        _fail_step(step_run, error)
        raise

    if inspect.isawaitable(result) and not isinstance(result, FlowRun):
        if not run._is_async:
            if inspect.iscoroutine(result):
                result.close()
            async_error = TypeError("a synchronous flow cannot execute an async retry operation")
            _fail_attempt(attempt, async_error)
            _fail_step(step_run, async_error)
            raise async_error
        return _retry_async(policy, operation, run, step_run, result, attempt)
    return _retry_sync(policy, operation, run, step_run, result, attempt)


__all__ = [
    "AsyncFlow",
    "AsyncFlowRun",
    "AttemptRun",
    "FlowRun",
    "FlowStoppedError",
    "RetryPolicy",
    "RunStatus",
    "StepRun",
    "SyncFlow",
    "SyncFlowRun",
    "flow",
    "retry",
    "step",
]
