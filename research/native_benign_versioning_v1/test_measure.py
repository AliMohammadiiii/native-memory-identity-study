import unittest

from .measure import graph_diagnostics, effect


class MeasurementTests(unittest.TestCase):
    def test_self_link_is_a_cycle_even_if_history_reader_has_a_loop_guard(self):
        rows = [{"id": 9, "supersedes": 9, "archived": 1, "content": "blue"}]
        self.assertEqual(graph_diagnostics(rows), {"self_edges": [9], "cycle_nodes": [9], "dangling_predecessors": []})

    def test_long_cycle_and_unrelated_root_are_separated(self):
        rows = [{"id": 1, "supersedes": 3}, {"id": 2, "supersedes": 1},
                {"id": 3, "supersedes": 2}, {"id": 4, "supersedes": None}]
        self.assertEqual(graph_diagnostics(rows)["cycle_nodes"], [1, 2, 3])
        self.assertFalse(graph_diagnostics(rows)["self_edges"])

    def test_success_and_latest_history_are_not_current_visibility(self):
        self.assertEqual(effect("return", "blue", [], [], []), "SUCCESS_WITH_REQUESTED_VALUE_UNAVAILABLE")
        self.assertEqual(effect("return", "blue", ["blue"], ["blue"], ["blue"]), "REQUESTED_VALUE_VISIBLE")

    def test_missing_or_disagreeing_observation_cannot_be_a_positive_finding(self):
        self.assertEqual(effect("return", "blue", None, [], []), "UNKNOWN")
        self.assertEqual(effect("return", "blue", ["blue"], [], []), "OBSERVATION_DISAGREEMENT")
        self.assertEqual(effect("exception", "blue", [], [], []), "API_EXCEPTION")


if __name__ == "__main__":
    unittest.main()
