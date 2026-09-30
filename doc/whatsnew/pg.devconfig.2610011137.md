**Research scripts are kept apart from the rest of the code.** AGENTS.md gains
a "Research scripts" section: utilities a research script needs stay in the
script or its `research/` folder, and research scripts may rely on
`src/landloss/` and `steps/` outputs but are not maintained when those change.
Ruff now bans importing any research package (TID251), and research folders are
excluded from the pre-commit hooks and from ruff.
