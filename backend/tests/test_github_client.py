import pytest

from app.tools.github_client import is_eligible_path, parse_repo_url, select_eligible
from app.tools.secrets import redact


def test_parse_valid_urls():
    assert parse_repo_url("https://github.com/psf/requests") == ("psf", "requests")
    assert parse_repo_url("https://github.com/psf/requests.git/") == ("psf", "requests")


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a",
                                 "https://github.com/a/b/tree/main", "git@github.com:a/b.git", "https://github.com/../b"])
def test_rejects_invalid_urls(url):
    with pytest.raises(ValueError):
        parse_repo_url(url)


def test_eligibility_rules():
    assert is_eligible_path("src/app.py")
    for bad in ["node_modules/x.py", ".venv/lib/x.py", "src/secrets.py", "src/.env.py", "a_pb2.py", "README.md", "../x.py"]:
        assert not is_eligible_path(bad), bad


def test_select_respects_limits_and_prefers_source_over_tests():
    tree = [{"path": f"pkg/m{i}.py", "type": "blob", "size": 100} for i in range(5)]
    tree += [{"path": "tests/test_a.py", "type": "blob", "size": 10}, {"path": "huge.py", "type": "blob", "size": 10**7}]
    chosen = select_eligible(tree, max_files=3, max_file_bytes=1000, max_total_bytes=10_000)
    assert len(chosen) == 3 and all("test" not in c["path"] for c in chosen)


def test_redact_removes_credentials():
    text = 'key = "AKIAABCDEFGHIJKLMNOP"\napi_key = "abcdef123456"\nx = 1'
    out = redact(text)
    assert "AKIAABCDEFGHIJKLMNOP" not in out and "abcdef123456" not in out and "x = 1" in out
