import unittest

from market_pulse.rules import build_consensus


class ConsensusTest(unittest.TestCase):
    def test_consensus_ignores_legacy_risk_signal(self):
        result = build_consensus(
            {
                "oneil": {"opinion": "매수 우위", "score": 80},
                "trend": {"opinion": "매수 우위", "score": 70},
                "risk": {"opinion": "매도/방어", "score": 0},
            }
        )

        self.assertEqual(result["opinion"], "매수 우위")
        self.assertEqual(result["score"], 75)


if __name__ == "__main__":
    unittest.main()
