# Working on CloudCart

## Before making changes

Read [project status](PROJECT_STATUS.md), the [handoff](docs/project/HANDOFF.md), and the requested milestone in the [implementation plan](docs/superpowers/plans/2026-10-16-cloudcart-implementation.md). The [approved design](docs/superpowers/specs/2026-10-16-cloudcart-design.md) defines the scope.

Work on the requested milestone. Creating this structure does not mean the full implementation is underway. Reuse the existing folders and add runnable files when their owning task begins; do not fill the project with dummy application modules or empty deployment manifests.

## Progress workflow

1. Set the active milestone to **In progress** in `PROJECT_STATUS.md` and identify its next concrete deliverable.
2. Implement the relevant steps and maintain their checkboxes in the detailed plan. A checked step means it was actually completed.
3. Run the checks appropriate to the change. Behavioral changes need meaningful regression proof; documentation/folder changes need structural and link checks, not invented application tests.
4. Record check commands, outcomes, limitations, and evidence in `docs/project/VERIFICATION.md`.
5. Mark the milestone **Done** only when its acceptance criteria are met. A prepared file is not proof that a deployment, image, or dashboard works.
6. Append a concise entry to `docs/project/SESSION_LOG.md`; refresh `docs/project/HANDOFF.md` with the next action. Update `CHANGELOG.md` for delivered changes and `DECISIONS.md` for architectural decisions.

Milestone status lives only in `PROJECT_STATUS.md`. The roadmap describes acceptance without duplicating live status. The implementation plan tracks individual steps. Preserve past verification records and session history; update the handoff in place.

Use ISO dates with the instructor's Asia/Thimphu timezone. Record exact times only when useful and known. Never invent test results, commits, deployment URLs, or version pins.

## Source and generated files

- Commit source, manifests, charts, dashboards, teaching documents, and sanitized release metadata once version control is initialized.
- Keep local environments, credentials, certificates/private keys, image archives, database backups, and generated evidence out of source control.
- Store local settings under `.local/`; store generated outputs under `artifacts/` in the documented subfolders.
- Use explicit target contexts for cluster-changing helpers; never silently delete a cluster or PVC.
- Do not expose application implementation details in the storefront unless they help its users.

## Completion standard

The final teaching kit must pass the acceptance scenarios on the actual M4 kind cluster, including image import, checkout correctness, policy enforcement, recovery, scaling, GitOps with a reachable repository, and populated metrics dashboards. Until those checks run, describe them as pending.
