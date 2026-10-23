# CloudCart project status

Last updated: 2026-10-16 (Asia/Thimphu).

## Current position

- **Phase:** project setup complete; application foundation next.
- **Architecture:** approved by the instructor.
- **Detailed implementation plan:** prepared; its application tasks have not started.
- **Application:** no runnable backend, frontend, or worker yet.
- **Infrastructure:** no cluster created or dependencies installed by this project.
- **Next milestone:** P01 — runnable database foundation, when implementation is requested.
- **Current blockers:** none for the completed structure/tracking task. Runtime prerequisites are not yet checked.

## Milestone board

This is the single source of truth for milestone status. Detailed step checkboxes live in the [implementation plan](docs/superpowers/plans/2026-10-16-cloudcart-implementation.md). Acceptance criteria live in the [roadmap](docs/project/ROADMAP.md).

| ID | Milestone | Status | Evidence |
| --- | --- | --- | --- |
| S00 | Approved design, project structure, progress tracking | Done | [Design](docs/superpowers/specs/2026-10-16-cloudcart-design.md), [verification](docs/project/VERIFICATION.md) |
| P01 | Runnable database foundation | Not started | — |
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

- Verify and pin the runtime, chart, controller, and ARM64 image compatibility matrix in P01.
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
