---
name: app-factory
description: "Coordinate a new App product or major lifecycle work from planning through release. For routine fixes, continue the existing project workflow without restarting product planning."
license: MIT
metadata:
  short-description: AI App Factory lifecycle orchestration
---

# App Factory

Use this workflow to coordinate a professional App lifecycle:

`Idea -> PRD -> UX/UI -> Architecture -> Coding -> Testing -> Deployment -> Release -> Maintenance`.

## Priority and routing

For an App-project request, work in this order:

1. `app-factory` owns phase selection, scope, gates, and handoffs.
2. If installed and applicable, `keel` can provide second-level lifecycle review and documentation discipline. It is optional, independently licensed, and is not included in this package.
3. Load only an available specialized skill needed for the current phase. The names below are optional routing examples; do not load or install every skill merely because this workflow was selected. Without those skills, continue using the phase deliverables and exit criteria in this file. Report a missing capability only when it actually prevents the requested result, and continue independent work.

| Area | Optional specialized skill |
| --- | --- |
| Product planning / initial build | `app-builder` |
| Architecture | `keel` and `database-design` as needed |
| Frontend | `frontend-developer` |
| Backend | `backend-dev-guidelines` |
| Mobile | `mobile-developer` |
| Database | `database-design` |
| Testing | `testing-qa` |
| Security | `security-auditor` |
| Deployment | `deployment-engineer`, `docker-expert`, `github-actions-advanced` |

## Non-negotiable gates

- **No code before product planning is complete.** In Phases 1-2, analyze, ask only material questions, and produce planning artifacts; do not implement code.
- **No project scaffold, source, configuration, or application assets before architecture is complete.** Finish the Phase 4 technical design and use the user's existing confirmation when it covers that design; ask only for a material unresolved decision. Planning and design documents may be produced before then.
- **No extra features before the MVP is defined.** Put non-MVP ideas in a deferred backlog. Do not add them unless the user explicitly changes the MVP scope.
- Treat a phase as complete only after its exit criteria are met and the user has had a chance to correct a material product or technical decision. Continue autonomously on routine details.
- Do not publish, deploy to production, submit to an app store, or use credentials without the user's explicit authorization and required account access.
- Reuse valid authorization and agreed decisions from the current session. Do not ask again for covered actions. A skill does not grant additional permissions, account access, or authority to send messages, spend money, transfer sensitive data, or perform destructive operations.

For existing projects, identify the current phase and preserve established requirements, architecture, and user changes. Routine fixes and small edits continue from the affected phase; do not repeat discovery or architecture unless the change materially alters the product scope or system design.

## Phase 1 — Product Discovery

Deliver: user/problem analysis, market and competitor signals appropriate to the request, target users, risks and assumptions, and a prioritized MVP definition.

Exit: a single problem statement, target user, success measure, and MVP scope are agreed or clearly recorded as assumptions.

## Phase 2 — Product Specification

Deliver: PRD, user stories with acceptance criteria, feature breakdown, non-functional requirements, and a deferred backlog. Keep the MVP boundary explicit.

Exit: every MVP feature has a user value, acceptance criteria, and priority.

## Phase 3 — UX/UI

Deliver: user flows, key states and edge cases, wireframes or screen specifications, and a reusable design system direction. Validate accessibility and platform conventions relevant to the chosen target.

Exit: MVP journeys and their primary/empty/error states are specified well enough for architecture and implementation.

## Phase 4 — Architecture

Deliver: justified technology choices, system boundaries, database design, API contracts, authentication/authorization approach, observability plan, test strategy, and an implementation plan. Record consequential tradeoffs.

Exit: architecture resolves data ownership, API boundaries, deployment target, security posture, and the build/test/release path. Only after this gate may project scaffolding begin.

## Phase 5 — Development

Implement only approved MVP work. If available and relevant, route web/client work to `frontend-developer`, server work to `backend-dev-guidelines`, mobile work to `mobile-developer`, and data work to `database-design`; otherwise use the project's existing workflow. Keep changes small, reviewable, and aligned with the approved architecture.

Exit: MVP acceptance criteria are implemented and developer checks pass.

## Phase 6 — Quality

Run checks proportionate to the affected behavior and release risk. If installed, load `testing-qa` for substantive test planning or validation work, and `security-auditor` when a requested audit or concrete security concern requires it. Existing project checks remain usable without either skill. Fix confirmed blockers, document residual risks, and do not claim unrun checks passed.

Exit: critical paths are tested, security findings have a disposition, and release-blocking defects are resolved or explicitly accepted by the user.

## Phase 7 — Deployment

Prepare a reproducible deployment path for the chosen target. Use Docker/container configuration only where relevant, and use `github-actions-advanced` or `deployment-engineer` if installed and applicable. These optional skills do not require changing the project's stack. Separate preview/staging from production. Keep secrets out of source control and archives.

Exit: a verified non-production deployment path exists, rollback is described, and production authorization is obtained before any live change.

## Phase 8 — Release

Prepare store metadata and compliance materials for App Store and/or Google Play when applicable, release notes, versioning, production monitoring, and incident ownership. Submission and production release require explicit user authorization.

Exit: release artifacts, monitoring, rollback, and support handoff are ready; record what was actually released versus prepared only.

## Phase 9 — Iteration

Use analytics, user feedback, reliability signals, and version-upgrade needs to propose a prioritized iteration plan. Re-run discovery/specification gates for material scope changes.

Exit: the next validated hypothesis or maintenance task is prioritized without silently expanding the MVP.

## Working record

At each handoff, state the current phase, completed deliverables, open assumptions or decisions, MVP scope, and the next gate. For an existing App, first identify its current phase and preserve existing user work.
