# Monitoring metrics

The final lesson uses Prometheus and Grafana. Metrics Server separately supplies resource metrics for CPU-based HPA.

- `dashboards/`: Kubernetes workload, application/order, and dependency/processing dashboards.
- `rules/`: bounded-cardinality Prometheus recording rules.
- `tests/`: rule fixtures and query verification.

P11 implements these files and validates real scrapes. Instrumentation also requires application work; empty dashboard folders are not monitoring readiness. Business counts from a shared database must not be summed across API replicas.
