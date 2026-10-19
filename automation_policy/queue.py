"""Pure state-transition queue. Never executes effects, mail, trades, deploys or DB writes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List
from .gate import evaluate

TRANSITIONS = {
    "READY": {"RUNNING", "BLOCKED_EXTERNAL"},
    "RUNNING": {"VERIFYING", "RETRY_WAIT", "BLOCKED_EXTERNAL", "FAILED_TERMINAL"},
    "VERIFYING": {"DONE", "RETRY_WAIT", "FAILED_TERMINAL"},
    "RETRY_WAIT": {"READY", "FAILED_TERMINAL"},
    "BLOCKED_EXTERNAL": {"READY", "FAILED_TERMINAL"},
    "DONE": set(),
    "FAILED_TERMINAL": set(),
}

@dataclass
class Task:
    task_id: str
    action: str
    state: str = "READY"
    attempts: int = 0
    max_attempts: int = 3
    evidence: dict = field(default_factory=dict)
    history: List[dict] = field(default_factory=list)

    def transition(self, target: str, reason: str) -> None:
        if target not in TRANSITIONS[self.state]:
            raise ValueError(f"illegal_transition:{self.state}->{target}")
        self.history.append({"from": self.state, "to": target, "reason": reason,
                             "at": datetime.now(timezone.utc).isoformat()})
        self.state = target

class Queue:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def add(self, task: Task) -> None:
        if not task.task_id or task.task_id in self.tasks:
            raise ValueError("missing_or_duplicate_task_id")
        if task.max_attempts < 1:
            raise ValueError("invalid_max_attempts")
        self.tasks[task.task_id] = task

    def claim(self, task_id: str) -> dict:
        task = self.tasks[task_id]
        if task.state != "READY":
            return {"claimed": False, "reason": "not_ready"}
        decision = evaluate(task.action, task.evidence)
        if not decision["allowed"]:
            task.transition("BLOCKED_EXTERNAL", decision["reason"])
            return {"claimed": False, **decision}
        if task.attempts >= task.max_attempts:
            task.transition("BLOCKED_EXTERNAL", "attempt_budget_exhausted")
            return {"claimed": False, "reason": "attempt_budget_exhausted"}
        task.attempts += 1
        task.transition("RUNNING", "policy_allowed")
        return {"claimed": True, "task_id": task_id, "attempt": task.attempts}

    def result(self, task_id: str, *, execution_ok: bool, verified: bool = False) -> None:
        task = self.tasks[task_id]
        if task.state != "RUNNING":
            raise ValueError("result_requires_running")
        if not execution_ok:
            task.transition("RETRY_WAIT" if task.attempts < task.max_attempts else "FAILED_TERMINAL", "execution_failed")
            return
        task.transition("VERIFYING", "execution_succeeded")
        task.transition("DONE" if verified else "FAILED_TERMINAL", "verification_passed" if verified else "verification_failed")

    def retry(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.state != "RETRY_WAIT":
            raise ValueError("retry_requires_wait")
        task.transition("READY", "retry_scheduled")
