#!/usr/bin/env python3
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STRATEGIES = os.path.join(os.path.dirname(HERE), "strategies", "pre_implementation_gate")
sys.path.insert(0, STRATEGIES)
import cycle_domain_review as strategy  # noqa: E402


def doc(cycle="141", domain="auth", rounds="[1, 2]", path="review.md"):
    return {"path": path,
            "content": f"---\ncycle_id: {cycle}\nround: {rounds}\ndomain_ref: {domain}\n---\n# Review\n"}


class TestCycleDomainReview(unittest.TestCase):
    def test_current_cycle_all_domains_pass(self):
        result = strategy.find_l3_review(
            {"cycle_ids": {"141"}, "matched_domains": {"auth", "secret"}},
            {"l3_review_docs": [doc(domain="auth"), doc(domain="secret", path="secret.md")]})
        self.assertTrue(result["found"])

    def test_stale_cycle_does_not_pass(self):
        result = strategy.find_l3_review(
            {"cycle_ids": {"141"}, "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(cycle="140")]})
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["auth"])

    def test_both_rounds_are_required(self):
        result = strategy.find_l3_review(
            {"cycle_ids": {"141"}, "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(rounds="[1]")]})
        self.assertFalse(result["found"])
        self.assertIn("malformed", result["reason"])

    def test_multiple_domains_use_and_semantics(self):
        result = strategy.find_l3_review(
            {"cycle_ids": {"141"}, "matched_domains": {"auth", "secret"}},
            {"l3_review_docs": [doc(domain="auth")]})
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["secret"])

    def test_unregistered_domain_match_is_fail_closed(self):
        result = strategy.find_l3_review(
            {"cycle_ids": {"141"}, "matched_domains": set()},
            {"l3_review_docs": [doc()]})
        self.assertFalse(result["found"])
        self.assertIn("registered risk domain", result["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
