# Verification record

Evidence belongs here; milestone status belongs in [PROJECT_STATUS.md](../../PROJECT_STATUS.md). Append future records with date, milestone, checks, result, limitations, and artifact locations. Generated outputs go under ignored `artifacts/verification/`; keep sanitized summaries here.

## 2026-10-16 — S00 structure and tracking

**Scope:** project folders, Markdown progress records, links, and planning consistency.

**Checks:** inspect the directory inventory; verify all local Markdown document targets exist; verify P01–P12 match the 12 implementation tasks and start as Not started; verify each planned source/deployment folder exists; check placeholder/README coverage; confirm application code and runtime configuration have not been introduced.

**Result:** passed. A one-off Python standard-library audit checked all 23 Markdown files and resolved all 39 local document links. All 12 milestone IDs match the implementation plan and remain Not started. All 23 `.gitkeep` markers are empty, and leaf folders have their intended documentation or markers. The 48 files are documentation, editor/ignore configuration, or placeholders. No application code or Git initialization was introduced.

**Method:** enumerate project files with `pathlib`; parse local Markdown links and milestone/task IDs; assert target existence, marker coverage, final newlines, and the expected documentation-only file types. No dependencies were installed for this check.

**Limitations:** no application tests, dependency installs, image builds, cluster checks, version compatibility checks, or runtime resource measurements. This is not deployment evidence.

## Future record format

```text
Date / milestone:
Change being verified:
Command or scenario:
Expected result:
Observed result:
Evidence files, if any:
Limitations / remaining checks:
```

## 2026-10-24 — P01 runnable database foundation

**Change being verified:** branch `p01-database-foundation`, commits `1d1783a`..`bfe4fee` on top of baseline `07181a2`. Locked uv backend project (Python 3.13, 32 packages), `Settings.from_env()` with lab-limit validation, `Database` session lifecycle with bounded timeouts, `create_app()` lifespan, Alembic scaffolding (no revisions yet), disposable Compose PostgreSQL/RabbitMQ, Make targets, version matrix, instructor prerequisites.

**Host observed (read-only, 2026-10-23):** Apple M4 arm64, 12 CPU, 24 GiB RAM. Docker Desktop server 29.5.3 with VM memory 8321232896 bytes (~7.75 GiB) and 12 CPUs; Compose v5.1.4. Tools: git 2.54.0, uv 0.12.17, python3 3.14.2, kind v0.32.0, kubectl client v1.36.4, helm v4.3.0, GNU make 3.81, node v24.12.0, npm 11.6.2; `promtool` missing. Existing unrelated kind cluster `dso202` (kindest/node:v1.36.1, binds 127.0.0.1:80/443/30080); kube contexts `kind-dso202` (current) and `saroj`; other containers `hall-booking-local-postgres` (127.0.0.1:5433) and `document-hub-postgres-1` (0.0.0.0:5432). None were changed.

**Commands (run by the session controller on HEAD `bfe4fee`, 2026-10-24 09:11 +0600):**

| Command or scenario | Expected | Observed |
| --- | --- | --- |
| `uv lock --check --project services/backend` | Lock matches pyproject | `Resolved 32 packages` |
| `make test-unit` | Settings and guard tests pass | `37 passed` |
| `make test-deps-up` | Both dependencies healthy, loopback only | `postgres:18.6-trixie` healthy on 127.0.0.1:15432; `rabbitmq:4.3.7-management` healthy on 127.0.0.1:15672 (AMQP) and 127.0.0.1:15673 (management) |
| `make test-integration` | Migrations, session commit/rollback, timeouts, lifespan disposal, broker handshake pass against real dependencies | `7 passed` |
| `make test-integration TEST_POSTGRES_URL='...@127.0.0.1:15432/postgres?host=db.example.com'` | Destructive fixture refuses a redirected host | Every test errors at setup: "must not contain query parameters (host)" |
| `make test-deps-down` | No project containers/networks/volumes remain | 0 containers, 0 networks, 0 volumes; `dso202` and other containers still up; context still `kind-dso202` |

**TDD evidence:** settings tests failed at import (`No module named 'cloudcart.config'`) before implementation, then passed. Review-fix changes were checked by temporarily breaking each fix and observing the matching test fail (implementer report).

**Reviews:** task review (spec + quality) approved after one fix round; final whole-branch review "with fixes"; one fix wave (`bfe4fee`) and a scoped re-review.

**Limitations / remaining checks:** local tests ran on CPython 3.13.15 while the pinned image is `python:3.13.17-slim-trixie` (uv 0.12.17 cannot install 3.13.17). The libpq `tcp_user_timeout` setting is only effective on Linux; on macOS the test proves the value reaches libpq. Platform versions in `versions.yaml` are selected from primary sources but not installed or exercised; Gateway API minimum Kubernetes version and kube-prometheus-stack on Kubernetes 1.36 are `partially_verified`. No images, cluster, manifests, or dashboards exist yet. The 7.75 GiB Docker VM has not been measured against a running cluster.
