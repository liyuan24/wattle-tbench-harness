import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "analyze_wattle_tbench.py"
SPEC = importlib.util.spec_from_file_location("analyze_wattle_tbench", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
analyzer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


def _write_run(tmp_path: Path, *, agent_log: str = "") -> Path:
    run_dir = tmp_path / "sample-run"
    trial_dir = run_dir / "sample-task" / "sample-task.1-of-1.sample-run"
    (trial_dir / "sessions").mkdir(parents=True)
    if agent_log:
        (trial_dir / "sessions" / "agent.log").write_text(agent_log, encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "task_id": "sample-task",
                        "trial_name": "sample-task.1-of-1.sample-run",
                        "is_resolved": False,
                        "failure_mode": "unset",
                        "agent_started_at": "2026-05-22T20:40:11+00:00",
                        "agent_ended_at": "2026-05-22T20:40:38+00:00",
                        "trial_started_at": "2026-05-22T20:40:06+00:00",
                        "trial_ended_at": "2026-05-22T20:40:57+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_analyze_run_extracts_agent_exception_from_log(tmp_path: Path) -> None:
    run_dir = _write_run(
        tmp_path,
        agent_log=(
            "Traceback (most recent call last):\n"
            "  File \"/root/.local/bin/wattle\", line 10, in <module>\n"
            "openai.BadRequestError: Error code: 400 - bad reasoning_content\n"
        ),
    )

    rows = analyzer.analyze_run(run_dir)

    assert rows[0].exception_type == "BadRequestError"
    assert rows[0].exception_message == "Error code: 400 - bad reasoning_content"


def test_summary_counts_exception_types(tmp_path: Path) -> None:
    run_dir = _write_run(
        tmp_path,
        agent_log="openai.BadRequestError: Error code: 400 - bad reasoning_content\n",
    )

    summary = analyzer.summarize(analyzer.analyze_run(run_dir))

    assert summary["runs"]["sample-run"]["exceptions"] == {"BadRequestError": 1}


def test_analyze_run_ignores_tool_result_exceptions_in_embedded_jsonl(tmp_path: Path) -> None:
    run_dir = _write_run(
        tmp_path,
        agent_log=(
            '{"type":"message","message":{"role":"user","content":'
            '[{"type":"tool_result","content":"Traceback (most recent call last):\\n'
            'TypeError: task command failed"}]}}\n'
        ),
    )

    rows = analyzer.analyze_run(run_dir)

    assert rows[0].exception_type is None
    assert rows[0].exception_message is None
