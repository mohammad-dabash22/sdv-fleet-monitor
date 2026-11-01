"""Exit codes: 0 clean, 1 violations, 2 input errors (2 wins over 1)."""
from .conftest import check, deployment, run


def test_clean_exits_0():
    assert check(deployment()).code == 0


def test_violation_exits_1():
    assert check(deployment(image="a:latest")).code == 1


def test_input_error_exits_2():
    assert check("a: [b\n").code == 2


def test_input_error_with_violations_exits_2(write):
    bad = write("v.yaml", deployment(image="a:latest"))
    broken = write("broken.yaml", "a: [b\n")
    assert run([bad, broken]).code == 2
