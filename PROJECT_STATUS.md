# CloudCart project status

Last updated: 2026-10-24 (Asia/Thimphu).

## Current position

- **Phase:** P01 database foundation done; P02 (catalog, carts, access boundaries) next, when requested.
- **Architecture:** approved by the instructor.
- **Detailed implementation plan:** Task 1 complete; Tasks 2–12 not started.
- **Application:** settings, database sessions, app factory, and Alembic scaffolding exist with passing unit and PostgreSQL integration tests. No product, cart, checkout, worker, or frontend features yet.
- **Infrastructure:** none created by this project. Disposable test PostgreSQL/RabbitMQ run only through `make test-deps-up` and are removed by `make test-deps-down`. Versions are selected in [versions.yaml](deploy/platform/versions.yaml), not yet proven on a cluster.
- **Version control:** local Git repository on `main`; P01 work on branch `p01-database-foundation`. No remote.
- **Next milestone:** P02 — catalog, persistent carts, access boundaries.
- **Current blockers:** none for P02. Known risks for later milestones: Docker Desktop VM has ~7.75 GiB against the 12–14 GiB planning estimate (P07/P09/P11); `promtool` not installed (P11).

## Milestone board

This is the single source of truth for milestone status. Detailed step checkboxes live in the [implementation plan](docs/superpowers/plans/2026-10-16-cloudcart-implementation.md). Acceptance criteria live in the [roadmap](docs/project/ROADMAP.md).

| ID | Milestone | Status | Evidence |
| --- | --- | --- | --- |
| S00 | Approved design, project structure, progress tracking | Done | [Design](docs/superpowers/specs/2026-10-16-cloudcart-design.md), [verification](docs/project/VERIFICATION.md) |
| P01 | Runnable database foundation | Done | [Verification 2026-10-24](docs/project/VERIFICATION.md#2026-10-24--p01-runnable-database-foundation) |
| P02 | Catalog, persistent carts, access boundaries | Not started | — |
| P03 | Atomic checkout and durable order contract | Not started | — |
| P04 | Reliable publisher and fulfillment worker | Not started | — |
| P05 | Storefront and instructor view | Not started | — |
| P06 | Versioned images and software-team handoff | Not started | — |
| P07 | kind infrastructure and plain-manifest deployment | Not started | — |
| P08 | Security, persistence, rollout, recovery exercises | Not started | — |
| P09 | Controlled load and CPU autoscaling | Not started | — |
| P10 | Helm equivalence and GitOps ownership | Not started | — |
| P11 | Metrics and three provisioned dashboards | Not started | — |
| P12 | Rehearsed teaching kit and release artifacts | Not started | — |

**Status meanings:** Not started; In progress; Blocked (name the dependency); Done (acceptance evidence exists). No completion percentage is assigned because the milestones vary in size.

## Pending implementation choices

- Close the two `partially_verified` compatibility edges in versions.yaml (Gateway API minimum Kubernetes version; kube-prometheus-stack on Kubernetes 1.36) before installing them in P07/P11.
- Instructor to ratify the version choices recorded in [DECISIONS.md](docs/project/DECISIONS.md) (D014).
- Measure Docker allocation and real cluster capacity in P07/P09/P11.
- Configure a Git source reachable by Argo CD in P10; no remote destination has been chosen.
- Add AMD64 image variants if the student distribution needs them in P06/P12.
- Fix lesson durations after the M4 rehearsal in P12.

## Project records

- [Decisions](docs/project/DECISIONS.md)
- [Session history](docs/project/SESSION_LOG.md)
- [Verification evidence](docs/project/VERIFICATION.md)
- [Next-session handoff](docs/project/HANDOFF.md)
- [Delivered changes](CHANGELOG.md)
