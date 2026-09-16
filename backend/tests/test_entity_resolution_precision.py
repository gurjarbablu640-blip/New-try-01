"""Task 3C.1 Labeled Precision Benchmark & Hardened Entity Resolution Regression.

Evaluates deterministic company entity classification and false-positive suppression:
- Labeled dataset of 60 cases (25 positives, 35 negatives covering all known failure classes)
- Asserts ENTITY_PRECISION >= 95%
- Asserts ZERO false positives among critical negative regression cases
- Tests headline boundary trimming
- Tests dynamic publisher suppression
- Tests normalized comparison key without display name overwriting
- Tests persistence guard behavior
"""
import unittest

from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
    get_normalized_comparison_key,
    normalize_entity_candidate,
    trim_headline_subject_boundary,
    validate_company_entity,
    resolve_canonical_company_identity,
    ENTITY_TELEMETRY,
    reset_entity_telemetry,
)


class TestEntityResolutionPrecision(unittest.TestCase):
    """Rigorous evaluation of company classification precision, recall, and false-positive suppression."""

    def setUp(self):
        reset_entity_telemetry()

    def test_labeled_corpus_precision_and_recall(self):
        """Measures precision and recall across 60 labeled cases (25 positive, 35 negative)."""
        # 25 authentic corporate organizations
        positives = [
            "Waaree Energies",
            "Tata AutoComp Systems",
            "Sundram Fasteners Limited",
            "JSW Steel",
            "Amara Raja",
            "Neuron Energy",
            "RenewSys",
            "Tata Electronics",
            "Valeo India",
            "Kehems Technologies",
            "Reliance Industries",
            "Bharat Forge",
            "Kaynes Technology",
            "Larsen & Toubro",
            "Schneider Electric",
            "Motherson Sumi Systems",
            "Exide Energy Solutions",
            "Sterlite Technologies",
            "Tata Motors",
            "Lucas TVS",
            "Mahindra & Mahindra",
            "Sona Comstar",
            "Hero MotoCorp",
            "Baxy Mobility",
            "Ola Electric Technologies Pvt Ltd",
        ]

        # 35 non-company entities covering all historical and live failure classes
        negatives = [
            # 18 Critical Historical / Live Regressions
            "Waaree Energies relocates 6GW vertically",
            "pv magazine India",
            "Automobile, Auto Components & EV",
            "Business Data & Market Insights",
            "EV Charging Station Franchise",
            "Daily Morning Newsletter",
            "A 40 Billion",
            "ion cell",
            "Omprakash Singh Bisht",
            "JMK Research",
            "Mega",
            "IBEF",
            "Ems profiles",
            "Our Businesses",
            "Moulding Apqp Jobs",
            "Solar Module",
            "Maruti Suzuki has",
            "ITP Aero has",
            # Unseen variants
            "Toyota to build three assembly plants",
            "Economic Times",
            "BusinessLine",
            "Auto parts manufacturers in Tamil Nadu",
            "How many Auto parts manufacturers are there in Tamil Nadu",
            "Automotive Components Manufacturers In Haryana",
            "Renewable Energy Policy 2026",
            "Gujarat Semiconductor Hub",
            "Narendra Modi",
            "Yogi Adityanath",
            "Did you know the worlds largest single",
            "About Our Company",
            "Careers at Tata",
            "Contact Us",
            "Battery Pack Solutions Franchise",
            "Senior Metrology Engineer Jobs",
            "Lithium Ion",
        ]

        critical_regressions = {
            "Waaree Energies relocates 6GW vertically",
            "pv magazine India",
            "Automobile, Auto Components & EV",
            "Business Data & Market Insights",
            "EV Charging Station Franchise",
            "Daily Morning Newsletter",
            "A 40 Billion",
            "ion cell",
            "Omprakash Singh Bisht",
            "JMK Research",
            "Mega",
            "IBEF",
            "Ems profiles",
            "Our Businesses",
            "Moulding Apqp Jobs",
            "Solar Module",
            "Maruti Suzuki has",
            "ITP Aero has",
        }

        tp = 0
        fn = 0
        fp = 0
        tn = 0
        critical_fp = []

        for p in positives:
            res = classify_entity_candidate(p)
            if res["entity_class"] == EntityType.COMPANY:
                tp += 1
            else:
                fn += 1
                print(f"False Negative: '{p}' rejected as {res['entity_class']} ({res['reason']})")

        for n in negatives:
            res = classify_entity_candidate(n)
            if res["entity_class"] == EntityType.COMPANY:
                fp += 1
                if n in critical_regressions:
                    critical_fp.append(n)
                print(f"False Positive: '{n}' accepted as {res['entity_class']}")
            else:
                tn += 1

        total = len(positives) + len(negatives)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        print(f"\n==================================================")
        print(f"TASK 3C.1 LABELED BENCHMARK RESULTS (N={total}):")
        print(f"  TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
        print(f"  PRECISION: {precision * 100:.2f}%")
        print(f"  RECALL:    {recall * 100:.2f}%")
        print(f"  CRITICAL FP: {len(critical_fp)}")
        print(f"==================================================")

        self.assertEqual(len(critical_fp), 0, f"Critical negative regressions failed: {critical_fp}")
        self.assertGreaterEqual(precision, 0.95, f"Precision {precision:.2f} below 95% threshold")
        self.assertGreaterEqual(recall, 0.90, f"Recall {recall:.2f} below acceptable 90% threshold")
        self.assertEqual(fp, 0, f"Expected zero false positives, got {fp}")

    def test_headline_subject_boundary_trimming(self):
        """Extracts legitimate corporate subjects from news headlines with predicate verbs."""
        test_cases = [
            ("Waaree Energies relocates 6GW vertically", "Waaree Energies"),
            ("Maruti Suzuki has announced major capex", "Maruti Suzuki"),
            ("ITP Aero has inaugurated its new plant", "ITP Aero"),
            ("Toyota to build three assembly plants in Karnataka", "Toyota"),
            ("Micron Celebrates Opening of Indias First Semiconductor", "Micron"),
        ]
        for headline, expected in test_cases:
            trimmed, did_trim = trim_headline_subject_boundary(headline)
            self.assertTrue(did_trim, f"Expected trimming for headline: '{headline}'")
            self.assertEqual(trimmed, expected, f"Expected '{expected}', got '{trimmed}'")

    def test_headline_boundary_does_not_split_ordinary_companies(self):
        """Legitimate companies containing words resembling verbs must not be incorrectly truncated."""
        intact_companies = [
            "Reliance Industries",
            "Kaynes Technology",
            "Kehems Technologies",
            "Tata AutoComp Systems",
            "Sundram Fasteners Limited",
        ]
        for name in intact_companies:
            trimmed, did_trim = trim_headline_subject_boundary(name)
            self.assertEqual(trimmed, name, f"Expected '{name}' to remain intact, got '{trimmed}'")

    def test_dynamic_publisher_suppression_via_url(self):
        """Suppresses publisher when candidate matches the news source domain."""
        res = classify_entity_candidate(
            "pv magazine India",
            url="https://www.pv-magazine-india.com/2024/07/15/vinfast-exploring-andhra-pradesh-plant/",
        )
        self.assertEqual(res["entity_class"], EntityType.PUBLISHER)
        self.assertFalse(res["is_company"])

        res2 = classify_entity_candidate(
            "Economic Times",
            url="https://economictimes.indiatimes.com/industry/auto/auto-news/tata-motors-capex/",
        )
        self.assertEqual(res2["entity_class"], EntityType.PUBLISHER)
        self.assertFalse(res2["is_company"])

    def test_domain_mismatch_on_news_page_does_not_reject_subject_company(self):
        """Legitimate company on a news article must NOT be rejected due to domain mismatch."""
        resolution = resolve_canonical_company_identity(
            raw_candidate="Waaree Energies",
            title="Waaree Energies to set up 6GW manufacturing facility in Gujarat",
            snippet="Solar module manufacturer Waaree Energies has commissioned a major new plant.",
            url="https://www.pv-magazine-india.com/2024/07/15/waaree-energies-expansion/",
        )
        self.assertTrue(resolution["is_valid"])
        self.assertEqual(resolution["company_name"], "Waaree Energies")
        self.assertEqual(resolution["entity_class"], EntityType.COMPANY)

    def test_normalized_comparison_key_preserves_display_name(self):
        """Normalized key deduplicates variations without overwriting display name."""
        variants = [
            ("Tata Electronics Private Limited", "tata electronics"),
            ("Tata Electronics Pvt Ltd", "tata electronics"),
            ("Tata Electronics Limited", "tata electronics"),
            ("Tata Electronics Ltd.", "tata electronics"),
            ("Tata Electronics", "tata electronics"),
        ]
        for display_name, expected_key in variants:
            key = get_normalized_comparison_key(display_name)
            self.assertEqual(key, expected_key)
            # Display name must remain unchanged by normalization
            clean_display = normalize_entity_candidate(display_name)
            self.assertEqual(clean_display, display_name.strip("."))

    def test_parent_subsidiary_separation(self):
        """Parent, subsidiary, and distinct entities must have distinct comparison keys."""
        comp1 = get_normalized_comparison_key("Tata Motors")
        comp2 = get_normalized_comparison_key("Tata Electronics")
        comp3 = get_normalized_comparison_key("Tata Power")
        self.assertNotEqual(comp1, comp2)
        self.assertNotEqual(comp2, comp3)
        self.assertNotEqual(comp1, comp3)

    def test_persistence_guard_blocks_non_company(self):
        """Guarantees that non-company candidates are rejected before DB creation."""
        non_companies = [
            "pv magazine India",
            "Automobile, Auto Components & EV",
            "Business Data & Market Insights",
            "EV Charging Station Franchise",
            "Omprakash Singh Bisht",
            "Our Businesses",
        ]
        for item in non_companies:
            cls = classify_entity_candidate(item)
            self.assertNotEqual(cls["entity_class"], EntityType.COMPANY)
            self.assertFalse(cls["is_company"])


if __name__ == "__main__":
    unittest.main()
