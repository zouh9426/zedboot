# ZeroWeave

[中文](README.md)

**A project-bootstrap orchestrator Skill.** When you start a project from scratch, ZeroWeave weaves three systems into it in one pass — a **project-management system** (five management documents + AI working rules), a **deployment system** (dedicated account + Docker + rsync push + private Git repo backup), and a **UI system** (invokes uiweft to generate DESIGN.md). It can also retrofit an existing project that lacks these systems until it looks as if they had been there from day one.

ZeroWeave runs once at bootstrap/retrofit time and then steps aside — day-to-day discipline lives in the files installed into your project (`AGENTS.md` + the five management documents), with no runtime dependency on this Skill.

## Requirements

Works with any AI coding tool that supports Agent Skills (`SKILL.md` format): Kimi Code, Claude Code, Codex, etc.

- **Required**: none.
- **Optional**: the UI track relies on [uiweft](https://github.com/zouh9426/uiweft). If it is missing, ZeroWeave tells you and pauses only the UI track; the management and deployment systems proceed normally.
- The deployment system is installed only for deployable code projects; no-deploy deliverable projects (reports, slide decks, etc.) get the management system only.

> Note: ZeroWeave's rulebooks and templates are written in Chinese. The workflows and file structure are language-agnostic, but the generated project documents will be in Chinese.

## Installation

Clone this repository into any skills directory:

```bash
# Kimi Code
git clone https://github.com/zouh9426/zeroweave ~/.kimi-code/skills/zeroweave
# or the shared location (works across tools)
git clone https://github.com/zouh9426/zeroweave ~/.agents/skills/zeroweave
```

Start a new session and the Skill will trigger automatically. Alternatively, paste the guided-install prompt from `SETUP.en.md` to your AI and let it handle installation and self-checks.

## Quick start

Tell your AI:

- **New project**: "Initialize this project from scratch with ZeroWeave" — it collects project identity, GitHub, server, and domain info up front ("TBD" answers are fine; they become tracked tasks), then installs the three systems.
- **Existing project**: "Retrofit this project with ZeroWeave" — it runs a read-only audit, produces a gap report and an adoption plan, and **only acts after your approval**; existing content is merged or archived, never business code.

## Two workflows

| Workflow | Scenario | Flow |
|---|---|---|
| init | Start from scratch | Dependency check → info collection → management → deployment → UI → close the loop |
| adopt | Retrofit existing | Audit (`scripts/audit.py`, read-only) → gap report → adoption plan (your call) → idempotent install → alignment |

## File structure

```text
zeroweave/
├── SKILL.md                 # Orchestration: mode detection, info collection, two workflows
├── references/              # Rulebooks (management rules, compact + reference; deployment guide)
├── assets/
│   ├── project/             # Project file templates (AGENTS/README/five-piece set, etc.)
│   ├── deploy/              # Four stack templates (Next.js/Python/Go/static) + shared parts
│   └── checklists/          # Go-live checklist, audit report, adoption plan templates
└── scripts/audit.py         # Read-only auditor for existing projects (stdlib only)
```

## License

MIT — see [LICENSE](LICENSE).
