"""Project-wide tdrive_sync settings.

Records where this project's own versioned data, and NHC's/others' source
material, live on the T: drive.

``tdrive_sync`` is a generic package (see ``src/tdrive_sync``) that knows
nothing about this project. It finds this file by walking up from the current
working directory, so it must sit at the project root, alongside
``pyproject.toml``.

This file is committed to git deliberately: ``BASE_DIR``, ``DATA_VERSION`` and
``SOURCE_MATERIAL_DIR`` are shared, team-wide decisions, not private
per-developer settings (those live in ``.env`` instead — see
``TTDRIVE_SYNC_LOCAL_MODE`` and ``TTDRIVE_SYNC_LOCAL_VERSION`` in
``.env.example``).
"""

from pathlib import Path

BASE_DIR = Path(
    r"T:\Auckland\Projects\1017473\1017473.2003\WorkingMaterial\versioned_data"
)

# Bump this whenever the shared data needs to move on from what is already
# saved at the current version -- tdrive_sync refuses to overwrite an existing
# file at a normal version. Set to "SCRATCH" (tdrive_sync.SCRATCH_VERSION) to
# let saves overwrite freely instead.
DATA_VERSION = "v1"

# Data supplied by someone else -- NHC, another team -- read via
# tdrive_sync.get_source_mat. Unversioned: this is read-only, and never
# written to by tdrive_sync.
SOURCE_MATERIAL_DIR = Path(r"T:\Auckland\Projects\1017473\1017473.2003\SourceMaterial")
