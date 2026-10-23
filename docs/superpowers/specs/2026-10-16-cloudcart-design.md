# CloudCart: Kubernetes operations teaching project

Status: approved by the instructor on 2026-10-16; project structure and progress tracking are prepared; application implementation has not started.

## Intent and agreed constraints

Students have already studied Kubernetes fundamentals, including Pods, Deployments, StatefulSets, ConfigMaps, Secrets, CRDs, Helm, and Argo CD. This project connects those objects through operating a believable application.

The instructor acts as the software team and supplies application source, Dockerfiles, and prebuilt application images. Students act as the Kubernetes operations team. The lessons cover deployment through monitoring metrics; CI and image-building instruction are outside the teaching scope.

The agreed application is an e-commerce shop with frontend, backend, asynchronous worker, database, and queue. The target is a local kind cluster with one control-plane node and two worker nodes on an Apple M4 MacBook Pro with 24 GB RAM. All runtime dependencies run locally in that cluster. Argo CD additionally needs a reachable Git source during the GitOps lesson. No cloud application services are required.

The name CloudCart and specific technologies and feature limits below originated as assistant recommendations and were accepted with the architecture on 2026-10-16. Exact version pins and measured resource values remain implementation decisions. Lesson durations are deliberately unspecified.

## Application scope

A single-store shop supports product browsing, a persistent cart, guest checkout, order history for the current guest session, and an order-status page. Seeded products have names, prices, stock quantities, and bundled static images. An instructor-only admin page shows stock and recent orders. Protect its API with a seeded instructor account; provide credentials through a Secret and store password hashes, not plaintext passwords, in the database. Guest order access must be tied to the guest session, not an arbitrary order ID.

Checkout uses a clearly labelled simulated payment result. A worker creates a receipt record and simulates packing and dispatch. Receipts are rendered from database records; PDF generation, uploads, object storage, real payment integration, shipping APIs, multiple sellers, and customer account registration are outside the baseline.

The UI exposes understandable business states: accepted, processing, fulfilled, and failed, plus when processing is awaiting queue publication. It displays the application version. A backlog should be visible without requiring students to read source code.

## Application architecture and technology

This is a modular backend with asynchronous processing. Catalog, cart, inventory, and orders share one backend and database, with a separately deployed worker. No further domain-service decomposition is required for the lessons.

| Component | Proposed technology | Responsibility |
| --- | --- | --- |
| Frontend | React and TypeScript, static assets served by Nginx | Storefront, guest cart, order tracking, instructor admin UI |
| API | Python and FastAPI | HTTP endpoints, validation, sessions, transactional checkout, metrics |
| Worker | Python, Celery | Receipt creation and simulated fulfillment |
| Database | PostgreSQL | Products, carts, sessions, orders, stock reservations, receipts, outbox |
| Queue | RabbitMQ | Durable task delivery and observable processing backlog |

The API and worker share a Python source tree and may share a container image with different startup commands. Frontend assets are a separate image. Provide ARM64 images for the instructor's M4; also supply AMD64 variants if the student distribution targets Intel/AMD hosts. Select and pin exact image, chart, Kubernetes, and dependency versions during implementation after checking compatibility; never use mutable latest tags in teaching releases.

### Request and order processing

1. The browser uses one application origin. Gateway routing sends the storefront to the frontend Service and API requests to the API Service.
2. The API persists carts and opaque guest sessions in PostgreSQL. Use HTTP-only session cookies and appropriate same-origin protections for state-changing endpoints.
3. Checkout validates current prices and stock server-side. In one database transaction it reserves inventory, creates the order, and writes an outbox event. Guard concurrent stock updates against overselling. A client idempotency key prevents duplicate orders when checkout is retried.
4. A small background publisher in each API process checks the outbox. Database locking/claiming coordinates replicas. The publisher uses persistent messages, durable queues, bounded broker timeouts, and publisher confirms; it marks an event published only after confirmation. A broker interruption leaves accepted orders pending for retry.
5. Celery workers consume the task, create the receipt, and advance the simulated fulfillment state. Store durable business state in PostgreSQL, without adding Redis as a result backend.
6. A job may be delivered more than once. Use database-enforced uniqueness and guarded state transitions so repeated execution cannot duplicate a receipt or apply fulfillment twice. Configure acknowledgements, worker-loss behavior, bounded retries with backoff, and failed-job recording explicitly. A restart alone is not a delivery guarantee.
7. The frontend polls order status. Completed orders and receipt views remain available after application Pod replacement.

Keeping the outbox publisher inside the API is an assistant choice to preserve the five-component baseline. It must have a managed lifecycle, bounded work, and independent tests. Its queue connection failure must not block unrelated HTTP requests or invalidate an otherwise usable API replica.

## Kubernetes platform

