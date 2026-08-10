# Typed flows

AutoDef flows organize ordinary Python and LLM-backed functions into observable workflows. A flow keeps Python's existing type system and control flow: functions remain responsible for business logic, while `step()` marks the operations whose status, results, timing, failures, and attempts should be recorded.

## Quick start

```python
from autodef import flow, step

@flow
def prepare_message(name: str) -> str:
    normalized = step(lambda: name.strip().title(), name="normalize_name")
    return step(lambda: f"Hello, {normalized}!", name="format_message")

run = prepare_message("  ada  ")

print(run.status)    # RunStatus.SUCCEEDED
print(run.result())  # Hello, Ada!
print(run.steps)     # The two recorded StepRun objects
```

Calling a synchronous flow executes it immediately and returns `FlowRun[R]`, where `R` is the decorated function's return type. Failures are stored on the run instead of being raised by the initial call; `run.result()` returns `R` or re-raises the recorded failure.

Flow lifecycle and step events are always sent to the standard-library `autodef.flows` logger at `INFO` level (failures use `ERROR`). Configure that logger using Python's normal logging handlers. Console output is separate and opt-in:

```python
import logging

logging.basicConfig(level=logging.INFO)

@flow(progress=True)
def tracked_work() -> int:
    return step(lambda: 42, name="compute")
```

`progress=True` prints compact flow and step updates to stdout, including start, completion, retry attempts, failures, and elapsed time. It defaults to `False`, so library consumers do not receive unsolicited console output. The LLM pipeline example enables it because model calls can take noticeable time.

## Why operations are zero-argument callables

`step()` accepts one callable that can be invoked without arguments:

```python
result = step(lambda: transform(source, mode="strict"), name="transform")
```

The closure preserves the exact signature of `transform` without reserving keywords such as `name`, `attempts`, or `delay`. Those names may legitimately belong to the wrapped function. It also gives each step one clear operation to execute and retain in memory.

A named zero-argument function works equally well and supplies its own default step name:

```python
def load_configuration() -> dict[str, str]:
    return {"mode": "strict"}

configuration = step(load_configuration)
```

Lambdas receive an ordinal fallback such as `step_1`; use `name=` when a stable or domain-specific name matters.

## Decisions and loops

Flows deliberately use normal Python rather than a graph DSL:

```python
@flow
def score(values: list[int], *, include_bonus: bool) -> int:
    scores = [
        step(lambda value=value: value * 10, name=f"score_{index}")
        for index, value in enumerate(values)
    ]

    if include_bonus:
        scores.append(step(lambda: 25, name="bonus"))

    return sum(scores)
```

The run records only the steps that actually execute. Decisions and loop iterations need no special node types, and intermediate variables retain their normal static types.

## Composing flows

Pass a flow call through `step()` to make it a child workflow:

```python
@flow
def parse(raw: str) -> list[str]:
    return step(lambda: raw.splitlines(), name="split_lines")

@flow
def import_document(raw: str) -> int:
    lines = step(lambda: parse(raw), name="parse_document")
    return step(lambda: len(lines), name="count_lines")
```

`step()` recognizes the returned child `FlowRun`, attaches it to `StepRun.child_run`, waits for it, and returns the child's typed result. A child failure fails the parent step and is captured by the parent flow.

Calling a flow without `step()` still returns its run object, but does not add it to the current flow's step hierarchy.

## LLM pipelines

Functions decorated with `@llm`, `@impl`, or `@shim` are ordinary typed callables and require no flow-specific adapter:

```python
from pydantic import BaseModel

from autodef import flow, llm, step

class Outline(BaseModel):
    sections: list[str]

@llm
def create_outline(topic: str) -> Outline:
    """Create a concise article outline."""
    ...

@llm
def draft_section(topic: str, section: str) -> str:
    """Draft one section of the article."""
    ...

@flow
def draft_article(topic: str) -> str:
    outline = step(lambda: create_outline(topic), name="outline")
    sections = [
        step(
            lambda section=section: draft_section(topic, section),
            name=f"draft_{index}",
        )
        for index, section in enumerate(outline.sections)
    ]
    return "\n\n".join(sections)
```

Prefer structured Pydantic results between LLM steps. They make validation explicit and preserve useful static types across the pipeline.

When Codex is installed, AutoDef's automatic provider selects it. Codex runs launched without an explicit working directory use the nearest Git root, so examples can be run from nested folders such as `examples/flows`. If no Git repository is available, AutoDef uses Codex's repo-check bypass and keeps the current directory as the workspace. The default Codex model is `gpt-5.6-luna` with medium reasoning; set `AUTODEF_CODEX_MODEL` or `AUTODEF_CODEX_REASONING_EFFORT` to override those defaults. An explicit Codex config value takes precedence over AutoDef's fallback.

