"""Run settings for the QGIS projects in this folder.

`gen_liq_pipeline_qgis_project.py` beside this reads these and holds no defaults
of its own.
"""

from pathlib import Path

# Where the projects and the files they read are written, each in its
# module's folder: <module>/<submodule>, e.g. hazard/liquefaction. A shared
# network folder, so the team can open them from their own machines.
QGIS_DIR = Path(r"U:\MAMI\land-loss")

# The extent to show: "wlg-pilot" for the small Wellington pilot box, "full"
# for the four territorial authorities, or any other name in
# landloss.io.area_of_interest.EXTENTS. Every layer is read for this extent, so
# the hazard and vul liquefaction steps have to have been run over it first.
EXTENT = "wlg-pilot"

# Which modelled earthquake to show the drawn states and ground lost for.
REALISATION_ID = 0
