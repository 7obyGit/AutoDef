from autodef import impl, llm, shim


class MathWizard:
    def __init__(self, base_value: int):
        self.base_value = base_value

    @llm(debug=True)  # type: ignore[untyped-decorator]
    def describe_state(self) -> str:
        """Provide a natural language description of the current state of the wizard, mentioning the base_value."""
        return ""

    @impl(debug=True)  # type: ignore[untyped-decorator]
    def calculate_power(self, exponent: int) -> int:
        """Calculate self.base_value raised to the power of exponent."""
        return 0

    @shim(debug=True)  # type: ignore[untyped-decorator]
    def tricky_operation(self, divisor: int) -> float:
        """
        Divide self.base_value by divisor.
        Note: This might fail if divisor is 0, please handle it or provide a shim.
        """
        return self.base_value / divisor

    @staticmethod
    @llm(debug=True)  # type: ignore[untyped-decorator]
    def general_info(topic: str) -> str:
        """Return some interesting facts about the given math topic."""
        return ""

    @classmethod
    @llm(debug=True)  # type: ignore[untyped-decorator]
    def class_identity(cls) -> str:
        """Describe what kind of class this is, based on its name."""
        return ""


def main() -> None:
    # 1. Test Instance Methods with State
    wizard = MathWizard(42)
    print("--- Instance Methods ---")
    print(f"Description: {wizard.describe_state()}")
    print(f"42^2 = {wizard.calculate_power(2)}")

    # 2. Test Shim with Recovery (Division by Zero)
    print("\n--- Shim Recovery ---")
    try:
        # This will trigger the shim since divisor is 0
        result = wizard.tricky_operation(0)
        print(f"Result of 42/0 (handled by shim): {result}")
    except Exception as e:
        print(f"Failed to handle 42/0: {e}")

    # 3. Test Static and Class Methods
    print("\n--- Static & Class Methods ---")
    print(f"Static info: {MathWizard.general_info('calculus')}")
    print(f"Class identity: {MathWizard.class_identity()}")


if __name__ == "__main__":
    # Clear cache for a clean run
    import shutil
    from pathlib import Path

    for d in [
        "describe_state",
        "calculate_power",
        "tricky_operation",
        "general_info",
        "class_identity",
    ]:
        p = Path(".autodef_cache") / d
        if p.exists():
            shutil.rmtree(p)
        p_shim = Path(".autodef_cache") / f"{d}_shim"
        if p_shim.exists():
            shutil.rmtree(p_shim)

    main()
