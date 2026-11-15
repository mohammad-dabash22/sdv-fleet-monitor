# Vendored skills (V1)

The skills in `.claude/skills/` are copied unchanged from their source repos. All three repos are MIT licensed; the licenses are in `licenses/`.
V1 uses them as is. V2 customizes them; `git diff skills-v1 skills-v2 -- .claude/skills` shows every change.

## Sources

| Repo | Commit | License |
|---|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` | MIT |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | `301b02b12bff98e4688e6984af6556802322bbde` | MIT |
| [obra/superpowers](https://github.com/obra/superpowers) | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT |

## Selection

Five skills, one per SDD step, so no two skills compete for the same job.

| Step | Skill | Source | Why this one |
|---|---|---|---|
| Requirements | `grilling` | mattpocock | Interviews one question at a time and looks facts up itself instead of asking |
| Spec, plan, tasks | `spec-driven-development` | addyosmani | Gated phases: specify, plan, tasks, implement; nothing moves on without approval |
| Build | `tdd` | mattpocock | Red-green-refactor with guidance on what to mock |
| Verify | `verification-before-completion` | superpowers | No "done" without command output as evidence |
| Review | `code-review-and-quality` | addyosmani | Multi-axis review, works without an issue tracker |

Not taken:
- The TDD skills from addyosmani and superpowers duplicate `tdd`.
- addyosmani `planning-and-task-breakdown` and `incremental-implementation` overlap the plan and tasks phases of `spec-driven-development`.
- mattpocock `code-review` needs an issue tracker set up first; `code-review-and-quality` doesn't.
- The superpowers planning skills depend on several other superpowers skills.

## Known limitations

- `spec-driven-development` refers to addyosmani's `test-driven-development`, `incremental-implementation` and `context-engineering`, which are not vendored; `tdd` covers the first.
- `code-review-and-quality` refers to `security-and-hardening`, which is not vendored.
- Nothing ties a requirement id to a test yet; traceability is manual in V1.
