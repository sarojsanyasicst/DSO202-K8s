# Host prerequisites

What the instructor's Apple Silicon Mac needs before working on CloudCart, and how to check each item. The selected component versions, their ARM64 evidence, and compatibility notes are in [deploy/platform/versions.yaml](../../deploy/platform/versions.yaml). This page covers the host tools only.

**Status (2026-10-23):** these checks support the P01 backend foundation. The tool versions below were observed on the M4 target. Checks for later milestones (cluster creation, image import, Calico, Traefik, Metrics Server, Argo CD, monitoring, browser tests, Prometheus rule tests) are **pending** and are not proven by this list.

## Host

| Item | Requirement | Check | Observed 2026-10-23 |
| --- | --- | --- | --- |
| Machine | Apple Silicon (arm64) Mac; target is an M4 with 24 GB RAM | `uname -m`; `sysctl -n hw.memsize` | arm64, 24 GiB, macOS 26.6.2 |

## Tools

| Tool | Pinned / minimum | Used for | Check | Observed 2026-10-23 |
| --- | --- | --- | --- | --- |
| Docker Desktop (Engine) | Engine 29.x | Test dependencies, kind nodes | `docker version --format '{{.Server.Version}}'` | 29.5.3 (CLI 29.1.3) |
| Docker Compose plugin | Compose v2 or newer with `up --wait` | `make test-deps-up` | `docker compose version` | v5.1.4 |
| GNU make | 3.81 or newer (macOS default is 3.81) | `make` targets | `make --version` | 3.81 |
| git | Any current release | Version control, Argo CD source | `git --version` | 2.54.0 |
| uv | 0.12.17 or newer | Python interpreter, locked dependencies, test runs | `uv --version` | 0.12.17 |
| Python | CPython 3.13 (provided by uv; no system Python needed) | Backend | `uv run --project services/backend python -VV` | 3.13.15 via uv 0.12.17 |
| kind | v0.32.0 (pinned) | Local cluster (Task 7) | `kind version` | v0.32.0 |
| kubectl | v1.35–v1.37 (within one minor of Kubernetes v1.36) | Cluster operations | `kubectl version --client` | v1.36.4 |
| Helm | v4.3.x (pinned v4.3.1) | Charts (Tasks 7, 10, 11) | `helm version --short` | v4.3.0 |
| Node.js / npm | To be pinned by Task 5 | Frontend build and browser tests | `node --version`; `npm --version` | v24.12.0 / 11.6.2 |
| promtool | To be pinned by Task 11 | Prometheus rule tests | `promtool --version` | not installed |

The backend is pinned to Python 3.13 because Celery and Kombu declare support only up to 3.13. uv 0.12.17 offers managed CPython up to 3.13.15; the release image is `python:3.13.17-slim-trixie`. A newer uv can provide the matching patch: run `uv python install 3.13`, then recreate `services/backend/.venv`, for example by deleting it and rerunning `make test-unit`.

Nothing on this list is installed or upgraded by the project's commands, except the interpreter and Python packages uv manages.

## Docker resources

The design starts from evaluating a Docker VM of about **12–14 GiB** memory, alongside the CPUs available on the actual machine. That figure is a planning estimate, not a measured requirement. The current VM has **7.75 GiB and 12 CPUs**, below that starting point. This is enough for the disposable PostgreSQL and RabbitMQ test containers. The three-node kind cluster with the platform components has not been measured yet; Task 7 records real idle and loaded usage.

Check the allocation:

```sh
docker info --format 'memory={{.MemTotal}} cpus={{.NCPU}}'
```

Change it in Docker Desktop under **Settings → Resources**. This is an instructor decision; project scripts never change it.

## Ports

The disposable test dependencies bind to loopback only:

| Host port | Container | Purpose |
| --- | --- | --- |
| 127.0.0.1:15432 | PostgreSQL 5432 | Test database server |
| 127.0.0.1:15672 | RabbitMQ 5672 | AMQP 0-9-1 |
| 127.0.0.1:15673 | RabbitMQ 15672 | Management UI and HTTP API |

Check that a port is free before `make test-deps-up` (no output means free):

```sh
lsof -nP -iTCP:15432 -sTCP:LISTEN
```

## Existing clusters and contexts

This Mac may already run unrelated kind clusters and Compose projects. For example, on 2026-10-23 a cluster `dso202` was running and `kind-dso202` was the current kubectl context, binding 127.0.0.1:80, 443 and 30080. Inspect them read-only before any cluster work:

```sh
kind get clusters
kubectl config get-contexts
kubectl config current-context
docker compose ls
```

**Never delete, recreate, or reconfigure a cluster or context you did not create for CloudCart.** CloudCart uses its own names: kind cluster `cloudcart`, context `kind-cloudcart`, and Compose project `cloudcart-test`. Pass the context explicitly (`kubectl --context kind-cloudcart ...`) instead of switching the current context. Treat deleting the `cloudcart` cluster or its PVCs as a destructive action that needs explicit authorization.

## Backend foundation check

From the repository root:

```sh
make test-unit
make test-deps-up      # waits until PostgreSQL and RabbitMQ are healthy
make test-integration
make test-deps-down    # removes the containers and their tmpfs data
```

Recorded results are kept in [VERIFICATION.md](../project/VERIFICATION.md).
