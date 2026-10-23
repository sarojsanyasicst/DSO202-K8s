# CloudCart

A local e-commerce application and Kubernetes operations teaching project.

Students receive source code, Dockerfiles, and prebuilt images from the software team, then deploy and operate the application on kind. The course ends with Prometheus metrics and Grafana dashboards. CI and image-building instruction are outside the lessons.

**Current state:** the backend database foundation (settings, database sessions, Alembic setup, locked Python dependencies, and disposable test dependencies) is in place. Application features, images, Kubernetes resources, and dashboards have not been implemented. See [project status](PROJECT_STATUS.md) for verified progress.

## Start here

- [Project status](PROJECT_STATUS.md): current milestone and progress.
- [Roadmap](docs/project/ROADMAP.md): stages and completion criteria.
- [Session handoff](docs/project/HANDOFF.md): context and the next useful step.
- [Architecture](docs/superpowers/specs/2026-10-16-cloudcart-design.md): approved design.
- [Implementation plan](docs/superpowers/plans/2026-10-16-cloudcart-implementation.md): detailed task checklist.
- [Working conventions](CONTRIBUTING.md): how to update progress and verify work.

## Architecture

The application is a modular monolith with an asynchronous worker. React serves the storefront; FastAPI owns catalog, carts, inventory, sessions, and orders. PostgreSQL stores business data and an outbox; RabbitMQ delivers tasks to a separately deployed Celery worker. API and worker share Python code.

The target is an Apple M4 MacBook Pro with 24 GB RAM, running kind with one control-plane node and two workers. Supporting tools are Calico, Traefik/Gateway API, Metrics Server, Helm, Argo CD, Prometheus, and Grafana. Selected versions are recorded in [deploy/platform/versions.yaml](deploy/platform/versions.yaml); running them on the cluster and measuring resource requirements are still pending.

## Project layout

```text
.
├── AGENTS.md                 # Instructions for future project work
├── PROJECT_STATUS.md         # Single milestone status board
├── CHANGELOG.md              # Delivered changes
├── CONTRIBUTING.md           # Progress and validation workflow
├── services/
│   ├── backend/              # FastAPI API, shared domain logic, Celery worker
│   │   ├── src/cloudcart/
│   │   ├── alembic/          # Database migrations
│   │   └── tests/            # Backend unit and integration tests
│   └── frontend/             # React storefront and browser tests
├── containers/               # Application Dockerfiles
├── deploy/
│   ├── kind/                 # Local cluster configuration
│   ├── platform/             # Pinned platform versions and settings
│   ├── plain/                # Plain Kubernetes teaching manifests
│   ├── helm/cloudcart/       # Application Helm chart
│   └── gitops/               # Argo CD project and application definitions
├── monitoring/
│   ├── dashboards/           # Provisioned Grafana dashboards
│   ├── rules/                # Prometheus recording rules
│   └── tests/                # Rule and query verification
├── scripts/                  # Setup, packaging, acceptance, traffic, reset helpers
├── tests/                    # Shared acceptance helpers and test dependencies
├── artifacts/                # Generated images, evidence, backups; release metadata
└── docs/
    ├── project/              # Roadmap, decisions, history, verification, handoff
    ├── handoff/              # Software-team delivery contract
    ├── instructor/           # Setup, demonstrations, recovery, measured results
    ├── students/             # Kubernetes exercises
    └── superpowers/          # Approved design and detailed implementation plan
```

Folders contain placeholders until their owning task is implemented. Host prerequisites are listed in [docs/instructor/prerequisites.md](docs/instructor/prerequisites.md). Backend test commands exist (`make help` lists them); application launch commands arrive with later tasks.
