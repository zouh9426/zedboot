# ZeroWeave Guided-Install Prompt

[中文](SETUP.md)

Paste everything inside the separator below to your AI (Kimi Code / Claude Code / Codex, etc.). It will run the full installation and self-check.

---

Please install the ZeroWeave skill (a project-bootstrap orchestrator) for me. Steps:

1. Check which skills directories exist on my machine: `~/.kimi-code/skills/`, `~/.agents/skills/`, or the current project's `.kimi-code/skills/` / `.agents/skills/`. If none exists, create `~/.agents/skills/` (shared across tools).
2. Install ZeroWeave into it: `git clone https://github.com/zouh9426/zeroweave <chosen-dir>/zeroweave`. If I gave you a zip or local directory instead, copy it there and make sure `zeroweave/SKILL.md` exists.
3. Optional dependency check: look for `uiweft/SKILL.md` in the same candidate locations. If found, tell me the path; if not, tell me "the UI track is unavailable; uiweft (https://github.com/zouh9426/uiweft) can be installed later — the management and deployment systems are unaffected".
4. Self-check:
   - Read `zeroweave/SKILL.md` and confirm the frontmatter parses (name/description present);
   - Run `python3 zeroweave/scripts/audit.py --help` (or a trial run against a directory) to confirm the audit tool works;
   - Report: install location, uiweft detection result, self-check conclusion.
5. Tell me how to trigger it: start a new AI session and say "Initialize this project from scratch with ZeroWeave" or "Retrofit this project with ZeroWeave".

Stop and report on any failure — do not improvise.

---
