# SEA-AD Slice

A small tool for exploring a large Alzheimer’s research dataset and pulling out the parts you actually want to work with.

The idea is pretty simple: instead of loading a huge file just to look at a specific group of cells or a handful of genes, build a searchable catalogue first, then use it to find and extract the relevant data.

This repo includes the search tools, a browser-based explorer, and the code that creates smaller datasets. It is a way to make the data easier to work with, not a tool that makes biological discoveries on its own.

## The dataset

[SEA-AD](https://brain-map.org/consortia/sea-ad/our-data), the Seattle Alzheimer’s Disease Brain Cell Atlas, provides data for studying brain cells in the context of Alzheimer’s disease.

This project uses the June 2026 RNA release for one brain region, the middle temporal gyrus (MTG). It contains measurements for roughly **1.18 million cells and 36,601 genes**, along with information about the cells and the people the samples came from.

Technically, these measurements come from cell nuclei, but I use “cells” here to keep things readable. The data and its annotations come from SEA-AD; this project adds a way to search and select from them.

## What it lets you do

You can start with a question like: “How many cells match this cell-type label, which donors do they come from, and can I get their measurements for these genes?”

From there, you can:

- Filter cells using the information already attached to them.
- Check how many cells match and how they are spread across donors.
- Select genes by name or identifier.
- Save the selected measurements as a smaller file for further analysis.
- Add up raw counts by donor, if you need a donor-level summary.

The last step is often called *pseudobulk*. It is a summary of the selected data, not a statistical test.

## How it works

There are two main pieces: **a catalogue of what is in the dataset**, and **the original file containing the gene measurements**.

### Find the cells first

The catalogue holds things like cell labels, donor IDs, and gene names. This information is called *metadata*: information describing the measurements, rather than the measurements themselves.

Searching the catalogue is a bit like looking up a book in a library catalogue. You can find what you need without opening every book. The catalogue lives in `data/mtg.sqlite`; SQLite is just the format used to store and search it.

### Read the measurements you need

Once the cells and genes are selected, the code reads their measurements from the original file in smaller chunks rather than loading the full expression matrix into memory.

It also keeps the data in a compact form that avoids storing every zero individually. Large selections can still take time, but you do not need to load the whole matrix just to work with a subset.

### Save the subset with a record of the selection

Exports use `.h5ad`, a common single-cell data format used with tools such as Scanpy. The file includes the selected measurements and their cell and gene information.

A separate recipe records the source and selection settings, so it is easier to see how the subset was made. The original data stays unchanged.

## What is in this copy?

**A GitHub checkout contains the code and documentation, not the dataset or search catalogue.** The catalogue and generated data files are excluded from Git. To build a catalogue from the original dataset, see [the technical guide](docs/technical-guide.md).

In the working copy used to prepare this repo, the search catalogue is available locally, but the full expression dataset is not. The catalogue is about **1.69 GB**. The original expression file is about **33 GB** and has been left out of this copy.

That means you can use the catalogue tools to search annotations, look up genes, and count matching cells. Reading expression values, creating new expression exports, or making donor-level summaries requires the original file.

The browser explorer’s code is also included, but its current startup requires that original file, so it is **not running in this copy**. This is a local project, not a hosted data service.

## Where things live

| Folder or file | What it is for |
| --- | --- |
| `app/` | The browser explorer, including the page you see and the server behind it. |
| `src/sea_ad_slice/` | The main code for searching, selecting, reading, and exporting data. |
| `data/` | The search catalogue and records identifying the original dataset. |
| `rust/` | An optional alternative implementation of one filtering step. You do not need to understand Rust to use the project. |
| `tests/` | Checks that the code behaves as expected on small, known examples. |
| `results/` | Reports and performance measurements from the original work. |
| `requirements.txt` | The Python packages needed to run the core tools. |
| `docs/technical-guide.md` | Commands and more detailed explanations for running or modifying the code. |

The scripts at the top level handle setup and checks, such as downloading the data, building the catalogue, and measuring performance. They are not things you need to run for every search.

## A few boundaries

- **Selection is not analysis.** The tool helps prepare data. It does not run a complete differential-expression analysis or account for differences between donors.
- **Labels need context.** For example, the `Immune` label should not automatically be read as “all of these are microglia.” Reference donors also need to be included or excluded deliberately.
- **Small previews are not random samples.** A cell limit takes the first matching cells in file order, not a balanced or representative group.
- **Raw and normalized values are different.** In this release, `UMIs` holds raw counts and `X` holds normalized expression. The export preserves whichever you select.
- **This is release-specific.** It does not automatically combine brain regions or make labels from different releases equivalent.

## Going a little deeper

You do not need to read the source code to get started with the project’s structure. These are the best next places to look:

- [Copy notes](COPY-NOTES.md): what was brought into this copy and what was left out.
- [Technical guide](docs/technical-guide.md): setup, example commands, and details for a computational collaborator.
- [Implementation report](results/implementation-report.md): what was checked and measured in the original workspace. These are historical results, not new tests of this copy; the generated expression files are not included here.
- [SEA-AD data overview](https://brain-map.org/consortia/sea-ad/our-data): the biological background and access information.

Please follow the Allen Institute’s data terms and citation guidance. The underlying dataset’s usage rights are separate from the code in this repo.
