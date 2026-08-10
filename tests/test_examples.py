import asyncio
import re
from pathlib import Path

import pytest

from autodef import FlowStoppedError, RunStatus
from examples.flows import async_background, basic, composition, failures, llm_pipeline, retries

PROJECT_ROOT = Path(__file__).parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


def test_every_python_example_compiles() -> None:
    example_files = sorted((PROJECT_ROOT / "examples").rglob("*.py"))
    assert example_files

    for example_file in example_files:
        source = example_file.read_text(encoding="utf-8")
        compile(source, example_file, "exec")


@pytest.mark.parametrize(
    "markdown_file",
    [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs" / "flows.md",
        PROJECT_ROOT / "examples" / "README.md",
    ],
)
def test_local_documentation_links_exist(markdown_file: Path) -> None:
    for raw_target in MARKDOWN_LINK.findall(markdown_file.read_text(encoding="utf-8")):
        target = raw_target.strip("<>")
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue

        relative_path = target.partition("#")[0]
        assert (markdown_file.parent / relative_path).exists(), (
            f"{markdown_file.relative_to(PROJECT_ROOT)} links to missing path {relative_path}"
        )


def test_basic_flow_example() -> None:
    run = basic.summarize_numbers([2, -1, 3, 4])

    summary = run.result()
    assert summary.squares == [4, 9, 16]
    assert summary.total == 29
    assert summary.average == pytest.approx(29 / 3)
    assert run.status is RunStatus.SUCCEEDED
    assert [record.name for record in run.steps] == [
        "remove_negatives",
        "square_0",
        "square_1",
        "square_2",
        "total",
        "average",
    ]


def test_composition_example_retains_child_run() -> None:
    run = composition.create_invoice([12.50, 3.25, 8.00], 0.2)

    assert run.result() == composition.Invoice(subtotal=23.75, tax=4.75, total=28.5)
    child_run = run.steps[0].child_run
    assert child_run is not None
    assert child_run.result() == 23.75
    assert [record.name for record in child_run.steps] == ["sum_prices"]


def test_step_retry_example_records_failures_and_success() -> None:
    retries.attempt_count = 0

    run = retries.fetch_data()

    assert run.result() == "service response"
    assert [attempt.status for attempt in run.steps[0].attempts] == [
        RunStatus.FAILED,
        RunStatus.FAILED,
        RunStatus.SUCCEEDED,
    ]


def test_failure_example_restarts_the_whole_flow() -> None:
    failures.invocations = 0

    failed = failures.temporarily_broken(21)
    replacement = failed.retry()

    assert failed.status is RunStatus.FAILED
    assert isinstance(failed.error, RuntimeError)
    assert replacement.result() == 42
    assert replacement.retry_of is failed


def test_async_example_executes_typed_steps() -> None:
    async def execute() -> None:
        run = await async_background.fetch_all(["one", "two"])

        assert run.result() == ["content from one", "content from two"]
        assert [record.name for record in run.steps] == ["fetch_0", "fetch_1"]

        background = async_background.fetch_all.start(["one", "two", "three"])
        await asyncio.sleep(0.15)
        assert background.stop()
        with pytest.raises(FlowStoppedError):
            await background
        assert background.status is RunStatus.STOPPED

    asyncio.run(execute())


def test_llm_pipeline_example_with_mocked_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    questions = ["What is typed?", "What is observable?"]

    def make_plan(topic: str) -> llm_pipeline.ResearchPlan:
        return llm_pipeline.ResearchPlan(topic=topic, questions=questions)

    def answer(topic: str, question: str) -> llm_pipeline.Finding:
        return llm_pipeline.Finding(question=question, answer=f"{topic}: {question}")

    def write(topic: str, findings: list[llm_pipeline.Finding]) -> llm_pipeline.Report:
        return llm_pipeline.Report(title=topic, summary="Complete", findings=findings)

    monkeypatch.setattr(llm_pipeline, "plan_research", make_plan)
    monkeypatch.setattr(llm_pipeline, "answer_question", answer)
    monkeypatch.setattr(llm_pipeline, "write_report", write)

    run = llm_pipeline.research("Typed flows")

    assert run.result() == llm_pipeline.Report(
        title="Typed flows",
        summary="Complete",
        findings=[llm_pipeline.Finding(question=question, answer=f"Typed flows: {question}") for question in questions],
    )
    assert [record.name for record in run.steps] == [
        "plan",
        "answer_1",
        "answer_2",
        "write_report",
    ]
