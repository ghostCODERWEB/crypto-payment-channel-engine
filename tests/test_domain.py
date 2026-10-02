import unittest, copy, json
from decimal import Decimal
from pathlib import Path
from cryptolab import analyze
from cryptolab.engine import *

EXAMPLE = json.loads(Path("examples/input.json").read_text())


class DomainTests(unittest.TestCase):
    def configured(self):
        d = copy.deepcopy(EXAMPLE)
        b = {"alice": 50, "bob": 150}
        d["events"] = [
            {
                "type": "update",
                "nonce": 1,
                "balances": b,
                "approvals": ["alice", "bob"],
                "commitment": commitment("channel1", 1, b),
                "timestamp": 1,
            },
            {"type": "close", "actor": "bob", "nonce": 0, "timestamp": 2},
            {"type": "challenge", "actor": "alice", "nonce": 1, "timestamp": 3},
            {"type": "settle", "timestamp": 12},
        ]
        return d

    def test_stale_state_dispute(self):
        r = analyze(self.configured())
        self.assertEqual(r["settlement"], {"alice": 50, "bob": 150})
        self.assertEqual(r["status"], "settled")

    def test_inflation(self):
        d = self.configured()
        d["events"][0]["balances"]["alice"] = 60
        with self.assertRaises(ValueError):
            analyze(d)

    def test_wrong_commitment(self):
        d = self.configured()
        d["events"][0]["commitment"] = "bad"
        with self.assertRaises(ValueError):
            analyze(d)

    def test_late_challenge(self):
        d = self.configured()
        d["events"][2]["timestamp"] = 12
        with self.assertRaises(ValueError):
            analyze(d)

    def test_early_settlement(self):
        d = self.configured()
        d["events"][-1]["timestamp"] = 11
        with self.assertRaises(ValueError):
            analyze(d)
