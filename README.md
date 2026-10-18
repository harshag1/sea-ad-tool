# SEA-AD Slice

Explore brain-cell data from Alzheimer’s research and pull out the cells and genes you want to study, without loading the whole dataset into memory.

This project provides a searchable catalogue, a browser explorer, and tools for saving smaller datasets. It prepares data, rather than running statistical analyses.

## How searching works

1. **Search the descriptions.** A catalogue stores cell-type labels, donor information, and gene names separately from the gene measurements. You can search these descriptions without opening the large measurement file.
2. **Choose a group.** Filter cells, choose genes, and preview how many cells match and which donors they come from.
3. **Read what you need.** The tools read the selected measurements in manageable chunks and can export a smaller `.h5ad` file for further analysis. They can also sum raw counts by donor, a summary called *pseudobulk*.

## About the data

The source is the **June 2026 SEA-AD RNA release** for the middle temporal gyrus (MTG): roughly **1.18 million cells and 36,601 genes**. “Cells” here means cell nuclei. SEA-AD supplies the data.

**The data is not included in Git.** You must download the original file (about 33 GB) and build the catalogue (about 1.69 GB). A built catalogue supports description searches and counts alone; reading measurements, exporting subsets, and using the browser explorer also require the original file. Generated exports are not included either.

## Find your way around

| Location | Contents |
| --- | --- |
| `src/sea_ad_slice/` | Search and export tools |
| `app/` | Browser explorer; see [app setup](app/README.md) |
| `data/` | Source records; local data and catalogue belong here |
| `tests/`, `rust/` | Code checks and optional filtering code |
| `docs/`, `results/` | Technical instructions and historical validation reports |

See the [technical guide](docs/technical-guide.md) for setup and usage. Reports are historical, not fresh-checkout verification.

## Keep in mind

Cell labels need biological context, and limited previews are not random samples. Raw counts (`UMIs`) and normalized expression (`X`) are different. This tool targets one release and brain region.

Follow [SEA-AD’s data access, terms, and citation guidance](https://brain-map.org/consortia/sea-ad/our-data). Dataset rights are separate from this code.
