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
- Initialized the local Git repository (`main`, baseline docs commit `07181a2`) and implemented P01 on branch `p01-database-foundation` with subagent implementation and reviews.
- Delivered the locked Python 3.13 backend project, settings, database lifecycle, app factory, Alembic scaffolding, disposable Compose PostgreSQL/RabbitMQ, Make targets, version matrix, and instructor prerequisites.
- Re-pinned Python from 3.15 to 3.13 because Celery/Kombu do not declare newer versions; removed the unused Uvicorn dependency until Task 6; fixed final-review findings (secret leak through exception context, connection keepalive bounds, test isolation and loopback guard).
- Verified on `bfe4fee`: 37 unit and 7 integration tests passing, dependencies healthy and removed cleanly. See [verification](VERIFICATION.md).
- Side effect on the host: uv downloaded CPython 3.15.0rc2 and 3.13.15 into its interpreter store and added a `~/.local/bin/python3.13` link.
- Next: P02 when requested. The branch is not yet merged into `main`.

## 2026-10-24 — Remote repository

- The instructor added the public GitHub remote `origin` (https://github.com/sarojsanyasicst/DSO202-K8s) and renamed the P01 branch to `main`, so P01 is integrated without a separate merge.
- Before the first push, the eight local commits were rewritten from the university email to the GitHub noreply identity, with dates and file contents unchanged. Commit hashes cited in project records were updated to the new values (for example, P01 now spans `1d1783a`..`bfe4fee`).
- Checked the tracked files for credentials and personal data before publishing: none found besides the labelled disposable test credentials.

## 2026-10-24 — P02 catalog, persistent carts, and access boundaries

- The instructor requested P02. Work ran in worktree branch `claude/p02-catalog-carts-access-875a84` with a subagent implementer, a task review, and a final whole-branch review.
- Settled eleven design questions before implementation (recorded as D019–D023): Argon2id via `argon2-cffi`, hashed opaque session tokens with fixed lifetimes, Strict HttpOnly cookies secure by default, an HMAC session-bound CSRF token plus Origin/`Sec-Fetch-Site` checks, seed password from `CLOUDCART_SEED_ADMIN_PASSWORD`, and cart limits with a version counter.
- Delivered catalog, identity, and cart modules, migration `371b57c4f5aa`, the idempotent seed command, and 93 new integration tests (`c01e916`, `6f9f7c0`).
- Verified on `6f9f7c0`: 38 unit and 100 integration tests passing, migration downgrade/upgrade round trip, and seed reruns without duplicates. See [verification](VERIFICATION.md).
- Reviews found no Critical or Important code issues; ten minor items were deferred to later tasks with recorded rulings (see [handoff](HANDOFF.md)).
- Next: P03 when requested. The branch is not yet merged into `main`.
