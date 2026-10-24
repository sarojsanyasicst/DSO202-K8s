# Architecture decisions

Accepted decisions come from the [approved design](../superpowers/specs/2026-10-16-cloudcart-design.md). New decisions should record a date, status, choice, and reason; preserve a superseded decision rather than silently deleting its history.

| ID | Date | Status | Decision | Reason |
| --- | --- | --- | --- | --- |
| D001 | 2026-10-16 | Accepted | Single-store e-commerce application | Familiar customer workflow makes operational behavior easy to observe |
| D002 | 2026-10-16 | Accepted | Modular backend plus separate asynchronous worker | Useful independent deployment/scaling with a manageable business codebase |
| D003 | 2026-10-16 | Accepted | React/TypeScript, FastAPI/Python, Celery, PostgreSQL, RabbitMQ | Clear roles for frontend, HTTP traffic, persistence, and background work |
| D004 | 2026-10-16 | Accepted | Transactional outbox and duplicate-safe fulfillment | Orders remain recoverable through broker outages and message redelivery |
| D005 | 2026-10-16 | Accepted | Local kind, 1 control plane + 2 workers, M4/24 GB | Matches the instructor's teaching environment |
| D006 | 2026-10-16 | Accepted | Calico and Traefik/Gateway API | Demonstrate enforced network access and application routing |
| D007 | 2026-10-16 | Accepted | Plain manifests, then Helm, then Argo CD | Teach resource behavior before packaging and reconciliation |
| D008 | 2026-10-16 | Accepted | Metrics Server for CPU HPA; Prometheus/Grafana for monitoring | Separate autoscaling resource metrics from dashboard history |
| D009 | 2026-10-16 | Accepted | Single-instance PostgreSQL/RabbitMQ with local PVCs | Fit the laptop lab while explicitly explaining availability/storage limits |
| D010 | 2026-10-16 | Accepted | Supplied source, Dockerfiles, and prebuilt images | Classroom time focuses on Kubernetes rather than CI/build pipelines |
| D011 | 2026-10-16 | Accepted | Simulated payment and fulfillment; no additional business microservices | Keep development focused on the operations lessons |
| D012 | 2026-10-16 | Adopted for project tracking | One live milestone board plus separate evidence/history/handoff records | Avoid inconsistent status copies and make future sessions resumable |
| D013 | 2026-10-23 | Accepted (implementation) | Backend runtime Python 3.13 (`>=3.13,<3.14`); release image `python:3.13.17-slim-trixie` | Only minor that every planned runtime dependency declares: Celery 5.6.3/Kombu 5.6.2 classifiers stop at 3.13. 3.15 was two weeks old and only an RC was installable locally; 3.14 is not declared by Celery stable. Revisit when Celery declares newer support |
| D014 | 2026-10-23 | Proposed — instructor to ratify | Version matrix in `deploy/platform/versions.yaml`: PostgreSQL 18.6, RabbitMQ 4.3.7, kind v0.32.0 with Kubernetes v1.36.1, Calico v3.33.0, Gateway API v1.6.3, Traefik chart 42.1.3, Metrics Server chart 3.14.0, Argo CD chart 10.11.1, kube-prometheus-stack 92.11.0, postgres-exporter v0.20.1 | Newest stable releases with verified ARM64 images that fit together. RabbitMQ 4.4.0 was three days old; Kubernetes v1.36.5 has no kind v0.32.0 node image (needs a kind upgrade). Two compatibility edges remain `partially_verified` |
| D015 | 2026-10-23 | Accepted (implementation) | Database access through a `Database` object (`session_factory`, `session_scope()`), created in the FastAPI lifespan; no engine at import time | Avoids global state; the session factory serves the Task 4 publisher signature. The plan's `session_scope()` is a method rather than a module function |
| D016 | 2026-10-23 | Accepted (implementation) | Integration tests use one freshly created PostgreSQL database per test session, migrated with Alembic and dropped afterwards, with autouse per-test truncation; destructive setup refuses non-loopback or query-redirected hosts | Later concurrency (two connections) and worker-subprocess tests cannot share one wrapping transaction |
| D017 | 2026-10-23 | Accepted (implementation) | Lab workload settings are off by default and bounded: CPU work 1–2000 ms (default 200), concurrency 1–8 (default 2) | Spec requires a bounded, disabled-by-default lab mode; the server cap stays well below the traffic runner's 20-client limit on a two-worker laptop cluster. Retune with Task 6/9 measurements |

## Choices deferred to implementation

Ratification of the D014 version matrix and closing its partially verified edges; measured resource requests/limits; Git source for Argo CD; conditional AMD64 distribution; lesson timing. These are not completed validations or architecture changes.
