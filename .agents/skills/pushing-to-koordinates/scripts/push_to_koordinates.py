"""Create or update a layer on the T+T Koordinates site, for the NLM groups.

Run with the repo venv (it imports geopandas, requests and landloss):

    SKILL=.agents/skills/pushing-to-koordinates
    uv run --frozen python $SKILL/scripts/push_to_koordinates.py spec.json

See ../SKILL.md for the spec format and the rules. The default is a dry run that
prints the plan and writes nothing; a spec has to say ``"apply": true`` to push.

A layer key in ``../registry.json`` maps to a layer ID. No ID means the layer is
created and the new ID is recorded; an ID means a new version is added to it. The
create path was tested against group 5452 on 2026-09-30. The update path is ported
from the NLM repo's ``update_layer_datasource`` and has not been run from here.
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests

from landloss.domain import constants
from landloss.io.readers import resolve_api_key

# The path resolution, colours and breaks are the QGIS builder's, imported rather
# than copied so a layer is the same colour on the map, in QGIS and in Google Earth.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "making-qgis-projects" / "scripts")
)
import build_qgis_project as qgis

resolve_layer_path = qgis._resolve  # noqa: SLF001
resolve_categories = qgis._categories  # noqa: SLF001

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "registry.json"
API_BASE = f"https://{constants.TTGROUP_DOMAIN}/services/api/v1"

# The groups this skill is for. Dev is the default; production needs a spec that says
# so, because a published layer there is seen by the whole NLM audience.
DEV_GROUP = 5452
PRODUCTION_GROUP = 5380
NLM_GROUPS = {DEV_GROUP: "National Liquefaction Model Dev", PRODUCTION_GROUP: "NLM"}

IMPORT_TIMEOUT_S = 1800
POLL_S = 3
GEOMETRY_KINDS = {"polygon": "polygon", "linestring": "line", "point": "point"}


class Koordinates:
    """A thin session on the Koordinates API.

    It does not retry. The NLM connection class retries every request, which is fine
    for a read and wrong for ``POST /layers/``, where a repeat after a timeout would
    create a second layer.
    """

    def __init__(self) -> None:
        """Open the session with the key for the T+T domain."""
        self.session = requests.Session()
        key = resolve_api_key(constants.TTGROUP_DOMAIN)
        self.session.headers["Authorization"] = f"key {key}"

    def call(
        self, method: str, path: str, ok: tuple[int, ...] = (200, 201, 202, 204), **kw
    ) -> requests.Response:
        """Make one request, raising with the server's message on failure."""
        url = path if path.startswith("http") else API_BASE + path
        response = self.session.request(method, url, timeout=120, **kw)
        if response.status_code not in ok:
            msg = f"{method} {url} -> {response.status_code}: {response.text[:500]}"
            raise RuntimeError(msg)
        return response

    def find_layer(self, group: int, title: str) -> int | None:
        """Return the ID of a layer in a group with exactly this title, if any."""
        url: str | None = f"{API_BASE}/layers/"
        params: dict[str, Any] | None = {"group": group, "page_size": 100}
        while url:
            response = self.call("GET", url, params=params)
            for item in response.json():
                if item["title"] == title:
                    return item["id"]
            url, params = response.links.get("next", {}).get("url"), None
        return None


# -------------------------------------------------------------------------------------
# Registry
# -------------------------------------------------------------------------------------


def read_registry() -> dict[str, Any]:
    """Read the registry of layer keys to Koordinates layer IDs."""
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def record_layer(key: str, entry: dict[str, Any]) -> None:
    """Add or replace one key in the registry, leaving every other key as it was."""
    registry = read_registry()
    registry[key] = entry
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# -------------------------------------------------------------------------------------
# Style
# -------------------------------------------------------------------------------------


def _literal(value: Any, *, numeric: bool) -> str:
    """Format a category value for a CartoCSS filter."""
    if numeric:
        return str(value)
    return "'" + str(value).replace("'", "\\'") + "'"


