# CloudCart project status

Last updated: 2026-10-24 (Asia/Thimphu).

## Current position

- **Phase:** P02 catalog, persistent carts, and access boundaries done on branch `claude/p02-catalog-carts-access-875a84` (not yet merged into `main`); P03 (atomic checkout and outbox) next, when requested.
- **Architecture:** approved by the instructor.
- **Detailed implementation plan:** Tasks 1–2 complete; Tasks 3–12 not started.
- **Application:** settings, database sessions, app factory, the first Alembic revision, product catalog, persistent guest carts, guest/instructor sessions with CSRF and same-origin checks, instructor stock updates, and the idempotent seed command, with passing unit and PostgreSQL integration tests. No checkout, worker, or frontend features yet.
- **Infrastructure:** none created by this project. Disposable test PostgreSQL/RabbitMQ run only through `make test-deps-up` and are removed by `make test-deps-down`. Versions are selected in [versions.yaml](deploy/platform/versions.yaml), not yet proven on a cluster.
- **Version control:** `main` holds P01; P02 is on branch `claude/p02-catalog-carts-access-875a84` awaiting the instructor's merge decision. Remote `origin` is the public GitHub repository [sarojsanyasicst/DSO202-K8s](https://github.com/sarojsanyasicst/DSO202-K8s); everything pushed there is public.
- **Next milestone:** P03 — atomic checkout and durable order contract.
- **Current blockers:** none for P03. Known risks for later milestones: Docker Desktop VM has ~7.75 GiB against the 12–14 GiB planning estimate (P07/P09/P11); `promtool` not installed (P11).

## Milestone board

This is the single source of truth for milestone status. Detailed step checkboxes live in the [implementation plan](docs/superpowers/plans/2026-10-16-cloudcart-implementation.md). Acceptance criteria live in the [roadmap](docs/project/ROADMAP.md).

| ID | Milestone | Status | Evidence |
| --- | --- | --- | --- |
| S00 | Approved design, project structure, progress tracking | Done | [Design](docs/superpowers/specs/2026-10-16-cloudcart-design.md), [verification](docs/project/VERIFICATION.md) |
| P01 | Runnable database foundation | Done | [Verification 2026-10-24](docs/project/VERIFICATION.md#2026-10-24--p01-runnable-database-foundation) |
| P02 | Catalog, persistent carts, access boundaries | Done | [Verification 2026-10-24](docs/project/VERIFICATION.md#2026-10-24--p02-catalog-persistent-carts-and-access-boundaries) |
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
- Confirm in P10 whether Argo CD uses the public `origin` repository as its Git source, with which revision and values path; it is a candidate, not yet configured or tested.
- Add AMD64 image variants if the student distribution needs them in P06/P12.
- Fix lesson durations after the M4 rehearsal in P12.

## Project records

- [Decisions](docs/project/DECISIONS.md)
- [Session history](docs/project/SESSION_LOG.md)
- [Verification evidence](docs/project/VERIFICATION.md)
- [Next-session handoff](docs/project/HANDOFF.md)
- [Delivered changes](CHANGELOG.md)
