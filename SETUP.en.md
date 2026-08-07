# ZeroWeave Guided-Install Prompt

> **Usage**: copy the **entire content** of this file (starting below the separator) and paste it to your AI agent (Kimi Code / Claude Code / Codex, etc.). It will run the full installation and self-check.
> 中文版：[SETUP.md](SETUP.md)

---

You are an installation assistant. Please install **ZeroWeave** (a project-bootstrap orchestrator skill) for me. Follow the steps below and tell me the result of each; on any failure, stop and report — do not skip ahead.

## Step 1: Identify the environment

1. Identify which tool you are (Kimi Code / Claude Code / Codex / other) and determine your skills directory. Common candidates:
   - `~/.agents/skills/` (shared convention)
   - `~/.kimi-code/skills/` (Kimi Code)
   - `~/.claude/skills/` (Claude Code)
   - `~/.codex/skills/` (Codex)
   If your tool has its own convention, that wins.
2. Check dependencies: `python3 --version` (needed by the adopt workflow's audit script, stdlib only). If missing, tell me how to install it and stop.

## Step 2: Check existing installations

Search the skills directory recursively for `SKILL.md` files and read the `name:` field in their frontmatter to check whether these skills are installed (**match by name, not directory name** — a directory name may differ from the skill name):

| skill name | role | required? |
|---|---|---|
| `zeroweave` | the orchestrator itself | required |
| `uiweft` | UI track (generates DESIGN.md) | optional |

Give me an "installed / missing" list.

## Step 3: Install what is missing

- **zeroweave (required)**: `git clone https://github.com/zouh9426/zeroweave` into a temporary directory, copy its `zeroweave/` **subdirectory** into the skills directory (the repo root is not the skill — the subdirectory is), then delete the temp directory.
- **uiweft (optional)**: if I need the UI system and you didn't find it in step 2, tell me, and optionally install it following the SETUP guide at https://github.com/zouh9426/uiweft; skipping it does not affect the management or deployment systems.
- Afterwards, verify again by `name:`.

## Step 4: Self-check

Run these in order (use the actual paths resolved in steps 2/3):

1. Read `<zeroweave>/SKILL.md` and confirm the frontmatter parses (`name:` and `description:` present).
2. `python3 <zeroweave>/scripts/audit.py --help` — should print usage; then run it once against a real directory — should print a structured audit report, not an error.

When both pass, report to me: the zeroweave install path, the uiweft detection result, and one confirmation line — "ZeroWeave is installed; say 'Initialize this project from scratch with ZeroWeave' or 'Retrofit this old project with ZeroWeave' in your project to begin."

---
