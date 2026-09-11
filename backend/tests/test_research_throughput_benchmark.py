"""Tests for Research Throughput Benchmark and Bounded Concurrency."""
import unittest
import time
from services.research_throughput_benchmark import (
    BENCHMARK_COMPANIES,
    DomainRateLimiter,
    ResearchThroughputBenchmark,
    research_throughput_benchmark,
)


class TestResearchThroughputBenchmark(unittest.TestCase):

    def test_domain_rate_limiter_throttles_rapid_access(self):
        limiter = DomainRateLimiter(min_interval_sec=0.05)
        t0 = time.time()
        limiter.acquire("example.com")
        limiter.acquire("example.com")
        elapsed = time.time() - t0
        self.assertGreaterEqual(elapsed, 0.04)

    def test_domain_rate_limiter_distinct_domains_dont_block(self):
        limiter = DomainRateLimiter(min_interval_sec=0.1)
        t0 = time.time()
        limiter.acquire("domain-a.com")
        limiter.acquire("domain-b.com")
        elapsed = time.time() - t0
        # Distinct domains should not force a 0.1s wait for each other
        self.assertLess(elapsed, 0.09)

    def test_single_company_research_metrics(self):
        bench = ResearchThroughputBenchmark(domain_min_interval=0.0)
        sample_co = BENCHMARK_COMPANIES[0]
        res = bench.research_single_company(sample_co)

        self.assertEqual(res.company, sample_co["company"])
        self.assertTrue(res.valid_trigger)
        self.assertTrue(res.exact_facility_found)
        self.assertTrue(res.person_found)
        self.assertGreater(res.search_queries_count, 0)
        self.assertIn(res.status, ("READY_FOR_EMAIL", "HOLD"))

    def test_sequential_benchmark_run(self):
        bench = ResearchThroughputBenchmark(domain_min_interval=0.0)
        # Test on 3 companies
        sample = BENCHMARK_COMPANIES[:3]
        report = bench.run_benchmark(companies=sample, max_workers=1)

        self.assertEqual(report.total_companies, 3)
        self.assertEqual(report.concurrency_mode, "SEQUENTIAL")
        self.assertGreater(report.candidate_companies_per_hour, 0)
        self.assertGreater(report.fully_researched_companies_per_hour, 0)
        self.assertGreaterEqual(report.valid_trigger_rate_pct, 90.0)
        self.assertGreaterEqual(report.exact_facility_rate_pct, 90.0)
        self.assertEqual(len(report.top_3_bottlenecks), 3)

    def test_bounded_parallel_benchmark_run(self):
        bench = ResearchThroughputBenchmark(domain_min_interval=0.0)
        sample = BENCHMARK_COMPANIES[:4]
        report = bench.run_benchmark(companies=sample, max_workers=2)

        self.assertEqual(report.total_companies, 4)
        self.assertEqual(report.concurrency_mode, "BOUNDED_PARALLEL_2")
        self.assertEqual(report.max_workers, 2)
        self.assertEqual(len(report.company_results), 4)
        self.assertGreater(report.avg_latency_seconds, 0)
        self.assertEqual(report.timeout_error_rate_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