| Concern | Proposed choice |
| --- | --- |
| Cluster | kind; one control plane and two workers; application scheduling on workers |
| Network policy enforcement | Calico, installed using a verified kind-compatible configuration |
| External access | Traefik with Gateway API, Gateway, and HTTPRoute; explicit host port mappings for macOS |
| Local hostname and TLS | Local shop hostname mapped to loopback; instructor-provided local certificate in a TLS Secret with documented browser trust setup |
| App workloads | Deployments for frontend, API, and worker |
| Stateful workloads | Single-instance PostgreSQL and RabbitMQ StatefulSets, each with a PVC |
| Service discovery | ClusterIP Services; internal database and broker endpoints |
| Packaging | Plain teaching manifests first; one application Helm chart later; pinned infrastructure charts with lab-specific values |
| GitOps | Argo CD, single-instance lab installation, using the application Helm chart from a reachable Git repository |
| Resource autoscaling | Metrics Server and a CPU-based API HPA |
| Monitoring | Prometheus Operator, Prometheus, Grafana, kube-state-metrics, kubelet/container metrics, PostgreSQL exporter, RabbitMQ Prometheus plugin |

Traefik is the accepted routing choice. Its Gateway API support gives CRDs a practical use. The community ingress-nginx controller retired in March 2026 and should not be selected for this new project. Nginx serving frontend static files is a separate use of Nginx.

Start with frontend=2, API=2, worker=1, PostgreSQL=1, and RabbitMQ=1. Spread stateless replicas across the two workers. The API HPA may scale from two to four replicas, subject to a measured resource budget. Scale the worker manually from one to three replicas to demonstrate backlog recovery. Worker queue-based autoscaling is outside the baseline.

Set requests and limits, startup/readiness/liveness probes, graceful termination, non-root application containers, and minimum RBAC permissions. Liveness checks detect a stuck process; they must not restart healthy applications just because PostgreSQL or RabbitMQ is temporarily unavailable. API readiness reflects whether it can serve its supported requests; broker failure is handled by the durable outbox. Workers stop taking new tasks and handle in-flight work during termination.

Demonstrate topology spread and a PodDisruptionBudget on replicated application workloads. Explain that a PDB concerns voluntary disruptions and does not guarantee availability during node loss. Single-instance stateful workloads are explicitly not highly available.

Namespace-level default-deny policies permit only required traffic: gateway to application HTTP endpoints, API to PostgreSQL and RabbitMQ, workers to PostgreSQL and RabbitMQ, DNS, and monitoring scrapes/exporter database access. Verify enforcement using a denied connection and an allowed connection; applying YAML alone does not prove enforcement.

## Storage and laptop resource boundaries

Use kind's verified local dynamic storage setup for the baseline. Document PVC binding, node affinity, reclaim behavior, and reset procedures. Deleting and recreating a database Pod on its storage node demonstrates persistence. Node-local volumes do not promise cross-node failover or survival after deleting the kind cluster. A worker-node outage can therefore leave PostgreSQL or RabbitMQ unavailable even while stateless replicas continue elsewhere.

Three containerized nodes share one physical laptop and its Docker VM. They provide scheduling and disruption exercises, not independent machine failure domains.

Start by evaluating a Docker VM allocation around 12–14 GiB and the CPU available on the actual machine; this is a planning estimate, not a measured requirement. Install infrastructure incrementally and record observed idle and loaded usage. Use one monitoring replica, short Prometheus retention (initial target 24 hours), a storage size cap, and disable unused monitoring components. Enable only collectors that work in kind; avoid unexplained red dashboards for inaccessible control-plane targets. Node/VM metrics must be labelled accurately rather than presented as macOS host metrics.

Use a trimmed kube-prometheus-stack configuration with Alertmanager disabled. A local Helm installation must work before enabling Argo CD ownership. The GitOps chapter needs a repository reachable from Argo CD; prepare the configuration with a documented repository URL input. Repository hosting, credentials, and publishing remain instructor setup choices. They do not require a Git server workload in the application architecture.

## Monitoring endpoint of the course

Metrics Server supplies the resource metrics API for kubectl top and CPU HPA. Prometheus scrapes time-series metrics; Grafana displays them. No Prometheus adapter is needed for this CPU-based HPA design.

Provide three provisioned dashboards:

| Dashboard | Required observations |
| --- | --- |
| Kubernetes workload health | Ready versus desired replicas, Pod restarts, CPU, memory, requests/limits, HPA replica count |
| Application and orders | HTTP request rate, error rate, p95 latency, accepted/fulfilled/failed order counts, pending publication backlog, processing duration and queue wait |
| Dependencies and processing | RabbitMQ ready/unacknowledged messages, consumers and redeliveries; PostgreSQL availability and connections; worker completions, retries, and failures |

