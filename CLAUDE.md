# CLAUDE.md

Guidance for AI assistants working in this repo. Read this first in every session.

## Project context

The project's requirements and history are in Obsidian-friendly markdown under `docs/`:

- `docs/requirements.md`: goals, requirements, decisions, and open questions. Still being defined. Treat unfilled sections as undecided.
- `docs/changelog.md`: log of changes, newest first.

## Rules

1. **Start of session:** run `git pull` and read `docs/requirements.md` and `docs/changelog.md` before making changes.
2. **Don't invent requirements.** If a task depends on something not in `docs/requirements.md`, ask the user or add it to "Open questions". Don't guess.
3. **After each change:** add an entry to the top of `docs/changelog.md` (date, what changed, requirement IDs, commit hash). Keep edits to existing entries to a minimum so teammates' merges don't conflict.
4. **Git:** commit locally when asked. Do not run `git push` without the user's explicit approval.
5. **Don't put secrets in the repo.**
