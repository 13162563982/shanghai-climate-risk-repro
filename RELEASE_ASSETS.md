# Release assets — the eight files GitHub will not accept as git objects

GitHub rejects any single file larger than **100 MiB**. Eight of the files this
model reads or writes are bigger than that, and none of them can be clipped,
downsampled or regenerated for publication — so they are attached, byte for
byte, to the GitHub **Release `v1.0.0`** of this repository.

Total: **18 files / 3.63 GiB**.

Download them from:

```
https://github.com/13162563982/shanghai-climate-risk-repro/releases/tag/v1.0.0
```

or run `fetch_release_assets.ps1`, which downloads each asset, checks its
SHA-256, and places it at the path below.

| asset | dataset | bytes | target path in the repository |
|---|---|---|---|
| `2021年我国乡镇（街道）边界数据.cpg` | D20 | 5 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.cpg` |
| `2021年我国乡镇（街道）边界数据.dbf` | D20 | 44,398,314 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.dbf` |
| `2021年我国乡镇（街道）边界数据.prj` | D20 | 145 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.prj` |
| `2021年我国乡镇（街道）边界数据.sbn` | D20 | 427,868 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbn` |
| `2021年我国乡镇（街道）边界数据.sbx` | D20 | 16,660 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbx` |
| `2021年我国乡镇（街道）边界数据.shp` | D20 | 331,955,444 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp` |
| `2021年我国乡镇（街道）边界数据.shp.xml` | D20 | 5,923 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp.xml` |
| `2021年我国乡镇（街道）边界数据.shx` | D20 | 349,348 | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shx` |
| `ETOPO_2022_v1_30s_N90W180_bed.tif` | D03 | 1,624,895,430 | `data\Hazard_data\ETOPO_2022_v1_30s_N90W180_bed.tif` |
| `haz_SS_ssp245.hdf5` | H | 219,502,759 | `Climate\output\intermediate\haz_SS_ssp245.hdf5` |
| `haz_SS_ssp585.hdf5` | H | 361,922,167 | `Climate\output\intermediate\haz_SS_ssp585.hdf5` |
| `haz_SS_synth.hdf5` | H | 107,168,215 | `Climate\output\intermediate\haz_SS_synth.hdf5` |
| `haz_TC_cvar_N100.hdf5` | I | 567,943,627 | `Finance\output\intermediate\haz_TC_cvar_N100.hdf5` |
| `processed_shanghai_20201231_all.cpg` | D17 | 5 | `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.cpg` |
| `processed_shanghai_20201231_all.dbf` | D17 | 208,784,829 | `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.dbf` |
| `processed_shanghai_20201231_all.prj` | D17 | 425 | `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.prj` |
| `processed_shanghai_20201231_all.shp` | D17 | 429,151,524 | `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.shp` |
| `processed_shanghai_20201231_all.shx` | D17 | 3,770,476 | `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.shx` |

## What each file is

### `2021年我国乡镇（街道）边界数据.cpg`

Code-page file of the township boundary layer.

- size: 5 bytes
- sha256: `3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.cpg`

### `2021年我国乡镇（街道）边界数据.dbf`

Attribute table of the township boundary layer.

- size: 44,398,314 bytes
- sha256: `f060d45728a619b52f2c831070e82a7eeffd1d31512fb15231c5110d7065e451`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.dbf`

### `2021年我国乡镇（街道）边界数据.prj`

CRS definition of the township boundary layer.

- size: 145 bytes
- sha256: `a02a27b1d1982c8516d83398e85a3c8b1aef1713c13ef4d84d7bde17430c07c4`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.prj`

### `2021年我国乡镇（街道）边界数据.sbn`

ESRI spatial index (companion file).

- size: 427,868 bytes
- sha256: `9dcf43c113157f67c299f18d7bbffa63909238add714ba852b80ae73a9a74f31`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbn`

### `2021年我国乡镇（街道）边界数据.sbx`

ESRI spatial index (companion file).

- size: 16,660 bytes
- sha256: `7f8947532f499244d1fddeea9d5884b085abf2c116ffb2be4e11550f8c7bb41e`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.sbx`

### `2021年我国乡镇（街道）边界数据.shp`

2021 national township boundary geography. Its Shanghai polyline **is the shoreline geometry** used by the surge model.

- size: 331,955,444 bytes
- sha256: `dce2c809b306fb14e1fe220567d6d7f57bf6a6eee6d5701b409c5f85a17c6434`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp`

### `2021年我国乡镇（街道）边界数据.shp.xml`

FGDC metadata of the township boundary layer.

- size: 5,923 bytes
- sha256: `1e90ab4cee4c262d26e2f6b261bae1c658fc9a39a6eb8109084d486a260ff391`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp.xml`

