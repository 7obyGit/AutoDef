from autodef import auto, func

def test_autodef_placeholder() -> None:
    @auto
    def my_func() -> None:
        pass
    
    assert my_func() is None

def test_func_placeholder() -> None:
    @func
    def my_llm_func() -> None:
        pass
    
    assert my_llm_func() is None
