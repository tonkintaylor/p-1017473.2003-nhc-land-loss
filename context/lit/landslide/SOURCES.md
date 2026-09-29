# Landslide literature

Papers the landslide hazard work genuinely relies on, tracked in the
repository. Working copies that are not yet relied on stay in
`temp/reference/landslide/`; see "Reference documents" in `AGENTS.md`.

| Folder | File | What it is | Where from |
| --- | --- | --- | --- |
| `allstadt_2018/` | `allstadt-2018-kaikoura-near-real-time-landslide-models.pdf` | Allstadt, Jibson et al. (2018), *BSSA* 108(3B), 1649–1664. Three global coseismic landslide models, Nowicki Jessee among them, run against the GNS Kaikōura inventory: all overpredicted the ~20 km² observed area. Read for `potential-landslide-rebuild.md` | <https://doi.org/10.1785/0120170297>, downloaded by hand 29 September 2026 |
| `nowicki_jessee_2018/` | `nowicki-jessee-2018-global-seismic-landslide-model.pdf` | Nowicki Jessee et al. (2018), *JGR Earth Surface* 123, 1835–1859. Global logistic regression for coseismic landslides: coefficients in Table 3, probability-to-areal-coverage conversion in equation 9. Read for `src/scripts/landloss/hazard/landslide/potential-landslide-rebuild.md`. | <https://doi.org/10.1029/2017JF004494>, downloaded by hand 29 September 2026 |
| `nowicki_jessee_2018/` | `nowicki-jessee-2018-supporting-information.pdf` | Supporting information to Nowicki Jessee et al. (2018): Figure S1 (buffer sizes), S2 (predictor histograms), S3 (model against inventory for each training event), S4 (the same for blind-test events, S4I–L being the four New Zealand events), Table S1 (single-variable regressions), Table S2 (top 10 models) | Wiley supporting information file `jgrf20878-sup-0001`, downloaded by hand 29 September 2026 |
| `nowicki_jessee_2018/` | `nowicki-jessee-2018-table-s3-model-selection.xls` | Table S3 to Nowicki Jessee et al. (2018): every model combination tested, ranked by AIC, with AUC, accuracy, PPV, NPV and pseudo-R² values. Wiley labels the file `ts01` | Wiley supporting information file `jgrf20878-sup-0002`, downloaded by hand 29 September 2026 |
