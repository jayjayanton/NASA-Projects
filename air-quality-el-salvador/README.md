# Air Quality & Public Health — El Salvador

During NASA DEVELOP, I helped prepare Earth-observation data for air-quality research in Central America. El Salvador was particularly useful because in-situ measurements were available for comparison with satellite-derived observations.

My contribution included helping develop automated extraction and preprocessing workflows to prepare satellite products for ArcGIS Pro, along with regression analysis in R comparing MODIS and VIIRS aerosol optical depth with available ground observations in the context of PM2.5.

The shared [EO Data Extraction and Processing](../eo-data-extraction-and-processing/) folder contains an example of raster extraction, but **the NDVI script is not the air-quality regression code**.

Original regression scripts, datasets, maps, and numerical results are not currently included.

## Results documented in the team poster and final presentation

The analysis compared satellite aerosol optical depth (AOD) with in-situ PM2.5 observations. The poster reports these **overall simple linear regression** results:

| Country | R² | Observations |
| --- | ---: | ---: |
| El Salvador | 0.3043 | 111 |
| Guatemala | 0.09274 | 59 |
| Panama | 0.4376 | 35 |

These are country-level team results, not independent model scores attributable to one contributor. The project reported elevated AOD and PM2.5 around April and May and investigated relationships with fires and health indicators. The presentation identifies missing observations, cloud cover, and meteorological variables omitted from simple regression as limitations.

## Historical source materials

- [Team poster](https://docs.google.com/presentation/d/1nepUS0tPo1rKZeQ4-si2ZBX3wJqunH45/edit) — methods, regression table, findings.
- [Final team presentation](https://docs.google.com/presentation/d/1Ld3EMtaWho0oGPEFmDX1h_A9AngoHsRy/edit) — methods, results, and limitations.

These are linked as source materials; the original editable files have not been copied into this public repository.
