Ruff no longer checks function complexity (C901, PLR0912, PLR0915). Parsers and data pipelines are naturally branchy, and splitting them only to satisfy a count made them harder to follow.
