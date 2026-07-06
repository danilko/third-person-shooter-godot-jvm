# PLATEAU data attribution

Real-world building/road/bridge geometry under `plateau/data/*.json` is derived from
[Project PLATEAU](https://www.mlit.go.jp/plateau/) (3D city model data), published by Japan's
Ministry of Land, Infrastructure, Transport and Tourism (MLIT), and distributed via the
[G-Spatial Information Center](https://www.geospatial.jp/ckan/dataset/plateau).

Licensed **CC BY 4.0** — free for commercial and non-commercial use, attribution required.

**Required credit line (include in any public build/release):** "Data: Project PLATEAU (MLIT)".

Raw source CityGML/OBJ downloads (multi-hundred-MB zips per municipality/tile) are **not** committed
to this repo — only the extracted/filtered/reprojected `data/*.json` (a few hundred KB to low MB per
precinct) is. Re-run `extract_plateau.py` against the source tiles to regenerate.
