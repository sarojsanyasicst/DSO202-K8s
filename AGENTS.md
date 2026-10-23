# CloudCart project instructions

## Start of work

- Read `PROJECT_STATUS.md` and `docs/project/HANDOFF.md` before continuing.
- Use the approved architecture in `docs/superpowers/specs/2026-10-16-cloudcart-design.md` and the task interfaces in `docs/superpowers/plans/2026-10-16-cloudcart-implementation.md`.
- Follow the requested task scope. Project structure and tracking are prepared; application implementation has not started.
- Frontend, API, worker, PostgreSQL, and RabbitMQ are the five application components. API and worker share Python business code.
- Target kind with one control plane and two workers on Apple M4/24 GB. Classroom scope ends with metrics monitoring; CI/image builds are supplied background material.

## Progress records

- Follow `CONTRIBUTING.md` for updates.
- `PROJECT_STATUS.md` owns milestone status; the implementation plan owns detailed step checkboxes.
- Record actual validation in `docs/project/VERIFICATION.md`; never mark a milestone done without its acceptance proof.
- Append session outcomes to `docs/project/SESSION_LOG.md` and refresh `docs/project/HANDOFF.md` before finishing a milestone or leaving partially completed work.
- Keep decisions and rationale in `docs/project/DECISIONS.md`.
- For a documentation-only change, use proportionate structural/link checks. Do not install dependencies or deploy infrastructure just to check Markdown.

## graphify

- When the user types `/graphify`, read and follow the installed graphify skill before doing anything else for that request.
- Use the available skill location; do not assume the legacy `~/.Codex/skills/graphify/SKILL.md` path exists.

## Scope and safety

- Preserve user changes. Keep generated artifacts and credentials out of source control.
- Name the project context explicitly for cluster operations. Treat PVC resets and cluster deletion as destructive actions, requiring the authorization appropriate to the task.
- Report unrun checks as pending. Never infer that source files, images, manifests, or dashboards work merely because they exist.
