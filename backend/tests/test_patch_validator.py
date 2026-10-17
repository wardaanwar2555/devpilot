import pytest

from app.tools.patch_validator import PatchError, apply_snippet, check_path, diff_paths, validate_patch

FILES = {"src/calc.py": "def div(a, b):\n    return a / b\n"}


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "C:\\x.py", "src\\calc.py", "other.py", ""])
def test_rejects_bad_paths(path):
    assert check_path(path, set(FILES)) is not None


def test_accepts_known_path():
    assert check_path("src/calc.py", set(FILES)) is None


def test_snippet_must_be_unique_and_present():
    with pytest.raises(PatchError):
        apply_snippet("a\na\n", "a\n", "b\n")
    with pytest.raises(PatchError):
        apply_snippet("a\n", "zzz", "b")


def test_valid_patch_builds_diff():
    proposal = {"file": "src/calc.py", "old_snippet": "    return a / b\n",
                "new_snippet": "    if b == 0:\n        raise ValueError('b is zero')\n    return a / b\n"}
    validation, patched, diff = validate_patch(FILES, proposal)
    assert validation.ok and validation.lines_added == 2
    assert diff_paths(diff) == {"src/calc.py"} and "ValueError" in patched


def test_rejects_syntax_breaking_patch_and_oversize():
    bad = {"file": "src/calc.py", "old_snippet": "    return a / b\n", "new_snippet": "    return a /\n"}
    assert not validate_patch(FILES, bad)[0].ok
    big = {"file": "src/calc.py", "old_snippet": "    return a / b\n", "new_snippet": "    x = 1\n" * 100 + "    return a / b\n"}
    assert "limit" in " ".join(validate_patch(FILES, big, 80)[0].problems)


def test_rejects_noop_and_foreign_file():
    assert not validate_patch(FILES, {"file": "src/calc.py", "old_snippet": "a / b", "new_snippet": "a / b"})[0].ok
    assert not validate_patch(FILES, {"file": "evil.py", "new_content": "x=1"})[0].ok
