"""Ratchet on QML property drilling through the graph-canvas pass-through hubs.

The graph-canvas decomposition campaign replaces "re-drill every canvas fact
through GraphNodeHost / GraphCanvas projections" with shared Facts objects
passed by reference. This test pins the drilling level so it can only go
down:

- over budget  -> fail: a new drilled pass-through was added; route the fact
  through the matching Facts object (GraphCanvasExecutionFacts /
  GraphCanvasPreferenceFacts) or the existing interaction object instead.
- under budget -> fail: drilling was removed; lower the budget here in the
  same change so the ratchet keeps tracking reality.

Counting is textual on purpose (comments included): the budget is a coarse
structural ratchet, not a parser.
"""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# (relative path, drilled token, committed budget)
# P6.2 ratchet: GraphNodeHost re-drills replaced by shared facts refs (36 -> 15).
# P8 ratchet: GraphCanvasRootBindings deleted; the canvas resolves bridges via
# its own facade service and sources projections from the facts objects (63 -> 0).
DRILL_BUDGETS: tuple[tuple[str, str, int], ...] = (
    ("ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml", "canvasItem.", 15),
    ("ea_node_editor/ui_qml/components/GraphCanvas.qml", "rootBindings.", 0),
)


class QmlDrillBudgetTests(unittest.TestCase):
    def test_drill_counts_match_committed_budgets(self) -> None:
        problems: list[str] = []
        for relative_path, token, budget in DRILL_BUDGETS:
            text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            count = text.count(token)
            if count > budget:
                problems.append(
                    f"{relative_path}: {count} occurrences of '{token}' exceed the "
                    f"budget of {budget}. Do not add new drilled pass-throughs; "
                    "read the fact from the shared Facts/interaction objects."
                )
            elif count < budget:
                problems.append(
                    f"{relative_path}: {count} occurrences of '{token}' are below the "
                    f"budget of {budget}. Ratchet the budget down to {count} in "
                    "tests/test_qml_drill_budget.py in this same change."
                )
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
