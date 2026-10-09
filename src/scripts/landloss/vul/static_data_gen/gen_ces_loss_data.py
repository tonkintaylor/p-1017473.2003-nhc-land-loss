from pathlib import Path

import geopandas as gpd
import pandas as pd

BASE_PATH = Path(
    r"T:\Auckland\Projects\1017473\1017473.2003\SourceMaterial\CHC-loss-data-from-NHC"
)
CES_DAMAGE_W_LOC_FP = BASE_PATH / r"For NLM - Uncapped CES Damage By QPID v2(Data).csv"
qpid_location_df = pd.read_csv(CES_DAMAGE_W_LOC_FP)

# Convert the NHC comparison dataset to a GeoDataFrame
qpid_location_gdf = gpd.GeoDataFrame(
    qpid_location_df,
    geometry=gpd.points_from_xy(
        qpid_location_df["Longitude"], qpid_location_df["Latitude"]
    ),
    crs="EPSG:4326",
).to_crs("EPSG:2193")
qpid_location_gdf.to_file(BASE_PATH / "ces_loss_data_with_geometry.gpkg", driver="GPKG")
# Split by Event Name and export each group
for event_name, group_gdf in qpid_location_gdf.groupby("Event Name"):
    output_filename = BASE_PATH / f"loss_data_{event_name.replace(' ', '_')}.gpkg"
    group_gdf.to_file(output_filename, driver="GPKG")