## Explicit retries

Steps do not retry by default. Use `retry()` when an operation is safe to repeat:

```python
from autodef import RetryPolicy, retry

response = retry(
    RetryPolicy(
        attempts=4,
        delay=0.5,
        backoff=2,
        exceptions=(ConnectionError, TimeoutError),
    ),
    lambda: call_service(request),
    name="call_service",
)
```

`attempts` is the total number of invocations, including the first. `delay` is the wait before the first retry, and each later delay is multiplied by `backoff`. Only exceptions listed in `exceptions` are retried. Each invocation becomes an `AttemptRun` under one `StepRun`.

Retry policies should only cover transient failures and idempotent operations. AutoDef does not infer whether an operation is safe to repeat.

## Flow-level retry

A failed or stopped run can restart the entire flow with its original arguments:

```python
from autodef import RunStatus

failed = import_document(raw_text)

if failed.status in {RunStatus.FAILED, RunStatus.STOPPED}:
    replacement = failed.retry()
    assert replacement.retry_of is failed
```

The original run remains immutable history. Flow-level retry does not resume from a failed step or reuse intermediate values.

For asynchronous flows, await an inline retry:

```python
replacement = await failed.retry()
```

Pass `background=True` to either sync or async `retry()` to start the replacement in the background. The async method itself is awaited to obtain the new live run.

## Background execution and stopping

Synchronous calls run inline by default. Use `.start()` to opt into background execution:

```python
run = import_document.start(raw_text)

print(run.status)
document_count = run.result(timeout=10)
```

`run.stop()` requests cancellation and returns whether the request was accepted. Synchronous cancellation is cooperative: AutoDef checks before steps and retry attempts, and retry delays wake early. Python cannot safely terminate an arbitrary synchronous function that is already executing. If that function returns after a stop request, the flow becomes stopped before publishing a result.

Async background flows cancel their active task where possible. The called coroutine must not suppress `asyncio.CancelledError` indefinitely.

Requesting the result of a stopped flow raises `FlowStoppedError`.

## Async flows

Decorating `async def` preserves async execution:

```python
@flow
async def download(url: str) -> bytes:
    return await step(lambda: client.get(url), name="download")

completed = await download("https://example.com/data")
content = completed.result()

live = download.start("https://example.com/large-data")
content = await live
```

An inline async flow call must be awaited to obtain its completed run. A live `FlowRun` is also awaitable and yields its typed result. Do not call blocking `result()` on a live async run from the same event loop; AutoDef raises an error directing you to await it instead.

A synchronous flow cannot execute an async step. Make the flow itself async and await the step.

## Inspecting executions

`FlowRun[R]` exposes:

| Attribute or method | Meaning |
| --- | --- |
| `status` | Current `RunStatus`. |
| `result(timeout=None)` | Wait for and return `R`, or raise the recorded failure. |
| `error` | The captured exception for a failed run. |
| `steps` | A snapshot of recorded `StepRun` objects. |
| `started_at`, `finished_at`, `duration` | Monotonic timing data in seconds. |
| `retry_of` | The earlier run when this is a whole-flow retry. |
| `stop()` | Request cooperative cancellation. |
| `retry(background=False)` | Restart a failed or stopped flow. |

Each `StepRun` contains its `name`, operation, status, result, error, timings, attempts, and optional `child_run`. Each `AttemptRun` records the same outcome and timing information for one retry attempt.

Possible statuses are `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `STOP_REQUESTED`, and `STOPPED`.

Arguments captured by operations and generated results remain in memory for inspection. Runs are not persisted, serialized, or sent to an external tracing service.

## Failure behavior

```python
run = failing_flow()

assert run.status is RunStatus.FAILED
assert run.error is not None
run.result()  # Re-raises the original exception.
```

This separation ensures the failed execution remains available for inspection and whole-flow retry. Exceptions derived directly from `BaseException`, such as `KeyboardInterrupt` and `SystemExit`, are not converted into ordinary failed runs.

`step()` and `retry()` raise `RuntimeError` when used outside an active flow because there would be no `FlowRun` in which to record them.

## Current scope

Flows are local and in-memory. The current API does not provide persisted state, resume-from-step, distributed workers, forced termination of synchronous code, or a pre-execution graph. Normal Python control flow and explicit observable boundaries keep the initial model small and strongly typed.

See all runnable demonstrations in the [flow examples](../examples/README.md#flows).
