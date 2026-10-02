"""Open a .qgs in QGIS headlessly and report what actually loaded.

Run with QGIS's own Python, not the repo venv:

    QGIS="C:/Program Files/QGIS 3.42.2/bin/python-qgis.bat"
    "$QGIS" verify_qgis_project.py project.qgs
    "$QGIS" verify_qgis_project.py project.qgs --render out_dir
        --extent 1746000 5423000 1754000 5429000

A .qgs that parses as XML can still open with broken layers, an unset project CRS or a
renderer QGIS quietly discarded, and none of that is visible without loading it. The
optional --render writes a PNG per layer, which is the only way to catch a project that
loads cleanly but draws nothing.
"""

import argparse
import sys
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsPalettedRasterRenderer,
    QgsProject,
    QgsRectangle,
    QgsSingleBandPseudoColorRenderer,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor


def describe(layer) -> str:
    """Summarise what QGIS actually made of one layer.

    Args:
        layer: The loaded QgsMapLayer.

    Returns:
        A one-line summary: validity, CRS, and the renderer with its ramp or
        class entries where there are any.
    """
    bits = [f"valid={layer.isValid()}", f"crs={layer.crs().authid()}"]
    renderer = layer.renderer()
    if renderer is None:
        return " | ".join([*bits, "renderer=None"])

    if isinstance(renderer, QgsPalettedRasterRenderer):
        classes = [(c.value, c.color.name(), c.label) for c in renderer.classes()]
        bits += [f"renderer={renderer.type()}", f"classes={classes}"]
    elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
        items = renderer.shader().rasterShaderFunction().colorRampItemList()
        bits += [
            f"renderer={renderer.type()}",
            f"ramp_items={len(items)}",
            f"first={items[0].value}:{items[0].color.name()}"
            if items
            else "ramp EMPTY",
            f"last={items[-1].value}:{items[-1].color.name()}" if items else "",
        ]
    else:
        bits.append(f"renderer={renderer.type()}")
    return " | ".join(b for b in bits if b)


def render(
    project, layer, extent, out_dir: Path, idx: int, *, size=(1600, 1100)
) -> Path:
    """Draw one layer to a PNG, which is the only way to catch a blank map.

    Args:
        project: The loaded QgsProject, read for its CRS.
        layer: The layer to draw.
        extent: ``(xmin, ymin, xmax, ymax)`` in the project CRS.
        out_dir: Where to write the PNG.
        idx: The layer's position, used in the file name.
        size: Canvas size in pixels. The default is the size of a real QGIS
            window, because a small render is its own kind of lie: at 500 px a
            metre-scale feature is half a pixel and reads as a blank layer when
            on screen it would be a visible speck.

    Returns:
        The path written.
    """
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setExtent(QgsRectangle(*extent))
    settings.setOutputSize(QSize(*size))
    settings.setDestinationCrs(project.crs())
    settings.setBackgroundColor(QColor(255, 255, 255))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    out = out_dir / f"render_{idx}.png"
    job.renderedImage().save(str(out))
    return out


def main() -> int:
    """Load the project named on the command line and report what came back.

    Returns:
        0 if every layer loaded and the project has a valid CRS, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--render", type=Path, default=None, help="Directory for PNGs.")
    parser.add_argument(
        "--size",
        type=int,
        nargs=2,
        metavar=("WIDTH", "HEIGHT"),
        default=(1600, 1100),
        help="Render size in pixels. Defaults to a real window; render smaller "
        "and small features vanish for reasons that are about the render, not "
        "the project.",
    )
    parser.add_argument(
        "--extent",
        type=float,
        nargs=4,
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        default=None,
        help="Render extent in the project CRS. Defaults to the full project "
        "extent, which for a regional raster is too coarse to judge - pass a "
        "town-sized box.",
    )
    args = parser.parse_args()

    app = QgsApplication([], False)
    app.initQgis()

    project = QgsProject.instance()
    if not project.read(str(args.project)):
        print(f"FAILED to read {args.project}", file=sys.stderr)
        return 1

    crs_ok = project.crs().isValid()
    print(f"project: {project.title()!r} | crs={project.crs().authid()} valid={crs_ok}")
    if not crs_ok:
        print(
            "  ^ no project CRS: check <properties><SpatialRefSys><ProjectionsEnabled>",
            file=sys.stderr,
        )

    if args.render:
        args.render.mkdir(parents=True, exist_ok=True)

    failures = 0
    for idx, node in enumerate(project.layerTreeRoot().children()):
        layer = node.layer()
        if layer is None:
            print(f"  [{idx}] <layer failed to load>")
            failures += 1
            continue
        checked = "on" if node.isVisible() else "off"
        print(f"  [{idx}] {layer.name()!r} ({checked}) | {describe(layer)}")
        if not layer.isValid():
            failures += 1
        if args.render:
            extent = args.extent or [
                layer.extent().xMinimum(),
                layer.extent().yMinimum(),
                layer.extent().xMaximum(),
                layer.extent().yMaximum(),
            ]
            out = render(
                project, layer, extent, args.render, idx, size=tuple(args.size)
            )
            print(f"        -> {out}")

    app.exitQgis()
    if failures or not crs_ok:
        print(f"{failures} invalid layer(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
