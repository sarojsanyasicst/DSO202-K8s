# Session history

Append outcomes in chronological order. Use [HANDOFF.md](HANDOFF.md) for the current continuation point and [PROJECT_STATUS.md](../../PROJECT_STATUS.md) for milestone status.

## 2026-10-16 — Architecture and implementation planning

- Chose the e-commerce application after comparing project ideas.
- Agreed on frontend, backend, worker, PostgreSQL, and RabbitMQ, targeting kind with one control-plane node and two workers on M4/24 GB.
- Set the teaching endpoint to monitoring metrics.
- Prepared the design, completed a builder-gap check, and obtained instructor approval of the architecture.
- Prepared the 12-task implementation plan. Application tasks were not executed.

## 2026-10-16 — Project structure and progress tracking

- The instructor requested a project structure and persistent progress records.
- Added the project folders, entry-point documentation, status board, roadmap, decision log, verification record, and handoff.
- Added working conventions, agent continuation instructions, and local/generated-file ignore rules.
- Kept runnable application/deployment files for their owning future milestones.
- Verified 23 Markdown files, 39 local document links, 23 placeholder folders, and consistent P01–P12 status/plan IDs.
- Scope: structure/documentation only; no packages installed, images built, cluster created, remote repository published, or application tests run.
- Next implementation milestone: P01, when requested. See [verification](VERIFICATION.md) for structural checks.

## 2026-10-23 to 2026-10-24 — P01 runnable database foundation

- The instructor requested implementation and limited this session to P01.
- Checked host tools, Docker allocation, kube contexts, and existing clusters read-only; the unrelated `dso202` cluster and other containers were left untouched.
- Initialized the local Git repository (`main`, baseline docs commit `ee657bc`) and implemented P01 on branch `p01-database-foundation` with subagent implementation and reviews.
- Delivered the locked Python 3.13 backend project, settings, database lifecycle, app factory, Alembic scaffolding, disposable Compose PostgreSQL/RabbitMQ, Make targets, version matrix, and instructor prerequisites.
- Re-pinned Python from 3.15 to 3.13 because Celery/Kombu do not declare newer versions; removed the unused Uvicorn dependency until Task 6; fixed final-review findings (secret leak through exception context, connection keepalive bounds, test isolation and loopback guard).
- Verified on `aab9757`: 37 unit and 7 integration tests passing, dependencies healthy and removed cleanly. See [verification](VERIFICATION.md).
- Side effect on the host: uv downloaded CPython 3.15.0rc2 and 3.13.15 into its interpreter store and added a `~/.local/bin/python3.13` link.
- Next: P02 when requested. The branch is not yet merged into `main`.
