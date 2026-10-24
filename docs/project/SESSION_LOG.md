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

## 2026-10-24 — P02 merged into main

- At the instructor's request, pushed `claude/p02-catalog-carts-access-875a84` and opened [PR #1](https://github.com/sarojsanyasicst/DSO202-K8s/pull/1); a pre-push check found no credentials or personal data beyond labelled test values.
- The instructor asked for a merge commit: PR #1 was merged on GitHub at 16:25 (+0600) as `97aba5a` (parents `1ddb042` and `ae2ec1e`), and local `main` was fast-forwarded to it. The merged tree is identical to the tested branch head `ae2ec1e`. The repository has no CI checks, so local test runs remain the evidence.
- The GitHub web merge recorded the account's primary email on `97aba5a` instead of the noreply identity (D018). The instructor chose to keep the commit rather than rewrite public `main`; later merges should use GitHub's email privacy setting or a local merge.
- Next: P03 when requested.

## 2026-10-24 — P03 atomic checkout and durable order contract

- The instructor requested P03. Work ran inline (superpowers executing-plans) in worktree branch `claude/p03-start-ce835d`, with test-first development and one fresh whole-branch review.
- Settled the checkout contract and storage (D024–D026): `POST /api/v1/orders` with `cart_version`, a simulated `payment_outcome`, and a required `Idempotency-Key`; 201/200 for new/replayed orders, 409 for conflicts, 402 for declines; cart-then-products-by-id lock order with guarded stock updates; one outbox event and at most one receipt per order.
- Delivered the orders module, migration `e7b83d9b2137`, guest order/receipt reads, and 56 new or extended tests (`50aca8d`, `e910f54`, `bf08d29`). Consolidated duplicated test helpers into `tests/helpers.py` and added the requested `RequestBodyLimit` unit test.
- Verified on `bf08d29`: 42 unit and 154 integration tests passing, Alembic `check` and round trip, mutation checks for every concurrency and idempotency guard. See [verification](VERIFICATION.md).
- The review found no Critical issues. Its one Important item, a missing test for the product lock order, was fixed. Five minor items were deferred (see [handoff](HANDOFF.md)).
- Next: P04 when requested. The branch is local only: not pushed and not merged into `main`.

## 2026-10-24 — P03 merged into main

- At the instructor's request, pushed `claude/p03-start-ce835d` and opened [PR #2](https://github.com/sarojsanyasicst/DSO202-K8s/pull/2) (ready for review). All five branch commits use the noreply identity.
- The instructor chose a local merge: merge commit `fb50bc9` (parents `30544c8` and `de1391e`, noreply author and committer) was created on top of `origin/main` and pushed to `main` together with this record. The merged tree is identical to the tested branch head `de1391e`.
- Full suite on `fb50bc9`, run under `caffeinate -i` to prevent the sleep interruption seen earlier: `42 passed` (unit) and `154 passed in 21.20s` (integration); test containers removed afterwards. The repository has no CI checks, so local runs remain the evidence.
- Next: P04 when requested.

## 2026-10-24 — P04 reliable publisher and fulfillment worker

- The instructor requested P04. Work ran inline (superpowers executing-plans) in worktree branch `claude/p04-start-3c8765`, test-first, with one fresh whole-branch review.
- Settled the publication and fulfillment design (D027–D031): an outbox publisher thread per API process with skip-locked claims and a 60 s lease, confirmed persistent mandatory publishing, bounded broker calls and exponential backoff; a solo-pool Celery worker with late acknowledgement and prefetch 1; durable attempt counting (at most four), backoff-then-requeue retries, stock returned once on failure; database errors outside an attempt requeue without using attempts.
- Delivered the `cloudcart.jobs` package, migration `674c483b8f18`, new settings, and 32 integration plus 19 unit tests with a TCP fault proxy and a worker harness (`a5668ca`, `280476b`, `5762706`, `049b220`).
- Found and fixed during the work: RabbitMQ 4.3 refuses Celery's remote-control queue (remote control disabled); an idle worker needed up to 10 s to honour SIGTERM (one-second wake-up bootstep).
- Verified on `049b220`: 61 unit and 186 integration tests passing, Alembic `check` and round trip, 15 mutation checks. See [verification](VERIFICATION.md).
- The review found no Critical issues; its one Important item (a non-connection database error dropped the task) was fixed with a failing-first test. Ten minors were deferred or ruled on (see [handoff](HANDOFF.md)).
- Next: P05 when requested. The branch is local only: not pushed and not merged into `main`.
