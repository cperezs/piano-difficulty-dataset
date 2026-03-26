# Difficulty-Annotated MusicXML Dataset for Piano

This repository contains the code and metadata required to reconstruct the MusicXML dataset with measure-level difficulty annotations described in the accompanying paper:

> **[Paper title placeholder]**
> [Author list placeholder]
> *Journal*. DOI: [https://doi.org/PLACEHOLDER](https://doi.org/PLACEHOLDER)

The dataset comprises 64 piano scores in MusicXML format, each annotated with difficulty-relevant measures. The scores span a wide range of the classical piano repertoire, and cover all difficulty levels. The original scores are sourced from the CIPI dataset; this repository provides the patches and scripts needed to deterministically reconstruct the annotated versions from those originals.

## Prerequisites

- **Python 3.12** (tested version)
- Access to the **CIPI dataset**, available on Zenodo: [https://doi.org/10.5281/zenodo.8037327](https://doi.org/10.5281/zenodo.8037327)

The CIPI dataset is described in the following publication:

> Ramoneda, P., Jeong, D., Eremenko, V., Tamer, N. C., Miron, M., & Serra, X. (2024). Combining Piano Performance Dimensions for Score Difficulty Classification. *Expert Systems with Applications*, 238, 121776. DOI: [https://doi.org/10.1016/j.eswa.2023.121776](https://doi.org/10.1016/j.eswa.2023.121776)

## Repository Structure

```
├── CIPI/                      # CIPI scores (user-provided; not tracked)
│   └── scores.zip.sha256      # SHA-256 checksum for scores.zip
├── difficulty_dataset/        # Reconstructed annotated MusicXML files (output)
├── metadata/
│   ├── checksums.csv          # SHA-256 checksums for all source and output files
│   ├── works_metadata.csv     # Composer, work, and movement metadata per file
│   └── annotations.json       # Annotated measure numbers for each file
├── patches/                   # Unified diff patches (one per score)
├── scripts/
│   ├── apply_patches.py       # Reconstruction script
│   └── create_patches.py      # Patch generation script (for reproducibility)
├── logs/                      # Execution logs (generated at runtime)
├── create_difficulty_dataset.sh  # Shell entry point
├── run_docker.sh              # Docker-based alternative entry point
└── README.md
```

## Reconstructing the Dataset

### Step 1 — Obtain the CIPI Scores

Download the file `scores.zip` from **version 0.1** of the CIPI dataset on Zenodo ([https://doi.org/10.5281/zenodo.8037327](https://doi.org/10.5281/zenodo.8037327)) and place it in the `CIPI/` directory of this repository.

### Step 2 — Run the Reconstruction Script

**Option A — Direct execution:**

```bash
bash create_difficulty_dataset.sh
```

**Option B — Using Docker** (no local Python installation required):

```bash
bash run_docker.sh
```

The Docker option runs `create_difficulty_dataset.sh` inside a `python:3.12-slim` container with the repository mounted as a volume.

### Step 3 — Retrieve the Output

Upon successful completion, the 64 reconstructed MusicXML files will be located in the `difficulty_dataset/` directory.

## Reconstruction Pipeline

The reconstruction script (`scripts/apply_patches.py`) executes the following steps:

1. **Verify `scores.zip` integrity** — Computes the SHA-256 hash of `CIPI/scores.zip` and compares it against the expected value in `CIPI/scores.zip.sha256`.
2. **Extract `scores.zip`** — Extracts the original CIPI score files into the `CIPI/` directory.
3. **Verify source checksums** — Validates each original score file against the checksums recorded in `metadata/checksums.csv`.
4. **Apply patches** — Applies the unified diff patches from `patches/` to reconstruct each annotated MusicXML file in `difficulty_dataset/`.
5. **Verify output checksums** — Validates each reconstructed file against the expected checksums in `metadata/checksums.csv`.

## Metadata

### `metadata/checksums.csv`

A semicolon-delimited CSV file with the following columns:

| Column | Description |
|---|---|
| `cipi_file` | Relative path to the original CIPI source file |
| `cipi_sha256` | SHA-256 checksum of the source file |
| `dataset_file` | Relative path to the reconstructed output file |
| `dataset_sha256` | SHA-256 checksum of the expected output file |

### `metadata/works_metadata.csv`

A semicolon-delimited CSV file containing bibliographic metadata for each score:

| Column | Description |
|---|---|
| `dataset_file` | Relative path to the dataset file |
| `composer` | Composer name (last, first) |
| `work_number` | Catalogue or opus number |
| `work_title` | Title of the work or collection |
| `movement_number` | Movement number within the work |
| `movement_title` | Full movement title including key and catalogue number |

### `metadata/annotations.json`

A JSON file mapping each dataset filename to its difficulty annotations. Each entry contains:

| Field | Description |
|---|---|
| `measures` | List of 1-indexed measure numbers annotated as difficulty-relevant |
| `total_measures` | Total number of measures in the score |
| `percentage` | Proportion of annotated measures relative to the total |

## Additional Scripts

The file `scripts/create_patches.py` contains the code used to generate the patches in `patches/` from the original and annotated score files. It is included for full reproducibility of the dataset construction pipeline but is **not required** to reconstruct the dataset.

## License

### Code License

The code in this repository (scripts, shell files, and all other software) is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for the complete license text.

### Dataset License

The resulting MusicXML dataset is licensed under the **Creative Commons Attribution 4.0 International License (CC BY 4.0)**. When using the dataset, you must provide appropriate attribution to the authors. See the [LICENSE-DATA](LICENSE-DATA) file for the complete license text, or visit [https://creativecommons.org/licenses/by/4.0/](https://creativecommons.org/licenses/by/4.0/) for more information.

### Citation

When using this dataset, please cite the accompanying research paper ([https://doi.org/PLACEHOLDER](https://doi.org/PLACEHOLDER)) and provide attribution to the dataset creators.
