"""RadAI — Subagent Orchestration Helper.

This module provides utilities to record the execution state of AI pipelines
in a format that specialized agentic subagents can easily monitor.
"""

import json
import time
from pathlib import Path
from typing import Any


class SubagentStateLogger:
    """Logs pipeline state to a JSON file for agentic monitoring."""

    def __init__(self, log_dir: Path, pipeline_id: str):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"pipeline_{pipeline_id}.json"
        self.state = {
            "pipeline_id": pipeline_id,
            "start_time": time.time(),
            "last_update": time.time(),
            "status": "initialized",
            "steps": [],
        }
        self._save()

    def _save(self):
        self.state["last_update"] = time.time()
        with open(self.log_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_step_start(self, step_name: str, details: dict[str, Any] | None = None):
        """Record the start of a pipeline step."""
        step = {
            "name": step_name,
            "status": "in_progress",
            "start_time": time.time(),
            "details": details or {},
        }
        self.state["steps"].append(step)
        self.state["status"] = f"running_{step_name}"
        self._save()

    def log_step_complete(self, step_name: str, result_summary: str | None = None):
        """Record the completion of a pipeline step."""
        for step in self.state["steps"]:
            if step["name"] == step_name and step["status"] == "in_progress":
                step["status"] = "completed"
                step["end_time"] = time.time()
                step["duration"] = step["end_time"] - step["start_time"]
                step["result"] = result_summary
                break
        self._save()

    def log_error(self, step_name: str, error: str):
        """Record an error in the pipeline."""
        for step in self.state["steps"]:
            if step["name"] == step_name:
                step["status"] = "failed"
                step["error"] = error
                break
        self.state["status"] = "failed"
        self._save()

    def finalize(self, status: str = "completed"):
        """Finalize the pipeline log."""
        self.state["status"] = status
        self.state["end_time"] = time.time()
        self.state["total_duration"] = self.state["end_time"] - self.state["start_time"]
        self._save()
