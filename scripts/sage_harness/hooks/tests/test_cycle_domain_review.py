#!/usr/bin/env python3
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STRATEGIES = os.path.join(os.path.dirname(HERE), "strategies", "pre_implementation_gate")
sys.path.insert(0, STRATEGIES)
import cycle_domain_review as strategy  # noqa: E402


def doc(cycle="141", domain="auth", rounds="[1, 2]", path="review.md", legacy=False):
    cycle_key = "cycle_id" if legacy else "cycle_stem"
    return {"path": path,
            "content": f"---\n{cycle_key}: {cycle}\nround: {rounds}\ndomain_ref: {domain}\n---\n# Review\n"}


class TestCycleDomainReview(unittest.TestCase):
    def test_current_cycle_all_domains_pass(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": {"auth", "secret"}},
            {"l3_review_docs": [doc(domain="auth"), doc(domain="secret", path="secret.md")]})
        self.assertTrue(result["found"])

    def test_stale_cycle_does_not_pass(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(cycle="140")]})
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["auth"])

    def test_both_rounds_are_required(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(rounds="[1]")]})
        self.assertFalse(result["found"])
        self.assertIn("malformed", result["reason"])

    def test_multiple_domains_use_and_semantics(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": {"auth", "secret"}},
            {"l3_review_docs": [doc(domain="auth")]})
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["secret"])

    def test_unregistered_domain_match_is_fail_closed(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": set()},
            {"l3_review_docs": [doc()]})
        self.assertFalse(result["found"])
        self.assertIn("registered risk domain", result["reason"])

    def test_incidental_sd3_number_does_not_bind_stale_cycle_three(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141-sd3", "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(cycle="3")]})
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["auth"])

    def test_v2_does_not_bind_cycle_two(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "v2", "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(cycle="2")]})
        self.assertFalse(result["found"])

    def test_legacy_cycle_id_is_not_accepted(self):
        result = strategy.find_l3_review(
            {"cycle_stem": "141", "matched_domains": {"auth"}},
            {"l3_review_docs": [doc(cycle="141", legacy=True)]})
        self.assertFalse(result["found"])

    def test_binding_error_is_returned_verbatim(self):
        result = strategy.find_l3_review(
            {"cycle_stem": None, "cycle_binding_error": "ambiguous cycle", "matched_domains": {"auth"}},
            {"l3_review_docs": []})
        self.assertFalse(result["found"])
        self.assertEqual(result["reason"], "ambiguous cycle")


if __name__ == "__main__":
    unittest.main(verbosity=2)
