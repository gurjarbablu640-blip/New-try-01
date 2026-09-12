"""Research & Discovery Metric Calculations.

Provides mathematically rigorous precision, recall, and F1 calculations
for intelligence discovery pipelines, explicitly preventing invalid claims
(e.g., reporting 100% precision when 0 positive candidates were accepted).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Union


def calculate_precision_recall_f1(
    tp: int,
    fp: int,
    tn: int,
    fn: int,
    stale_valid_discoveries: int = 0,
    total_benchmark_positives: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate precision, recall, F1, and leakage metrics.

    Distinguishes DISCOVERY_RECALL (genuine event identified irrespective of current recency)
    from CURRENT_OPPORTUNITY_RECALL (passes production 2026-09-12 recency gate).

    When TP + FP == 0:
        precision is "NOT_MEASURABLE" (not 100% or 0%)
        false_positive_leakage is 0
    """
    total_accepted = tp + fp
    total_actual_positives = total_benchmark_positives if total_benchmark_positives is not None else (tp + fn)

    # 1. Precision & Leakage
    if total_accepted == 0:
        precision: Union[float, str] = "NOT_MEASURABLE"
        fp_leakage = 0
    else:
        precision = round(float(tp) / float(total_accepted), 4)
        fp_leakage = fp

    # 2. Discovery Recall (rediscovered real events, including historically valid stale ones)
    total_discovered_events = tp + stale_valid_discoveries
    if total_actual_positives > 0:
        discovery_recall = round(float(total_discovered_events) / float(total_actual_positives), 4)
        current_opportunity_recall = round(float(tp) / float(total_actual_positives), 4)
    else:
        discovery_recall = "NOT_MEASURABLE"
        current_opportunity_recall = "NOT_MEASURABLE"

    # 3. F1 Score
    f1: Union[float, str] = "NOT_MEASURABLE"
    if isinstance(precision, float) and isinstance(discovery_recall, float):
        denom = precision + discovery_recall
        if denom > 0:
            f1 = round(2.0 * (precision * discovery_recall) / denom, 4)

    # 4. Specificity & Negative Rejection Rate
    total_negatives = tn + fp
    if total_negatives > 0:
        specificity = round(float(tn) / float(total_negatives), 4)
    else:
        specificity = "NOT_MEASURABLE"

    return {
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "stale_valid_discoveries": stale_valid_discoveries,
        "total_actual_positives": total_actual_positives,
        "total_accepted_candidates": total_accepted,
        "precision": precision,
        "false_positive_leakage": fp_leakage,
        "discovery_recall": discovery_recall,
        "current_opportunity_recall": current_opportunity_recall,
        "f1": f1,
        "specificity": specificity,
        "discovery_recall_percent": f"{round(discovery_recall * 100, 1)}%" if isinstance(discovery_recall, float) else "NOT_MEASURABLE",
        "current_opportunity_recall_percent": f"{round(current_opportunity_recall * 100, 1)}%" if isinstance(current_opportunity_recall, float) else "NOT_MEASURABLE",
        "precision_percent": f"{round(precision * 100, 1)}%" if isinstance(precision, float) else "NOT_MEASURABLE",
        "f1_percent": f"{round(f1 * 100, 1)}%" if isinstance(f1, float) else "NOT_MEASURABLE",
    }
