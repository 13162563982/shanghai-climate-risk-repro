# === district_price_data.py ===
# Housing-price panel loader for Shanghai districts.
# Used by visualization/basic_facts.py for the historical housing-price figure.

from __future__ import annotations

import re

import numpy as np
import pandas as pd


def _month_columns(frame: pd.DataFrame) -> list[str]:
    return [str(c) for c in frame.columns if re.fullmatch(r"\d{4}-\d{2}", str(c))]


def _normalize_district_name(series: pd.Series, config_module) -> pd.Series:
    return series.astype(str).str.strip().replace(config_module.ADMIN_DISTRICT_RENAME)


def _price_month_index(config_module) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{config_module.CFI_PRICE_YEAR_START}-01-01")
    end = pd.Timestamp(f"{config_module.CFI_PRICE_YEAR_END}-12-01")
    return pd.date_range(start, end, freq="MS")


def load_city_price_long(config_module) -> pd.DataFrame:
    city_wide = pd.read_excel(config_module.CITY_PRICE_EXCEL)
    month_cols = _month_columns(city_wide)
    if not month_cols:
        return pd.DataFrame(columns=["year_month", "date", "city_price"])

    meta_cols = [c for c in ["省名", "省代码", "市名", "市代码"] if c in city_wide.columns]
    city_long = city_wide.melt(
        id_vars=meta_cols, value_vars=month_cols,
        var_name="year_month", value_name="city_price",
    )
    city_long["city_price"] = pd.to_numeric(city_long["city_price"], errors="coerce")
    city_long = city_long.dropna(subset=["city_price"]).copy()
    city_long["year_month"] = city_long["year_month"].astype(str)
    city_long["date"] = pd.to_datetime(city_long["year_month"], format="%Y-%m", errors="coerce")
    city_long = city_long.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return city_long[["year_month", "date", "city_price"]]


def load_district_price_long(config_module, fill_missing: bool = True) -> pd.DataFrame:
    district_wide = pd.read_excel(config_module.DISTRICT_PRICE_EXCEL)
    month_cols = _month_columns(district_wide)
    meta_cols = [c for c in ["省名", "省代码", "市名", "市代码", "县名", "县代码"]
                 if c in district_wide.columns]

    district_long = district_wide.melt(
        id_vars=meta_cols, value_vars=month_cols,
        var_name="year_month", value_name="raw_price",
    )
    district_long["raw_price"] = pd.to_numeric(district_long["raw_price"], errors="coerce")
    district_long["district_std"] = (
        _normalize_district_name(district_long["县名"], config_module)
        if "县名" in district_long.columns else pd.NA
    )
    district_long["district"] = district_long["district_std"]
    district_long["year_month"] = district_long["year_month"].astype(str)
    district_long["date"] = pd.to_datetime(district_long["year_month"], format="%Y-%m", errors="coerce")
    district_long = (district_long
                     .dropna(subset=["date", "district_std"])
                     .sort_values(["district_std", "date"])
                     .reset_index(drop=True))

    raw_panel = (
        district_long.groupby(["district_std", "date"], as_index=False)["raw_price"]
        .mean().sort_values(["district_std", "date"])
    )

    month_index = _price_month_index(config_module)
    grid = pd.MultiIndex.from_product(
        [list(config_module.SHANGHAI_DISTRICTS), month_index],
        names=["district_std", "date"],
    ).to_frame(index=False)

    district_long = grid.merge(raw_panel, on=["district_std", "date"], how="left")
    district_long["district"] = district_long["district_std"]
    district_long["year_month"] = district_long["date"].dt.strftime("%Y-%m")

    city_long = load_city_price_long(config_module)
    city_long = city_long[["date", "city_price"]].drop_duplicates(subset=["date"]).copy()
    district_long = district_long.merge(city_long, on="date", how="left")

    district_long["district_price"] = district_long["raw_price"]
    district_long["price_imputed"] = False

    if fill_missing:
        def _fill_group(group: pd.DataFrame) -> pd.DataFrame:
            ratio = group["raw_price"] / group["city_price"]
            ratio = ratio.interpolate(method="linear", limit_area="inside")
            ratio = ratio.ffill().bfill()
            imputed_price = ratio * group["city_price"]
            group["district_price"] = np.where(
                group["raw_price"].notna(), group["raw_price"], imputed_price,
            )
            group["price_imputed"] = group["raw_price"].isna() & group["district_price"].notna()
            return group

        filled_groups = []
        for _, group in district_long.groupby("district_std", sort=False):
            filled_groups.append(_fill_group(group.copy()))
        district_long = pd.concat(filled_groups, ignore_index=True)

    return district_long[[
        "district", "district_std", "year_month", "date",
        "raw_price", "district_price", "price_imputed",
    ]]
