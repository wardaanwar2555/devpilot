from app.tools.static_analyzer import analyze_files, analyze_source

BUGGY = '''
def add(item, bucket=[]):
    bucket.append(item)
    return bucket

def load():
    try:
        return int("x")
    except:
        pass  # TODO handle

def check(x):
    if x == None:
        return undefined_name
'''

CLEAN = '''
def add(item, bucket=None):
    bucket = [] if bucket is None else bucket
    bucket.append(item)
    return bucket
'''


def rules(findings):
    return {f["rule_id"] for f in findings}


def test_ast_detects_known_issues():
    found = analyze_source(BUGGY, "m.py")
    assert {"devpilot.mutable-default", "devpilot.bare-except", "devpilot.todo"} <= rules(found)
    bare = next(f for f in found if f["rule_id"] == "devpilot.bare-except")
    assert bare["line"] == 9 and bare["evidence"] == "except:" and not bare["confirmed"]


def test_syntax_error_is_confirmed_and_only_finding():
    found = analyze_source("def broken(:\n    pass\n", "bad.py")
    assert len(found) == 1 and found[0]["confirmed"] and found[0]["category"] == "syntax"


def test_clean_code_has_no_fabricated_findings():
    findings, _ = analyze_files([{"path": "clean.py", "content": CLEAN}])
    assert [f for f in findings if f["severity"] != "info"] == []


def test_external_tools_run_and_dedupe():
    findings, status = analyze_files([{"path": "m.py", "content": BUGGY}])
    assert status["ruff"] == "ok" and status["bandit"] == "ok"
    assert "F821" in rules(findings)  # undefined name, from ruff
    assert len({f["id"] for f in findings}) == len(findings)
    assert findings[0]["severity"] in ("high", "critical")  # sorted by severity


def test_bandit_security_finding_and_secret_redaction():
    src = 'import subprocess\nPASSWORD = "supersecret123"\nsubprocess.call("ls " + input(), shell=True)\n'
    findings, _ = analyze_files([{"path": "s.py", "content": src}])
    sec = [f for f in findings if f["source"] == "bandit"]
    assert sec
    assert all("supersecret123" not in f["evidence"] + f["details"] for f in findings)
