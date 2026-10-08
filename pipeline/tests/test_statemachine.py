"""Static checks on statemachine.asl.json: wiring, retries, catches and substitutions."""
import json
import re
from pathlib import Path

import pytest

ASL_PATH = Path(__file__).resolve().parents[1] / "statemachine.asl.json"
TEMPLATE = (Path(__file__).resolve().parents[1] / "template.yaml").read_text()
ASL = json.loads(ASL_PATH.read_text())
STATES = ASL["States"]
INNER = STATES["TranscribeWindows"]["ItemProcessor"]["States"]


def targets(states):
    for name, s in states.items():
        for key in ("Next", "Default"):
            if key in s:
                yield name, s[key]
        for c in s.get("Choices", []) + s.get("Catch", []):
            yield name, c["Next"]


def test_all_transitions_exist():
    for name, target in targets(STATES):
        assert target in STATES, f"{name} -> {target}"


def test_all_states_reachable():
    seen, todo = set(), [ASL["StartAt"]]
    edges = {}
    for name, target in targets(STATES):
        edges.setdefault(name, []).append(target)
    while todo:
        s = todo.pop()
        if s not in seen:
            seen.add(s)
            todo.extend(edges.get(s, []))
    assert seen == set(STATES)


def test_timeout():
    assert ASL["TimeoutSeconds"] == 3600


TASKS = [n for n, s in STATES.items() if s["Type"] == "Task"]


@pytest.mark.parametrize("name", TASKS + ["TranscribeWindow"])
def test_tasks_retry_throttling(name):
    state = STATES.get(name) or INNER[name]
    assert state["Resource"] == "arn:aws:states:::lambda:invoke"
    assert state["Retry"][0]["ErrorEquals"] == ["ThrottlingException"]
    assert "Lambda.TooManyRequestsException" in state["Retry"][1]["ErrorEquals"]


@pytest.mark.parametrize("name", [n for n in TASKS if n not in ("ParseEvent", "MarkFailed")] + ["TranscribeWindows"])
def test_failures_go_to_mark_failed(name):
    assert STATES[name]["Catch"] == [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "MarkFailed"}]


def test_parse_event_and_mark_failed_have_no_catch():
    assert "Catch" not in STATES["ParseEvent"]
    assert "Catch" not in STATES["MarkFailed"]
    assert "Catch" not in INNER["TranscribeWindow"]


def test_map_runs_two_windows():
    m = STATES["TranscribeWindows"]
    assert m["MaxConcurrency"] == 2
    assert m["ItemsPath"] == "$.split.windows"
    assert m["ResultPath"] == "$.windowResults"


def test_mark_failed_passes_cause():
    payload = STATES["MarkFailed"]["Parameters"]["Payload"]
    assert payload["status"] == "FAILED"
    assert payload["errorMessage.$"] == "$.error.Cause"


def test_substitutions_defined_in_template():
    used = set(re.findall(r"\$\{(\w+)\}", ASL_PATH.read_text()))
    assert used == {"ParseEventFnArn", "SplitAudioFnArn", "TranscribeWindowFnArn", "AssembleAudioTextFnArn",
                    "ExtractPdfFnArn", "UpdateStatusFnArn", "ChunkFnArn", "SummarizeFnArn", "IndexFnArn"}
    for name in used:
        assert f"        {name}:" in TEMPLATE
