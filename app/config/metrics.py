from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route", "status"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_ms",
    "HTTP request duration in milliseconds",
    ["method", "route", "status"],
    buckets=[5, 15, 50, 100, 250, 500, 1000],
)
REQUEST_ABORTED = Counter(
    "http_requests_aborted_total", "Aborted HTTP requests", ["method", "route"]
)
