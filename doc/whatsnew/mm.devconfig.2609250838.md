Changelog fragments are now named `{initials}.{type}.{yymmddhhmm}.md` rather than
`{issue_num}.{type}.md`, so two branches in progress at once no longer take the same
number and conflict on merge. Every existing fragment has been renamed to its author's
initials and the time its commit added it, and each changelog entry now shows who made
it. Two new pre-commit hooks reject a numbered name and a draft `towncrier build` that
fails. The scheme, and how to add a contributor or change it again, is in the
"Changelog fragments" section of `AGENTS.md`.