def _paint(kind: str, colour: str, layer: dict[str, Any]) -> str:
    """CartoCSS declarations that paint one feature class in one colour."""
    width = layer.get("width", 1.5 if kind != "line" else 3)
    if kind == "point":
        return f"marker-fill: {colour}; marker-width: 6; marker-allow-overlap: true;"
    if kind == "line":
        return f"line-color: {colour}; line-width: {width};"
    outline = colour if layer.get("outline", "match") == "match" else layer["outline"]
    fill = "" if layer.get("fill") is False else f"polygon-fill: {colour};"
    return f"{fill} line-color: {outline}; line-width: {width / 3:.2f};"


def stylesheet(layer_id: int, layer: dict[str, Any], gdf: gpd.GeoDataFrame) -> str:
    """Build the CartoCSS for a layer from the spec's style keys.

    Args:
        layer_id: The Koordinates layer the rules are scoped to.
        layer: The layer spec: ``field`` with ``categories`` or ``cmap``, or ``color``.
        gdf: The data, read for the geometry type, the column type and the breaks.

    Returns:
        The stylesheet text.

    Raises:
        ValueError: If categories or a colour ramp are given with no ``field``.
    """
    kind = GEOMETRY_KINDS[gdf.geom_type.iloc[0].replace("Multi", "").lower()]
    field = layer.get("field")
    rules = []

    if (layer.get("categories") or layer.get("cmap")) and not field:
        msg = f"{layer['title']!r} gives categories or cmap but no 'field'."
        raise ValueError(msg)

    if layer.get("categories"):
        numeric = gdf[field].dtype.kind in "iuf"
        for value, (colour, _) in resolve_categories(layer).items():
            test = f"[{field} = {_literal(value, numeric=numeric)}]"
            rules.append(f"{test} {{ {_paint(kind, colour, layer)} }}")
    elif layer.get("cmap"):
        from matplotlib import colormaps
        from matplotlib.colors import to_hex

        edges = qgis.graduated_breaks(
            gdf[field].dropna().tolist(),
            int(layer.get("bins", 8)),
            layer.get("bin_mode", "quantile"),
        )
        cmap = colormaps[layer["cmap"]]
        count = len(edges) - 1
        # Ascending, so each later rule overrides the one before it.
        for i in range(count):
            colour = to_hex(cmap(i / max(count - 1, 1)))
            rules.append(f"[{field} >= {edges[i]}] {{ {_paint(kind, colour, layer)} }}")
    else:
        rules.append(_paint(kind, layer.get("color", "#5707b3"), layer))

    return f".layer-{layer_id} {{ " + " ".join(rules) + " }"


# -------------------------------------------------------------------------------------
# Push
# -------------------------------------------------------------------------------------


def to_upload_file(layer: dict[str, Any]) -> tuple[Path, gpd.GeoDataFrame]:
    """Read the layer from its local copy and write it out as a GeoPackage.

    Koordinates takes GeoPackage, which the NLM already uploads; this repo stores
    GeoParquet, which it does not. The CRS is left as it is.

    Args:
        layer: The layer spec, in the QGIS builder's form (``store`` and ``fname``,
            or ``path``).

    Returns:
        ``(the GeoPackage path, the data)``.

    Raises:
        FileNotFoundError: If the local copy is not on this machine. T: is never
            read from here.
    """
    source, _ = resolve_layer_path(dict(layer), "local")
    path = Path(source)
    if not path.exists():
        msg = f"{path} is not on this machine. Run the step that writes it first."
        raise FileNotFoundError(msg)
    read = (
        gpd.read_parquet
        if path.suffix.lower() in qgis.PARQUET_SUFFIXES
        else gpd.read_file
    )
    gdf = read(path)
    if gdf.empty:
        msg = f"{path.name} has no features; there is nothing to publish."
        raise ValueError(msg)
    out = Path(tempfile.mkdtemp(prefix="koordinates_")) / f"{layer['key']}.gpkg"
    gdf.to_file(out, layer=layer["key"].replace("-", "_"), driver="GPKG")
    return out, gdf


