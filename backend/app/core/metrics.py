from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "path"])
EVALUATION_SUCCESS = Gauge("evaluation_success_ratio", "Rolling evaluation success ratio")
HUMAN_MACHINE_ALIGNMENT = Gauge("human_machine_alignment_ratio", "Judge and human verdict alignment")
SANDBOX_ACTIVE = Gauge("sandbox_active", "Currently active sandboxes")
SANDBOX_RUNS = Counter("sandbox_runs_total", "Sandbox executions")
SANDBOX_TIMEOUTS = Counter("sandbox_timeouts_total", "Sandbox hard timeouts")
CELERY_QUEUE_LENGTH = Gauge("celery_queue_length", "Celery queue depth", ["queue"])
