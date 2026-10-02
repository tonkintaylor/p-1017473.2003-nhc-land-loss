# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

`landloss` — NHC land loss project (job number 1017473.2003). Python 3.13, managed
with `uv`. Source lives in `src/landloss`, tests in `tests`.

See instructions under AGENTS.md

## Always run the pre-commit hooks after making changes

This repo uses [prek](https://github.com/j178/prek) (a drop-in pre-commit runner)
with the hooks defined in `.pre-commit-config.yaml`. The same command runs in CI
(`.github/workflows/static-checks.yml`), so anything that fails here fails the PR.

After finishing a set of file changes — and before reporting the work as done or
creating a commit — run:

```Powershell
uv run --frozen prek -a
```

To check only the files you touched instead of the whole repo:

```Powershell
uv run --frozen prek run --files <path> [<path> ...]
```

Notes:

- Several hooks (`ruff-check --fix`, `ruff-format`, `uv-lock`, `uv-export`,
  `trailing-whitespace`, `nbstripout`) rewrite files in place. A hook reporting
  "files were modified by this hook" is a failure: re-run the command until it
  passes cleanly, and review the edits the hooks made.
- Fix any remaining failures yourself rather than skipping hooks. Do not use
  `--no-verify`, `SKIP=`, or otherwise bypass the hooks.
- `FIX` (TODO/FIXME) rules are disabled in the hooks but enforced separately in CI
  via `uv run ruff check --select "FIX"`, so avoid leaving TODO comments behind.
- If `prek` is not installed, run `./tasks/dev_sync.ps1` to set up the environment.

## Tests

```Powershell
uv run --frozen pytest
```

## Changelog

Any user-facing change needs a changelog entry: add
`doc/whatsnew/{initials}.{entry_type}.{yymmddhhmm}.md`, where `{initials}` are the
committing developer's (`git config user.name`), `{yymmddhhmm}` is the current time, and
`{entry_type}` is one of `feature`, `bugfix`, `doc`, `removal`, `newhome`, `test`, or
`devconfig`. Never append to an existing fragment; write a new one. See "Changelog
fragments" in AGENTS.md.
