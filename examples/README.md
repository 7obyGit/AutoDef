# AutoDef examples

Examples are grouped by the feature they demonstrate. Run them from the repository root so local files and caches resolve consistently:

```bash
uv run python examples/flows/basic.py
```

Most `impl`, `llm`, and `shim` examples call the configured model provider. See the [main README](../README.md#configuration) before running them. The local flow examples do not require an LLM.

## Flows

- [`flows/basic.py`](flows/basic.py) — typed results, ordinary decisions and loops, step history, and timing.
- [`flows/composition.py`](flows/composition.py) — nesting one flow inside another and inspecting child runs.
- [`flows/retries.py`](flows/retries.py) — explicit attempts, exception filtering, delay, and backoff.
- [`flows/failures.py`](flows/failures.py) — failed-run inspection and whole-flow restart.
- [`flows/async_background.py`](flows/async_background.py) — async steps, background execution, awaiting results, and stopping.
- [`flows/llm_pipeline.py`](flows/llm_pipeline.py) — a structured plan/research/report pipeline built from `@llm` functions.

Read the complete [flows guide](../docs/flows.md) for the API contract and failure semantics.

## Other features

- [`impl/basic.py`](impl/basic.py) — generate and cache a typed implementation.
- [`impl/error_correction.py`](impl/error_correction.py) — regenerate a failing implementation.
- [`impl/with_llm.py`](impl/with_llm.py) — generate procedural code that delegates natural-language work to `@llm`.
- [`llm/basic.py`](llm/basic.py) — text and structured LLM responses.
- [`llm/images.py`](llm/images.py) — image arguments from paths and Pillow.
- [`llm/paths.py`](llm/paths.py) — include file metadata and contents in a request.
- [`shim/basic.py`](shim/basic.py) — repair a function after a runtime error.
- [`task/basic.py`](task/basic.py) — delegate a repository change to Codex.
- [`classes/methods.py`](classes/methods.py) — decorators on instance, class, and static methods.

The sample image used by the multimodal example lives under [`assets`](assets/).
