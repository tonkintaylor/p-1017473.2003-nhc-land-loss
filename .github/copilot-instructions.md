# Copilot Instructions

## T Drive Access Restrictions

The `T:` drive is a shared network drive. Access to it must be treated as
**read-only everywhere**, with one exception:

- **Read-only (no writes, edits, deletes, moves, or renames):** anywhere on
  `T:` outside the path below.
- **Read-write allowed:** only within
  `T:\Auckland\Projects\1017473\1017473.2003` (and its subdirectories).

Before performing any operation on `T:` that creates, modifies, deletes, or
moves a file or directory, verify the target path is within
`T:\Auckland\Projects\1017473\1017473.2003`. If it is not, do not perform the
operation — report back to the user instead of proceeding.
