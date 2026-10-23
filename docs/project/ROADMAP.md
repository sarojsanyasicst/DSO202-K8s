# Delivery roadmap

The live milestone board is [PROJECT_STATUS.md](../../PROJECT_STATUS.md). This document defines acceptance; detailed implementation steps and file ownership are in the [implementation plan](../superpowers/plans/2026-10-16-cloudcart-implementation.md).

## Application milestones

| ID / plan task | Deliverable | Acceptance gate |
| --- | --- | --- |
| P01 / Task 1 | Runnable database foundation | Locked dependencies, validated settings, healthy disposable PostgreSQL/RabbitMQ, migration framework, passing foundation checks |
| P02 / Task 2 | Catalog, persistent carts, access boundaries | Repeatable seed, separate persistent guest carts, protected instructor actions, CSRF/session checks |
| P03 / Task 3 | Atomic checkout and outbox | No overselling, one order per idempotent request, transaction rollback without partial state, guest-owned order access |
| P04 / Task 4 | Reliable async fulfillment | Durable publication recovery, duplicate-safe receipts/fulfillment, bounded retries, tested worker shutdown and crash recovery |
| P05 / Task 5 | Storefront and instructor view | Browser shopping journey works, operational states are visible, responsive/accessibility checks complete |
| P06 / Task 6 | Prebuilt release images and handoff | ARM64 v1/v2 images run, version/probe/configuration contracts verified, archives/checksums and handoff available |

## Kubernetes and teaching milestones

| ID / plan task | Deliverable | Acceptance gate |
| --- | --- | --- |
| P07 / Task 7 | Plain manifests on kind | Three Ready nodes, bound PVCs, expected app replicas, local HTTPS checkout and fulfillment, initial resource measurements |
| P08 / Task 8 | Security and recovery exercises | Proven allowed/denied traffic, persistence after Pod replacement, compatible rollout/rollback, backlog/outbox recovery |
| P09 / Task 9 | Controlled load and autoscaling | Bounded traffic, working resource metrics, API scales between 2–4 replicas, worker backlog drains after scaling |
| P10 / Task 10 | Helm and Argo CD | Chart equivalence, explicit deployment ownership, reachable Git source, verified reconciliation and revision revert |
| P11 / Task 11 | Metrics and dashboards | Correct scrapes and aggregations, three populated dashboards, observed load/backlog/recovery, measured laptop resource fit |
| P12 / Task 12 | Rehearsed teaching release | Complete student/instructor kit, verified image import, timed full rehearsal on the M4, honest list of any remaining gaps |

## Sequencing

Build the application through P05 before treating the project as a Kubernetes demonstration. Add operational behavior and delivery artifacts in P06, then prove the deployment before introducing Helm/GitOps. Instrumentation belongs in application work and P11; Metrics Server is installed before the P09 HPA exercise. Prometheus/Grafana are the final teaching milestone, followed by the P12 end-to-end rehearsal.

The actual dependency graph and cross-task signatures are in the detailed plan. Documentation and folder creation alone do not pass an application milestone.
