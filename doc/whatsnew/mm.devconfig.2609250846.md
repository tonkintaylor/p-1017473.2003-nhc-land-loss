CI now loads a Bitbucket SSH key before installing dependencies, so the private
`ttpy-gis` dependency resolves in the static checks, tests and Copilot setup
workflows. Needs a read-only Bitbucket access key for `ttpy-gis` stored as the
`BITBUCKET_SSH_KEY` repository secret.
