<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Agent Development Guidelines

This document codifies git and development practices for AI agents working on
this repository. These practices are derived from the project constitution and
established development conventions.

## Constitution

If `.specify/memory/constitution.md` exists in this repository, read it and
follow its principles. The constitution takes precedence over this file if
there is any conflict between the two documents.

## Git Commit Message Rules

This project follows the
[seven rules of a great Git commit message](https://chris.beams.io/posts/git-commit/).
Several rules are enforced automatically by **gitlint** (see `.gitlint`).

### Rule 1: Separate subject from body with a blank line

The blank line between the subject and body is critical. Git tools like `log`,
`shortlog`, and `rebase` rely on this separation. Simple changes may omit the
body entirely.

- **Enforcement**: Convention and tooling; gitlint validates structure.

### Rule 2: Limit the subject line to 50 characters

Keep subjects concise. The project convention is a 50-character
subject; the mechanically enforced ceiling is higher.

- **Enforcement**: gitlint `title-max-length`, which enforces its
  72-character default because `.gitlint`'s `[title-max-length]`
  stanza is commented out. The 50-character target is therefore a
  stricter project convention applied by hand; no hook will catch a
  subject of 51 to 72 characters.

### Rule 3: Capitalize the subject line

The subject line MUST start with a capital letter. This project uses
Conventional Commits, whose capitalized types naturally satisfy this rule.

- **Enforcement**: gitlint `contrib-title-conventional-commits` requires
  capitalized types.

### Rule 4: Do not end the subject line with a period

The subject line MUST NOT end with a period. Trailing space is precious
when you are limited to 50 characters.

- **Enforcement**: gitlint `title-trailing-punctuation` (T3, enabled by
  default).

### Rule 5: Use the imperative mood in the subject line

Write the subject as if completing the sentence: "If applied, this commit
will \_\_\_\_\_\_\_\_." The Conventional Commit type prefix naturally leads into
imperative mood.

Good examples:

- `Fix: correct race condition in calendar refresh`
- `Feat: add door code rotation support`
- `Refactor: extract event parsing to helper`

Bad examples:

- ~~`Fix: fixed the race condition`~~ (past tense)
- ~~`Feat: adds door code rotation`~~ (third person)
- ~~`Refactor: extracting event parsing`~~ (gerund)

- **Enforcement**: Manual discipline; not automatically enforceable.

### Rule 6: Wrap the body at 72 characters

Body text MUST be wrapped at 72 characters per line. Lines containing URLs
MAY exceed this limit, but enforcement tooling has limitations.

- **Enforcement**: gitlint `body-max-line-length` enforces its
  80-character default; `.gitlint` does not override it. The
  72-character wrap is therefore a stricter project convention applied
  by hand, and no hook will catch a body wrapped at 73 to 80
  characters. In addition, the configured `ignore-by-body` rule
  disables the check entirely for any commit body containing a line
  that matches the URL pattern.

### Rule 7: Use the body to explain what and why, not how

The code diff shows _how_ a change was made. The commit body should explain
_what_ problem is being solved and _why_ this approach was chosen. Include
context that will help future developers understand the rationale.

- **Enforcement**: Manual discipline; not automatically enforceable.

## Conventional Commit Format

This project uses **Conventional Commits** with **capitalized types**:

```plaintext
Type(scope): Short imperative description

Body explaining what and why. Wrap at 72 characters.
URLs on their own line are exempt from the wrap limit.

Co-authored-by: <AI Model Name> <appropriate-email@provider.com>
Signed-off-by: Name <email>
```

**Allowed types** (capitalized, enforced by gitlint):

- `Fix` — Bug fixes
- `Feat` — New features
- `Chore` — Maintenance tasks
- `Docs` — Documentation changes
- `Style` — Code style/formatting (no logic change)
- `Refactor` — Code refactoring (no behavior change)
- `Perf` — Performance improvements
- `Test` — Adding or updating tests
- `Revert` — Reverting previous commits
- `CI` — CI/CD configuration changes
- `Build` — Build system changes

### Commit Command

Always use the `-s` flag for Developer Certificate of Origin sign-off:

```bash
git commit -s -m "Type(scope): Short imperative description

Body explaining what changed and why.

Co-authored-by: <AI Model> <email@provider.com>"
```

### Co-Authorship

All AI-assisted commits MUST include a `Co-authored-by` trailer identifying
the AI model used:

| Model | Co-authored-by |
| ------- | ---------------- |
| Claude | `Co-authored-by: Claude <claude@anthropic.com>` |
| ChatGPT | `Co-authored-by: ChatGPT <chatgpt@openai.com>` |
| Gemini | `Co-authored-by: Gemini <gemini@google.com>` |
| Copilot | `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` |

This trailer goes at the end of the commit message body. Note that
`git commit -s` appends the `Signed-off-by` line after all other
content, so it will appear after the `Co-authored-by` trailer
automatically.

## Gitlint Enforcement Summary

The following gitlint rules are active (see `.gitlint` for full config):

| Rule | What it checks | Enforced limit |
| ---- | -------------- | -------------- |
| `title-max-length` (T1) | Subject length | 72 (gitlint default; stanza commented out). Project convention: 50 |
| `title-trailing-punctuation` (T3) | No trailing `.` `;` `:` etc. | Enabled |
| `body-max-line-length` (B1) | Body line length | 80 (gitlint default; not overridden). Project convention: 72 |
| `contrib-title-conventional-commits` | Capitalized type prefix | Required |
| `contrib-body-requires-signed-off-by` | DCO sign-off present | Required |
| `ignore-by-body` | Exempt URL lines from B1 | Enabled |

## Pre-Commit Hooks

This repository uses pre-commit hooks that run automatically on `git commit`.
The hooks enforce (non-exhaustive list):

- **gitlint** — Commit message format validation (see rules above)
- **reuse** — SPDX license header compliance
- **ruff** — Python linting and formatting
- **mypy** — Python type checking
- **interrogate** — Docstring coverage (100% required)
- **yamllint** — YAML linting
- **actionlint** — GitHub Actions workflow validation

Check `.pre-commit-config.yaml` for the complete list.

### If Pre-Commit Fails

**CRITICAL**: Do NOT use `git reset` after a failed commit attempt.

1. Fix the issues identified by the pre-commit hooks
2. Stage the fixes: `git add <files>`
3. Attempt the commit again as if you hadn't tried before
4. The pre-commit hooks will run again on the new attempt

Pre-commit hooks may auto-fix some issues (e.g., ruff format). If files were
modified by hooks, stage them and commit again.

### Never Bypass Hooks

Using `--no-verify` to bypass pre-commit hooks is **PROHIBITED**.

## Atomic Commits

Each commit MUST represent exactly one logical change:

- ✅ One feature per commit
- ✅ One bug fix per commit
- ✅ One refactor per commit
- ❌ Multiple unrelated changes in one commit

### Task List Updates Are Separate Commits

Changes to task tracking documents (e.g., `tasks.md`) MUST be committed
separately from the code or documentation they track. Bundling a task
list update into the same commit as the work it describes breaks commit
atomicity — even when both changes are classified as documentation.

- ✅ Commit 1: `Feat(core): Add HTTP client` (code + tests)
- ✅ Commit 2: `Docs(tasks): Mark T015 complete` (tasks.md only)
- ❌ Single commit with code changes **and** tasks.md update

## SPDX License Headers

All new source files MUST include SPDX headers:

```python
# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
```

Check `REUSE.toml` for file-type-specific header requirements.

## Requirement Citations

Spec-driven requirements live in `specs/NNN-name/spec.md` and are
numbered `FR-001`, `FR-002`, … **Numbering restarts in every spec**,
so `FR-030` in spec 001 is a completely different requirement from
`FR-030` in spec 004. A bare `FR-NNN` is therefore ambiguous.

**Going forward, write new citations as `spec XX FR-NNN`:**

```plaintext
# Good — unambiguous
# See spec 004 FR-030 (privacy chokepoint)

# Discouraged — ambiguous across four specs
# See FR-030
```

**Do NOT retrofit existing bare citations.** There are ~178 bare
`FR-NNN` references in `custom_components/`; rewriting them would be
pure churn with no functional benefit.

## Git Worktrees

When creating git worktrees for feature branches, bug fixes, or any
other work, **always** place them in the sibling `worktrees/` directory,
namespaced by repository:

```bash
git worktree add /home/tykeal/repos/personal/homeassistant/worktrees/homeassistant-hospitable/<worktree-leaf> -b <branch-name> main
```

The `worktrees/` directory is a sibling of the repository under the
repository root's parent directory, and each repository gets its own
subdirectory inside it:

```text
repos/personal/homeassistant/
├── homeassistant-hospitable/     ← this repository
└── worktrees/                    ← all worktrees go here
    └── homeassistant-hospitable/ ← namespaced by repository
        ├── docfix1/
        └── some-feature/
```

The worktree leaf name is a short label for the work; it does not have
to mirror the branch name, and a leaf that avoids `/` keeps the
directory layout flat.

**NEVER** create worktrees inside the repository directory itself.

Clean up worktrees when the associated branch has been merged:

```bash
git worktree remove /home/tykeal/repos/personal/homeassistant/worktrees/homeassistant-hospitable/<worktree-leaf>
git branch -D <branch-name>
```

## Testing Requirements

The Python project lives under `custom_components/`. Run commands
from the repository root using `uv`:

- Run tests before committing: `uv run pytest tests/`
- Run linting before committing: `uv run ruff check custom_components/ tests/`
- All tests must pass before pushing
- New features should include appropriate test coverage

## Development Workflow Summary

1. Make changes to code
2. Run tests locally to verify: `uv run pytest tests/ -x -q`
3. Run linting: `uv run ruff check custom_components/ tests/`
4. Stage changes: `git add <files>`
5. Commit with sign-off and co-authorship:

   ```bash
   git commit -s -m "Type(scope): Short imperative description

   Body explaining what and why.

   Co-authored-by: <AI Model> <email@provider.com>"
   ```

6. If pre-commit fails, fix issues and commit again (don't reset)
7. Push when ready

## Quick Reference

| Requirement | Command/Format |
| ------------ | ---------------- |
| Sign-off | `git commit -s` |
| Co-author | `Co-authored-by: <Model> <email>` |
| Subject format | `Type(scope): imperative description` |
| Type case | Capitalized (e.g., `Fix`, `Feat`) |
| Subject length | ≤50 chars (project convention; gitlint enforces 72) |
| Body line length | ≤72 chars, URLs exempt (project convention; gitlint enforces 80) |
| Subject punctuation | No trailing period |
| Subject mood | Imperative ("Add", not "Added") |
| Body content | Explain what and why, not how |
| After failed commit | Fix and retry (no reset) |
| Requirement citation | `spec XX FR-NNN` (not bare `FR-NNN`) |
