"""Declarative DAG validation and readiness calculation. Never executes external effects."""
from dataclasses import dataclass
from .gate import evaluate

@dataclass(frozen=True)
class Step:
    id: str
    action: str
    needs: tuple[str, ...] = ()

def validate(steps: list[Step]) -> list[str]:
    by_id = {s.id: s for s in steps}
    if len(by_id) != len(steps) or any(not s.id for s in steps):
        raise ValueError("duplicate_or_empty_step_id")
    for step in steps:
        for dep in step.needs:
            if dep not in by_id:
                raise ValueError(f"unknown_dependency:{dep}")
        if not evaluate(step.action)["allowed"]:
            raise ValueError(f"action_not_allowed_for_unattended_plan:{step.action}")
    result, visiting, visited = [], set(), set()
    def visit(step_id):
        if step_id in visiting:
            raise ValueError("dependency_cycle")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dep in by_id[step_id].needs:
            visit(dep)
        visiting.remove(step_id)
        visited.add(step_id)
        result.append(step_id)
    for step in steps:
        visit(step.id)
    return result

def ready(steps: list[Step], completed: set[str], failed: set[str] | None = None) -> list[str]:
    failed = failed or set()
    order = validate(steps)
    by_id = {s.id: s for s in steps}
    if not completed.issubset(by_id.keys()) or not failed.issubset(by_id.keys()):
        raise ValueError("unknown_task_state")
    if completed & failed:
        raise ValueError("conflicting_task_state")
    return [sid for sid in order if sid not in completed and sid not in failed
            and all(dep in completed for dep in by_id[sid].needs)]
