# What is included

This GitHub repository contains the SEA-AD explorer source, Python query tools, optional Rust filtering source, tests, documentation, and historical benchmark records.

## Data stays outside Git

The full expression file (`SEAAD_MTG_RNAseq_final-nuclei.2026-06-22.h5ad`, about 33 GB) and the generated metadata catalogue (`mtg.sqlite`, about 1.69 GB) are not committed. Neither are generated expression exports, compiled libraries, caches, or source ZIP bundles.

The working copy used to prepare this repository had a local metadata catalogue. That does not mean the catalogue is included when you clone the repository. See [the technical guide](docs/technical-guide.md) for download and indexing commands. Those commands require the Python dependencies and enough disk space for the original data and catalogue.

## What needs which files

With a built catalogue, the catalogue tools can search annotations, count cohorts, and look up cells and genes without reading the expression file. Reading expression values, exporting new expression subsets, and donor-level aggregation require the original expression data as well.

The browser explorer currently checks for the source expression file at startup, so it cannot run with the catalogue alone. It is not deployed by cloning this repository. Its example expression downloads also depend on generated outputs that are not committed.

## Historical records

Reports under `results/` and `app/` describe work done in the original workspace. They are not a claim that the full dataset or a running app is included, or that all tests have been rerun in a fresh checkout. Paths in those records may refer to files that are deliberately excluded from Git.