def upload_source(api: Koordinates, gpkg: Path, title: str, group: int) -> int:
    """Upload a file as a source and wait for its datasource to appear.

    Args:
        api: The session.
        gpkg: The file to upload.
        title: Shown on the source. Required by the API as well as ``name``.
        group: The group that owns the source.

    Returns:
        The datasource ID.

    Raises:
        RuntimeError: If no datasource appears after a few minutes.
    """
    meta = {"name": title, "title": title, "type": "upload", "group": group}
    with gpkg.open("rb") as handle:
        response = api.call(
            "POST",
            "/sources/",
            files={
                "file": (gpkg.name, handle, "application/geopackage+sqlite3"),
                "source": (None, json.dumps(meta), "application/json"),
            },
        )
    source_id = response.json()["id"]
    for _ in range(60):
        found = api.call("GET", f"/sources/{source_id}/datasources/").json()
        if found:
            return found[0]["id"]
        time.sleep(5)
    msg = f"Source {source_id} produced no datasource. Delete it in Koordinates."
    raise RuntimeError(msg)


def wait_for_import(api: Koordinates, version_url: str) -> None:
    """Block until a draft version has finished importing.

    Raises:
        RuntimeError: On an import error or after the timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < IMPORT_TIMEOUT_S:
        version = api.call("GET", version_url).json().get("version", {})
        if version.get("status") == "error":
            msg = f"Import failed for {version_url}: {version}"
            raise RuntimeError(msg)
        if version.get("status") == "ok":
            return
        time.sleep(POLL_S)
    msg = f"Import did not finish within {IMPORT_TIMEOUT_S // 60} minutes."
    raise RuntimeError(msg)


def publish_and_wait(api: Koordinates, version_url: str) -> None:
    """Publish a draft version and wait until it is live."""
    api.call("POST", version_url + "publish/")
    for _ in range(60):
        if api.call("GET", version_url).json().get("published_at"):
            return
        time.sleep(2)
    msg = f"{version_url} was not published within two minutes."
    raise RuntimeError(msg)


def create_layer(
    api: Koordinates, layer: dict[str, Any], datasource: int
) -> tuple[int, str]:
    """Create a layer and publish its first version.

    The call to create is made once and never retried: a repeat after a timeout
    would make a duplicate.

    Returns:
        ``(layer ID, published version URL)``.
    """
    body = {
        "title": layer["title"],
        "group": layer["group"],
        "data": {"datasources": [{"id": datasource}]},
        "tags": layer.get("tags", []),
        "description": layer.get("description", ""),
    }
    layer_id = api.call("POST", "/layers/", json=body).json()["id"]
    # The Location header points at the layer, not the draft, so ask for the draft.
    # Creating starts the import itself.
    version = api.call("GET", f"/layers/{layer_id}/versions/").json()[0]["id"]
    version_url = f"{API_BASE}/layers/{layer_id}/versions/{version}/"
    wait_for_import(api, version_url)
    publish_and_wait(api, version_url)
    return layer_id, version_url


def update_layer(api: Koordinates, layer_id: int, datasource: int) -> str:
    """Add a new published version of an existing layer from a new datasource.

    Ported from the NLM repo and not yet run from this one.

    Returns:
        The published version URL.
    """
    versions_url = f"{API_BASE}/layers/{layer_id}/versions/"
    for version in api.call("GET", versions_url).json():
        if not version.get("published_at"):
            # A leftover draft blocks a new one.
            api.call("DELETE", f"{versions_url}{version['id']}/")
    api.call("POST", versions_url)
    draft = api.call("GET", versions_url).json()[0]["id"]
    version_url = f"{versions_url}{draft}/"
    api.call("PUT", version_url, json={"data": {"datasources": [datasource]}})
    api.call("POST", version_url + "import/")
    wait_for_import(api, version_url)
    publish_and_wait(api, version_url)
    return version_url


def apply_style(
    api: Koordinates, layer_id: int, layer: dict[str, Any], gdf: gpd.GeoDataFrame
) -> int:
    """Publish a CartoCSS style and make it the layer's default.

    Setting the default needs a new draft version, so a styled layer has one more
    version than a plain one.

    Returns:
        The style ID.
    """
    styles_url = f"{API_BASE}/layers/{layer_id}/styles/"
    name = layer.get("style_name", "House style")
    css = stylesheet(layer_id, layer, gdf)
    style_id = api.call(
        "POST",
        styles_url,
        json={"name": name, "stylesheets": css, "style_type": "cartocss"},
    ).json()["id"]
    api.call("POST", f"{styles_url}{style_id}/publish/")
    for _ in range(90):
        state = api.call("GET", f"{styles_url}{style_id}/").json()["state"]
        if state == "ACTIVE":
            break
        if state != "GENERATING":
            msg = f"Style {style_id} ended in state {state}."
            raise RuntimeError(msg)
        time.sleep(1)
    else:
        msg = f"Style {style_id} did not finish generating."
        raise RuntimeError(msg)

    versions_url = f"{API_BASE}/layers/{layer_id}/versions/"
    api.call("POST", versions_url)
    draft = api.call("GET", versions_url).json()[0]["id"]
    version_url = f"{versions_url}{draft}/"
    api.call("PUT", version_url, json={"default_style": style_id})
    publish_and_wait(api, version_url)
    return style_id


def check_layer(layer: dict[str, Any]) -> None:
    """Refuse a layer spec that breaks the skill's rules.

    Raises:
        ValueError: If the spec lacks a key or title, names a group outside the NLM
            ones, or targets production without confirming.
    """
    for required in ("key", "title"):
        if not layer.get(required):
            msg = f"Every layer needs a {required!r}: {layer}"
            raise ValueError(msg)
    group = layer.setdefault("group", DEV_GROUP)
    if group not in NLM_GROUPS:
        msg = f"Group {group} is not an NLM group. Use one of {sorted(NLM_GROUPS)}."
        raise ValueError(msg)
    if group == PRODUCTION_GROUP and not layer.get("confirm_production"):
        msg = (
            f"{layer['key']} targets the production NLM group {PRODUCTION_GROUP}. "
            f'Set "confirm_production": true on the layer if that is intended.'
        )
        raise ValueError(msg)


def push(layer: dict[str, Any], *, apply: bool, api: Koordinates | None) -> None:
    """Plan, and if applying, carry out, the push of one layer.

    Args:
        layer: The layer spec.
        apply: Whether to write. False prints the plan only.
        api: The session, or None for a dry run without a key.
    """
    check_layer(layer)
    if layer.get("attribution"):
        layer["description"] = (
            f"{layer.get('description', '')}\n\n{layer['attribution']}".strip()
        )
    registry = read_registry()
    existing = registry.get(layer["key"], {}).get("layer_id")
    gpkg, gdf = to_upload_file(layer)
    action = f"update layer {existing}" if existing else "create a new layer"
    print(
        f"[{layer['key']}] {action} in group {layer['group']}: {layer['title']!r}, "
        f"{len(gdf):,} features, {gdf.crs.to_string()}"
    )
    print(f"    style: {stylesheet(existing or 0, layer, gdf)[:160]} ...")
    if not apply:
        return
    assert api is not None  # noqa: S101

    if not existing:
        clash = api.find_layer(layer["group"], layer["title"])
        if clash:
            msg = (
                f"Group {layer['group']} already has a layer titled {layer['title']!r} "
                f"(ID {clash}) that the registry does not know. Add it to the registry "
                f"if it is this one, or change the title."
            )
            raise RuntimeError(msg)

    datasource = upload_source(api, gpkg, layer["title"], layer["group"])
    if existing:
        update_layer(api, existing, datasource)
        layer_id = existing
    else:
        layer_id, _ = create_layer(api, layer, datasource)
        # Recorded the moment the ID exists, so a failure later cannot orphan it.
        record_layer(
            layer["key"],
            {"layer_id": layer_id, "group": layer["group"], "title": layer["title"]},
        )
    style_id = apply_style(api, layer_id, layer, gdf)
    print(f"[{layer['key']}] live as layer {layer_id} (style {style_id})")


def run(spec: dict[str, Any]) -> None:
    """Push every layer in a spec. A dry run unless the spec says ``apply``."""
    apply = bool(spec.get("apply"))
    api = Koordinates() if apply else None
    if not apply:
        print('DRY RUN: nothing is written. Set "apply": true to push.')
    for layer in spec["layers"]:
        push(dict(layer), apply=apply, api=api)


def main() -> None:
    """Push the layers in the spec file named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Path to the JSON spec.")
    args = parser.parse_args()
    run(json.loads(args.spec.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
