import os
import rasterio

_REPO_ROOT = os.path.dirname(__file__)
_TERRAIN_ROOT = os.path.join(_REPO_ROOT, "terrain")

path = os.path.join(_TERRAIN_ROOT, "mountain", "n30_e078_1arc_v3.tif")
print(path)
print("Exists:", os.path.exists(path))
if os.path.exists(path):
    with rasterio.open(path) as ds:
        print("Shape:", ds.shape)
