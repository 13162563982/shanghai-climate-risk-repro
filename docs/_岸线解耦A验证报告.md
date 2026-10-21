==============================================================================
OPTION-A RESULT VERIFICATION  (is the surge channel back to the fine layer?)
==============================================================================

  ADMIN_BOUNDARY_SHP        = D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8\期刊投稿\Nature-JF投稿\Nature npj Natural Hazards\data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.shp
  COASTLINE_BOUNDARY_SHP    = D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8\期刊投稿\Nature-JF投稿\Nature npj Natural Hazards\data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp
  effective for shoreline   = COASTLINE (fine)

-- 1. shoreline length re-derived from each layer (same DEM, same code) --
  fine layer     (2021年我国乡镇（街道）边界数据.shp) :    347.9 km
  official layer (上海_区级_GS2024-0650.shp) :     96.2 km
  ratio official/fine :   27.7%
  [PASS] shoreline actually used by the pipeline is the fine one (~347.9 km)   347.9 km
  [PASS] official layer alone would only give ~96 km (the artefact)   96.2 km

-- 2. surge-channel inputs across the three runs (byte identity) --
  building_coast_distance_m.npy    legacy=D1681967CA4D  preA=24A1C23739C8  A=D1681967CA4D
  twl_vec_hist.npy                 legacy=7D5C305ACF66  preA=7D5C305ACF66  A=7D5C305ACF66
  twl_vec_synth.npy                legacy=EE8053DF8088  preA=EE8053DF8088  A=EE8053DF8088
  [PASS] building_coast_distance_m.npy: A == legacy (surge channel is a no-op)
  [PASS] building_coast_distance_m.npy: A != preA (the fix actually changed it)
  [PASS] twl_vec_hist.npy: identical in all three runs
  [PASS] twl_vec_synth.npy: identical in all three runs

-- 3. city EAL: legacy vs preA vs A (bn CNY) --
  scenario    profile             legacy      preA         A  preA vs leg   A vs leg
  historical  baseline_nodef     24.1528   23.3333   24.2035       -3.39%      0.21%
  historical  current_def_gap    18.9697   19.0056   19.0056        0.19%      0.19%
  SSP2-4.5    baseline_nodef     33.3259   31.9454   33.3920       -4.14%      0.20%
  SSP2-4.5    current_def_gap    23.8476   23.8926   23.8926        0.19%      0.19%
  SSP5-8.5    baseline_nodef     40.2249   38.2886   40.2978       -4.81%      0.18%
  SSP5-8.5    current_def_gap    26.4691   26.5185   26.5185        0.19%      0.19%

-- 4. city SURGE EAL, historical / baseline_nodef --
  legacy=6.2471   preA=5.3930 (-13.67%)   A=6.2631 (+0.26%)
  [PASS] city surge EAL is back to the legacy value (within 0.5%)   6.2631 vs 6.2471 bn
  [PASS] the preA surge artefact is gone   -13.67% was the artefact

-- 5. residual city compound-EAL offset (attribution only) --
  max |A - legacy| over the 6 scenario x profile cells = 0.2099%
  [PASS] residual offset is attribution-scale (< 0.5%)   0.2099%

==============================================================================
OPTION-A RESULT VERIFICATION = PASS   (9/9 checks)
==============================================================================
