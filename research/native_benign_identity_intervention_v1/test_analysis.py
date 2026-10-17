import copy
import unittest

from .analyze import derive


def fixture():
    observation = {
        "current_contents": ["blue"], "physical_contents": ["blue"],
        "sentinel_contents": ["memoryprobe unrelated keep"], "other_namespace_contents": [],
        "physical_rows": [{"id": 2, "supersedes": None, "archived": 0}],
    }
    return {"final": copy.deepcopy(observation), "cold": copy.deepcopy(observation),
            "steps": [{"native": {"outcome": "return", "value": {"id": 2, "supersedes": 2}, "returned_id": 2}}],
            "aliases": {"subject": 2}, "final_outcome": "return", "final_requested": "blue"}


class ObservationValidity(unittest.TestCase):
    def test_returned_self_predecessor_is_separate_from_persisted_graph(self):
        result = derive(fixture())
        self.assertTrue(result["response_self_predecessor"])
        self.assertEqual(result["stored_self_edges"], 0)
        self.assertFalse(result["confirmed_current_loss"])

    def test_unavailable_observation_is_not_treated_as_value_loss(self):
        cell = fixture()
        del cell["cold"]["current_contents"]
        with self.assertRaises(KeyError):
            derive(cell)

    def test_only_public_absence_does_not_meet_confirmed_loss_endpoint(self):
        cell = fixture()
        cell["final"]["current_contents"] = []
        cell["cold"]["current_contents"] = []
        self.assertFalse(derive(cell)["confirmed_current_loss"])

    def test_drift_blocks_interpretation(self):
        cell = fixture()
        cell["cold"]["current_contents"] = []
        with self.assertRaisesRegex(ValueError, "cold_observation_drift"):
            derive(cell)


if __name__ == "__main__":
    unittest.main()
