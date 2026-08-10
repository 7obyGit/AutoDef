"""Chain structured LLM functions in an observable, typed flow."""

from functools import partial

from pydantic import BaseModel

from autodef import flow, llm, step


class ResearchPlan(BaseModel):
    topic: str
    questions: list[str]


class Finding(BaseModel):
    question: str
    answer: str


class Report(BaseModel):
    title: str
    summary: str
    findings: list[Finding]


@llm
def plan_research(topic: str) -> ResearchPlan:
    """Create three focused research questions for the topic."""
    return ResearchPlan(topic="", questions=[])


@llm
def answer_question(topic: str, question: str) -> Finding:
    """Answer one research question concisely and accurately."""
    return Finding(question="", answer="")


@llm
def write_report(topic: str, findings: list[Finding]) -> Report:
    """Turn the findings into a concise report with a useful title and summary."""
    return Report(title="", summary="", findings=[])


@flow(silent=False)
def research(topic: str) -> Report:
    plan = step(lambda: plan_research(topic), name="plan")
    findings: list[Finding] = [
        step(
            partial(answer_question, topic, question),
            name=f"answer_{index}",
        )
        for index, question in enumerate(plan.questions, start=1)
    ]
    report: Report = step(partial(write_report, topic, findings), name="write_report")
    return report


if __name__ == "__main__":
    run = research("How typed workflows improve LLM application reliability")

    print(run.result().model_dump_json(indent=2))
    print("\nExecuted steps:")
    for recorded_step in run.steps:
        print(f"- {recorded_step.name}: {recorded_step.status}")
