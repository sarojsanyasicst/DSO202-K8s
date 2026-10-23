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

## Choices deferred to implementation

Exact stable versions and compatibility matrix; measured resource requests/limits; Git source for Argo CD; conditional AMD64 distribution; lesson timing. These are not completed validations or architecture changes.