### `2021年我国乡镇（街道）边界数据.shx`

Shapefile index of the township boundary layer.

- size: 349,348 bytes
- sha256: `7b74f78d0f1376e409833d83f5eb87611c065e458126c63b7578a47de462dc6b`
- goes to: `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shx`

### `ETOPO_2022_v1_30s_N90W180_bed.tif`

ETOPO 2022 global bed topography (15 arc-s). Read by `02_hazard_surge.py`.

- size: 1,624,895,430 bytes
- sha256: `c85d2139821b396c06560a3356e993b2d9316baee7970f234586805fb7bc276e`
- goes to: `data\Hazard_data\ETOPO_2022_v1_30s_N90W180_bed.tif`

### `haz_SS_ssp245.hdf5`

Storm-surge hazard, SSP2-4.5 scenario. Produced by step C02.

- size: 219,502,759 bytes
- sha256: `53b305146d51a4a073fe3f47448a94fa0c14da3ce6db840c26f87230dbb953b6`
- goes to: `Climate\output\intermediate\haz_SS_ssp245.hdf5`

### `haz_SS_ssp585.hdf5`

Storm-surge hazard, SSP5-8.5 scenario (CLIMADA `Hazard` HDF5). Produced by step C02, read by C05/C06/C07.

- size: 361,922,167 bytes
- sha256: `46f2cf2a389a393df3e291fba6634c120ecb3e9d71d0b15c869af0bc62d44e64`
- goes to: `Climate\output\intermediate\haz_SS_ssp585.hdf5`

### `haz_SS_synth.hdf5`

Storm-surge hazard, synthetic-track set. Produced by step C02.

- size: 107,168,215 bytes
- sha256: `1d0d0a5b49ec151f1279a1c5edbfff4fc20af7c04795c9c26df2cc82bb818633`
- goes to: `Climate\output\intermediate\haz_SS_synth.hdf5`

### `haz_TC_cvar_N100.hdf5`

Tropical-cyclone hazard used by the climate-CVaR calculation (N=100). Produced by step F01.

- size: 567,943,627 bytes
- sha256: `b32173eacb613dce77bac4f639d98aab93031aa9131bcf6bbf2592d4f79eed98`
- goes to: `Finance\output\intermediate\haz_TC_cvar_N100.hdf5`

### `processed_shanghai_20201231_all.cpg`

Code-page file of the building vector.

- size: 5 bytes
- sha256: `3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824`
- goes to: `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.cpg`

### `processed_shanghai_20201231_all.dbf`

Attribute table of the building vector (same dataset as the `.shp`).

- size: 208,784,829 bytes
- sha256: `ad82e7dd1eedcb3e6f8cb185e525651c03a91a73f82034d02441b714525b406a`
- goes to: `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.dbf`

### `processed_shanghai_20201231_all.prj`

CRS definition of the building vector.

- size: 425 bytes
- sha256: `f2e7fb14d55bdd8d6a3bc2c272a48729d8f9d0ad72936e20eae6a9a81c2fccd0`
- goes to: `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.prj`

### `processed_shanghai_20201231_all.shp`

2024 Shanghai multi-attribute building vector, 2020-12-31 snapshot (CMAB-derived). Read by `03_exposure.py`.

- size: 429,151,524 bytes
- sha256: `e61afa252b9e716107594b905519adbd2afd9da3767f9f15d9a4b9e788574527`
- goes to: `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.shp`

### `processed_shanghai_20201231_all.shx`

Shapefile index of the building vector.

- size: 3,770,476 bytes
- sha256: `7294faf0fb8236dd073be74d92a50ce18ccfbf8542d15f9f4e840a2dc308ce6d`
- goes to: `data\Exposure_data\房屋\2024年上海多属性建筑矢量数据\processed_shanghai_20201231_all.shx`

## Why these are needed

* Three of them are **inputs the model reads** (ETOPO, the building vector, the
  township/shoreline layer) — without them steps C02 and C03 cannot run.
* Four are **cached CLIMADA hazards** produced by steps C02 and F01. They are not
  required to reproduce the paper — a full re-run takes about 26 minutes — but
  they are shipped so the archived tree matches the one the results came from.
* Shapefile companions (`.dbf`, `.shx`, `.prj`, `.cpg`, `.sbn`, `.sbx`, `.shp.xml`)
  travel with their `.shp`: a shapefile is only usable as a set.

`SHA256SUMS.csv` and `manifest.json` list every one of them as well.
