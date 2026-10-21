# Shanghai real-estate climate risk

Code, input data and results for a study of how tropical-cyclone wind and storm
surge translate into risk for Shanghai's residential buildings and its housing
market, with and without the city's sea defences.

The model couples a cyclone wind hazard (IBTrACS + CLIMADA), a storm-surge
hazard (ETOPO bathymetry, FABDEM terrain, the municipal shoreline), a
building-level exposure layer, vulnerability functions carrying a
temperature-elasticity factor, a defence-gap sensitivity analysis, and a
finance layer (climate CVaR, finance risk index, composite risk index).

## What is here

- `Climate/`, `Finance/`, `Composite/` — model code
- `data/` — the inputs the model reads, published verbatim
- `*/output/` — the results the paper reports
- `provenance/` — one card per dataset: producer, identifier, licence, usage
- `DATA_SOURCES.md`, `REPRODUCE.md` — data provenance and how the pipeline runs

Files larger than GitHub's 100 MiB limit are attached to the
[`v1.0.0` release](https://github.com/13162563982/shanghai-climate-risk-repro/releases/tag/v1.0.0).

## Licence

MIT for the code (see `LICENSE`). Third-party data keep their producers' terms;
each dataset's licence is recorded in `provenance/`.
