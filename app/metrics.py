"""Request count, latency, and cost for each model.

These are the same signals a production metrics system would graph.
"""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

_LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class TranslationMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self.requests = Counter(
            "translation_requests_total",
            "Completed translation requests.",
            ("model",),
            registry=self.registry,
        )
        self.latency = Histogram(
            "translation_latency_seconds",
            "Translation latency in seconds.",
            ("model",),
            registry=self.registry,
            buckets=_LATENCY_BUCKETS,
        )
        self.cost = Counter(
            "translation_cost_usd_total",
            "Estimated translation cost in USD.",
            ("model",),
            registry=self.registry,
        )

    def record(self, *, model: str, latency_ms: int, cost_usd: float) -> None:
        self.requests.labels(model=model).inc()
        self.latency.labels(model=model).observe(latency_ms / 1000)
        if cost_usd > 0:
            self.cost.labels(model=model).inc(cost_usd)

    def render(self) -> bytes:
        return generate_latest(self.registry)
