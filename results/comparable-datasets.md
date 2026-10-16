# Brain single-nucleus datasets comparable to SEA-AD

The strongest next app candidate is the Mathys ROSMAP PFC427 atlas: it documents a joint H5AD matrix and deidentified donor metadata. PsychAD offers broader disease coverage but requires more access and scale planning.

| Dataset | Verified scale and fit | Documented formats and access |
|---|---|---|
| **Mathys ROSMAP PFC427 atlas** ([official repository](https://compbio.mit.edu/ad_aging_brain/)) | 2.3 million cells from 427 ROSMAP participants; aged prefrontal cortex, AD pathology, cognition and resilience. | Repository lists `PFC427_raw_data.h5ad`, deidentified individual-metadata TSV and cell-type RDS files. Complete human data, detailed metadata and identity mappings require Synapse access and a Data Use Certificate. |
| **PsychAD** ([primary paper](https://www.nature.com/articles/s41597-025-04687-5)) | >6.3 million nuclei from 1,494 donors; prefrontal cortex across neurodegenerative and psychiatric disorders. Includes AD, PD, schizophrenia and controls. | Data and access requirements are documented through the AD Knowledge Portal, dataset `syn60084804`. Exact file formats and permissions require release-level inspection. A previously proposed CELLxGENE collection could not be verified as PsychAD and is excluded. |
| **Siletti adult human brain reference** ([HCA portal](https://data.humancellatlas.org/hca-bio-networks/nervous-system/atlases/brain-v1-0)) | >3 million nuclei from 3 donors and approximately 100 dissections; normal anatomical reference, not a disease case-control cohort. | HCA links CELLxGENE exploration and downloadable resources, split by cell class and region. The portal lists about 2.5M neurons and 888.3k non-neuronal cells. Treat the Allen/HCA presentations of this reference as one dataset, not independent cohorts. |
| **Wang et al. Parkinson’s substantia nigra atlas, 2024** ([paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10780895/), [GEO GSE184950](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE184950)) | 32 donors: 23 idiopathic PD and 9 controls. 457,453 pre-QC droplet profiles; **315,867 high-quality nuclei** retained. This is not the Kamath study. | GEO lists a 1.7 GB TAR archive of processed supplementary data and an XLSX supplement; raw reads are in SRA. Internal matrix format and ready-made H5AD availability were not inspected. |

## Recommended order

1. **PFC427 for the next app import:** documented H5AD plus donor TSV is closest to the current workflow. First inspect file size, sparse layout, gene identifiers and donor-column compatibility; the data have not been downloaded or tested here.
2. **PsychAD for cross-disorder analysis:** prioritize after checking portal permissions and the specific release files. It is substantially larger than the present SEA-AD slice.

The PD atlas is a smaller disease-focused alternative. The Siletti reference is useful for anatomical context rather than AD case-control comparisons.

## Overlap and access cautions

PFC427 is a ROSMAP release, not an independent alternative to ROSMAP as a whole. Its repository supplies donor/cell overlap tables and includes earlier Mathys data. PsychAD also overlaps prior donor cohorts. Deduplicate donors and cells before pooling or using one release as independent validation.

Counts refer to specific publications or releases. Cells, pre-QC profiles, samples and donors are not interchangeable. Publicly listed download links were verified on source pages; bulk transfer and app compatibility were not tested. No datasets were downloaded and no app data were changed.
