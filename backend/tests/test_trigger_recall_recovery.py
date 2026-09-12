import unittest
from services.research_metrics import calculate_precision_recall_f1
from services.signal_discovery_engine import generate_adaptive_trigger_queries, expand_trigger_queries_with_gemini
from services.trigger_discovery_service import (
    evaluate_event_semantics,
    should_escalate_to_browser,
    EVENT_ACTION_PATTERNS,
)


class TestTriggerRecallRecovery(unittest.TestCase):
    """Regression test suite for trigger recall recovery, metric math, query passes, and browser escalation."""

    def test_precision_metric_zero_accepted_safety(self):
        """When TP + FP == 0, precision must be NOT_MEASURABLE and leakage must be 0."""
        metrics = calculate_precision_recall_f1(
            tp=0,
            fp=0,
            tn=16,
            fn=16,
            stale_valid_discoveries=0,
            total_benchmark_positives=16,
        )
        self.assertEqual(metrics["precision"], "NOT_MEASURABLE")
        self.assertEqual(metrics["false_positive_leakage"], 0)
        self.assertEqual(metrics["discovery_recall"], 0.0)
        self.assertEqual(metrics["current_opportunity_recall"], 0.0)
        self.assertEqual(metrics["f1"], "NOT_MEASURABLE")

    def test_precision_metric_standard_calculation(self):
        """Verify precision and discovery recall calculation when positives are accepted."""
        metrics = calculate_precision_recall_f1(
            tp=8,
            fp=0,
            tn=16,
            fn=4,
            stale_valid_discoveries=4,
            total_benchmark_positives=16,
        )
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["discovery_recall"], 0.75)
        self.assertEqual(metrics["current_opportunity_recall"], 0.5)
        self.assertAlmostEqual(metrics["f1"], 0.8571, places=2)
        self.assertEqual(metrics["true_positives"], 8)
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["true_negatives"], 16)
        self.assertEqual(metrics["stale_valid_discoveries"], 4)

    def test_adaptive_query_generation_structure(self):
        """Adaptive query generator must produce 3 structured passes."""
        passes = generate_adaptive_trigger_queries(
            company_name="Tata Motors Limited",
            sector="Automotive OEM",
            hub="Sanand Gujarat",
            official_domain="tatamotors.com",
        )
        self.assertIn("pass_1", passes)
        self.assertIn("pass_2", passes)
        self.assertIn("pass_3", passes)

        # Pass 1: company and event verbs
        self.assertTrue(any("plant" in q or "capex" in q for q in passes["pass_1"]))
        # Pass 2: location / corridor specific
        self.assertTrue(any("Sanand Gujarat" in q for q in passes["pass_2"]))
        # Pass 3: filings and official site
        self.assertTrue(any("site:tatamotors.com" in q or "BSE" in q or "NSE" in q for q in passes["pass_3"]))

    def test_gemini_expansion_capped_at_three(self):
        """Gemini query expansion must never exceed 3 queries per company."""
        queries = expand_trigger_queries_with_gemini("Tata Motors", "Auto", "Sanand", max_queries=3)
        self.assertLessEqual(len(queries), 3)

    def test_event_action_patterns_broadened_inflections(self):
        """Trigger evaluation must match legitimate industrial verbal inflections."""
        valid_samples = [
            "Maruti Suzuki commissions fourth production line at Gujarat facility",
            "JSW Steel inaugurates new 5 MTPA blast furnace in Bellary",
            "Ambuja Cements announces capex of Rs 6000 crore for Mundra grinding unit",
            "Tata Power sets up 400 MW solar plant in Dholera",
            "Novonesis plans capacity ramp-up at its Patalganga enzymes plant",
            "Hero MotoCorp to build a plant in Chittoor Andhra Pradesh",
        ]

        for sample in valid_samples:
            eval_res = evaluate_event_semantics(sample)
            self.assertTrue(eval_res["is_verified"], f"Failed to match valid industrial event phrase: '{sample}'")

    def test_browser_escalation_criteria(self):
        """Only Tier A/B news domains with anti-bot challenge status codes should escalate to browser."""
        # Tier A domain with 403 challenge -> should escalate
        self.assertTrue(should_escalate_to_browser("https://economictimes.indiatimes.com/article123", 403))
        self.assertTrue(should_escalate_to_browser("https://www.thehindubusinessline.com/news/article456", 429))

        # Rejected domain -> must NEVER escalate
        self.assertFalse(should_escalate_to_browser("https://pinterest.com/pin/123", 403))
        self.assertFalse(should_escalate_to_browser("https://facebook.com/post/456", 429))

        # Normal 200 OK -> does not need browser escalation
        self.assertFalse(should_escalate_to_browser("https://economictimes.indiatimes.com/article123", 200))


if __name__ == "__main__":
    unittest.main()