Application counters/histograms must aggregate correctly across replicas and worker processes. Durable business counts come from PostgreSQL; avoid summing duplicate per-replica database gauges. Use bounded metric labels such as route templates, method, outcome, and version. Never label time series with order IDs, session IDs, or customer details. Correlate individual orders through structured application logs instead.

Include ServiceMonitor/PodMonitor resources, minimal PromQL examples, and a repeatable traffic generator with a fixed run length and concurrency cap. Provide normal traffic, browsing/API load, and order-processing backlog scenarios. A normal shop request may not be CPU-heavy enough to trigger HPA: include a documented, bounded lab-only workload mode for a reproducible scaling exercise, disabled by default. Grafana panels must distinguish attempt counters from unique completed orders and queue wait from execution duration.

The course ends with students reading and explaining metrics under load and controlled failure. Centralized logging infrastructure, distributed tracing, alert notification routing, service meshes, multi-cluster operations, and stateful HA are outside this baseline. Basic kubectl logs and events remain part of everyday troubleshooting.

## Teaching sequence and proof of success

1. Receive the software-team handoff: source, Dockerfiles, prebuilt images, release notes, ports, environment settings, dependency contracts, health endpoints, metrics, and runbook. Load the provided images onto all eligible kind nodes. No classroom build pipeline is necessary.
2. Deploy database and broker with storage, then the application. Run migrations and idempotent seed operations as explicit Jobs before enabling traffic. Verify product browsing, checkout, and fulfillment.
3. Configure routing and local TLS, application settings, Secrets, resource policies, and namespace/RBAC/network access. Prove an allowed and denied connection.
4. Exercise probe behavior, replacement of a failed stateless Pod, persistence after stateful Pod replacement, rolling releases, and rollback to a supplied compatible image. Restrict release migrations to backward-compatible changes for this lesson.
5. Stop worker consumers, create orders, observe the queue, restart/scale workers, and verify no duplicate business results. Interrupt RabbitMQ separately and verify accepted orders are eventually published from the outbox. Use a documented broker outage method that preserves broker identity and storage.
6. Run controlled traffic and demonstrate CPU-based API autoscaling. Explain resource requests and capacity limits on the two workers.
7. Package the resources with Helm, then introduce Argo CD reconciliation. Transfer ownership deliberately: remove the manually installed release/resources before the GitOps-managed installation, after the instructor's documented data preservation/reset step. Never leave two deployment methods managing the same resources. Demonstrate drift repair and a Git-based release/revert; perform experiments through declared configuration once reconciliation is enabled.
8. Install/configure monitoring and replay the traffic/backlog scenarios. Students use dashboards to explain which component is saturated or unavailable, whether scaling helped, and whether processing recovered correctly.

Infrastructure prerequisites can be installed before the chapter that teaches them; notably, Metrics Server is required for the autoscaling exercise. Runbooks provide a known reset point between failure demonstrations. Each exercise names the action, expected application behavior, Kubernetes observations, recovery step, and pass condition. Run and time every exercise on the actual M4 cluster before treating the teaching kit as ready.

## Deliverables and implementation boundaries

The eventual project includes application source, Dockerfiles, versioned prebuilt image archives/tags, plain manifests, application Helm chart, infrastructure values, Argo CD definitions, dashboards and scrape definitions, bounded traffic scenarios, instructor runbook, student exercises, and a concise software-team handoff document. Local loading of images and external retrieval of infrastructure charts/images must be documented; a fully air-gapped kit is not a current requirement.

The builder chooses exact library versions, schema/module structure, migration tooling, styling, seed data, exporter implementation, local certificate generation, and detailed resource values while preserving the behavior above. Verify ARM64 availability and a compatible Kubernetes/Calico/Traefik/Gateway API/monitoring matrix before pinning versions. Exact session lengths, a public release destination, and student-host portability can be settled later without blocking an implementation plan.

No application implementation, infrastructure installation, cluster creation, repository initialization, remote publishing, or deployment is part of writing this design. The next stage after instructor approval is an implementation plan.

## Primary references checked on 2026-10-16

- [kind configuration and multi-node limitations](https://kind.sigs.k8s.io/docs/user/configuration/)
- [Traefik Gateway API routing](https://doc.traefik.io/traefik/reference/dynamic-configuration/kubernetes-gateway/)
- [Kubernetes ingress-nginx retirement](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/)
- [Calico policy enforcement](https://docs.tigera.io/calico/latest/network-policy/get-started/kubernetes-policy/kubernetes-network-policy)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)
- [Metrics Server](https://kubernetes-sigs.github.io/metrics-server/)
- [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/blob/main/charts/kube-prometheus-stack/README.md)
- [RabbitMQ Prometheus plugin](https://github.com/rabbitmq/rabbitmq-server/blob/main/deps/rabbitmq_prometheus/README.md)
- [FastAPI background-work guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Celery task acknowledgement and idempotency](https://docs.celeryq.dev/en/latest/userguide/tasks.html)
