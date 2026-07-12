from pydantic import BaseModel

from autodef import impl, llm


class Plan(BaseModel):
    task: str
    steps: list[str]
    context: str


@llm
def plan(task: str) -> Plan:
    """
    Generate a plan for how to execute the task given

    The plan should be separated into independent steps, where each step is a description containing the information needed to complete that step

    The context should be provided to every step of the plan, provide shared information here

    :param task:
    :return:
    """
    return Plan(task="", steps=[], context="")


@llm
def execute_step(step: str) -> str:
    return ""


@impl
def execute_plan(plan: Plan) -> str:
    """
    Execute the plan to complete the task

    Each step of the plan should be passed to an execute step function where an LLM can perform the step

    :param plan:
    :return:
    """
    return ""


@impl
def execute_task(task: str) -> str:
    """
    Execute the task by creating and then executing a plan

    :param task:
    :return: The finished solution
    """
    return ""


if __name__ == "__main__":
    print("Running chain example...")
    print(execute_task("Write a Python program that prints 'Hello, World!'"))
    print("Complete!")
