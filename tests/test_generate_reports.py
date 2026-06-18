from __future__ import annotations

import json

from scripts.generate_reports import _build_aggregate, _build_per_task_rows, _iter_trials


def _write_result(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _trial(task_name: str, trial_name: str, reward, exception_info=None):
    verifier_result = None
    if reward is not None:
        verifier_result = {"rewards": {"reward": reward}}
    return {
        "trial_name": trial_name,
        "task_name": task_name,
        "agent_info": {"model_info": {"provider": "deepseek", "name": "deepseek-v4-pro"}},
        "agent_result": {
            "metadata": {"provider": "deepseek", "model": "deepseek-v4-pro"},
            "n_input_tokens": 1,
            "n_cache_tokens": 2,
            "n_output_tokens": 3,
        },
        "verifier_result": verifier_result,
        "exception_info": exception_info,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:10Z",
    }


def test_reports_count_harbor_exception_schema_and_missing_rewards_as_zero(tmp_path):
    run_dir = tmp_path / "run"
    _write_result(
        run_dir / "job" / "job" / "passed__abc" / "result.json",
        _trial("passed", "passed__abc", 1.0),
    )
    _write_result(
        run_dir / "job" / "job" / "failed__abc" / "result.json",
        _trial("failed", "failed__abc", 0.0),
    )
    _write_result(
        run_dir / "job" / "job" / "timeout__abc" / "result.json",
        _trial(
            "timeout",
            "timeout__abc",
            None,
            {
                "exception_type": "AgentTimeoutError",
                "exception_message": "Agent execution timed out",
            },
        ),
    )
    _write_result(
        run_dir / "job" / "job" / "result.json",
        {"stats": {"n_completed_trials": 3}},
    )

    trials = _iter_trials(run_dir)
    per_task = _build_per_task_rows(trials)
    aggregate = _build_aggregate(trials, per_task)

    assert len(trials) == 3
    assert aggregate["n_trials"] == 3
    assert aggregate["n_errors"] == 1
    assert aggregate["exceptions"] == {"AgentTimeoutError": 1, "none": 2}
    assert aggregate["mean_reward"] == 1 / 3

    timeout_row = next(row for row in trials if row["task_name"] == "timeout")
    assert timeout_row["reward"] is None
    assert timeout_row["score_reward"] == 0.0
    assert timeout_row["exception_type"] == "AgentTimeoutError"
    assert (
        timeout_row["failure_summary"]
        == "Exception: AgentTimeoutError Agent execution timed out"
    )


def test_reports_extract_verifier_failure_and_agent_artifacts(tmp_path):
    run_dir = tmp_path / "run"
    trial_dir = run_dir / "job" / "job" / "train-fasttext__abc"
    _write_result(
        trial_dir / "result.json",
        _trial("train-fasttext", "train-fasttext__abc", 0.0),
    )
    _write_result(
        trial_dir / "verifier" / "ctrf.json",
        {
            "results": {
                "tests": [
                    {
                        "name": "test_outputs.py::test_accuracy",
                        "status": "failed",
                        "trace": (
                            "def test_accuracy():\n"
                            ">       assert accuracy > ACCURACY_THRESHOLD\n"
                            "E       assert 0.619625 > 0.62\n"
                        ),
                    },
                    {
                        "name": "test_outputs.py::test_model_size",
                        "status": "passed",
                    },
                ]
            }
        },
    )
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "agent" / "wattle-exit-status.txt").write_text("0\n", encoding="utf-8")
    (trial_dir / "agent" / "wattle-output.log").write_text(
        "Saved /app/model.bin\nAccuracy: 0.6244\n",
        encoding="utf-8",
    )

    [row] = _iter_trials(run_dir)

    assert row["failed_tests"] == "test_outputs.py::test_accuracy"
    assert "assert 0.619625 > 0.62" in row["verifier_failure_snippets"]
    assert row["agent_exit_status"] == "0"
    assert "Accuracy: 0.6244" in row["agent_output_tail"]
    assert row["failure_summary"].startswith(
        "Verifier failed: test_outputs.py::test_accuracy"
    )


def test_reports_include_exception_traceback_tail(tmp_path):
    run_dir = tmp_path / "run"
    _write_result(
        run_dir / "job" / "job" / "timeout__abc" / "result.json",
        _trial(
            "timeout",
            "timeout__abc",
            None,
            {
                "exception_type": "AgentTimeoutError",
                "exception_message": "Agent execution timed out",
                "exception_traceback": "line 1\nline 2\nroot cause",
            },
        ),
    )

    [row] = _iter_trials(run_dir)

    assert row["exception_traceback_tail"] == "line 1\nline 2\nroot cause"


def test_reports_recognize_codex_job_name_prefix(tmp_path):
    run_dir = tmp_path / "run"
    _write_result(
        run_dir
        / "jobs"
        / "codex-codex-gpt-5.5-high"
        / "codex-codex-gpt-5.5-high"
        / "train-fasttext__abc"
        / "result.json",
        _trial("train-fasttext", "train-fasttext__abc", 1.0),
    )

    trials = _iter_trials(run_dir)

    assert trials[0]["job_name"] == "codex-codex-gpt-5.5-high"
