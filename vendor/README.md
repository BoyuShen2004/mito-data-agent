# `vendor/` — large third-party dependencies vendored into this repo

Not tracked in git (see `.gitignore` — same reasoning as `/data/`: large
binaries and a full third-party source tree don't belong in this repo's own
history). This file is the one exception, kept so the directory's purpose
and provenance survive a fresh clone even though its contents don't.

## `sam2/` — facebookresearch/sam2, vendored

Backs `MITO_TRACKING_PROVIDER=sam2` (`backend/annotation/tracking/adapters/
sam2.py` + `sam2_bridge.py`) — the real GPU SAM2 model used for fork-aware
mitochondria tracking, as opposed to the dependency-free `local` CPU
stand-in used everywhere else (dev/CI/no-GPU).

**Why vendored instead of `pip install`ed**: this app deliberately never
requires `torch`/`sam2` outside of a GPU compute node (see
`progress/development.md`'s "Fork-aware SAM2 tracking on GPU nodes" section) —
`sam2_bridge.py` inserts `MITO_SAM2_ROOT` onto `sys.path` at the moment
`Sam2TrackingProvider._load()` actually runs, rather than the package being
pip-installed into the shared conda env, so importing the rest of the app
(and running the full test suite) never needs it.

**Provenance**: copied 2026-07-20 from `/projects/weilab/shenb/MTS/sam2`,
which was a checkout of `https://github.com/facebookresearch/sam2` at
commit `2b90b9f5ceec907a1c18123530e92e794ad901a4` (2024-12-15), plus four
downloaded checkpoints (`checkpoints/sam2.1_hiera_{tiny,small,base_plus,
large}.pt`, see `checkpoints/download_ckpts.sh` to refetch/verify). The
`.git` history of that checkout was **not** copied (no need to carry
upstream's repo history inside this one; if you need it, the original
checkout is still at `MTS/sam2` or re-clone upstream at the commit above).

**Default config**: `config/settings.py` points `MITO_SAM2_ROOT` at this
directory, `MITO_SAM2_CHECKPOINT` at `sam2.1_hiera_tiny.pt` (smallest/
fastest — swap to `sam2.1_hiera_large.pt` for the most accurate model, at
the cost of speed/VRAM), and `MITO_SAM2_CONFIG` at
`configs/sam2.1/sam2.1_hiera_t.yaml` — all overridable via `.env`. These
resolve out of the box as soon as this directory exists with this layout;
no `.env` changes needed unless you want a different checkpoint or keep the
checkout somewhere else.

**Regenerating this directory** (fresh clone, or after deleting it to save
space): either
- copy it again from another checkout of this repo / from `MTS/sam2` if
  still available, or
- re-clone upstream and re-download checkpoints:
  ```bash
  git clone https://github.com/facebookresearch/sam2.git vendor/sam2
  cd vendor/sam2 && git checkout 2b90b9f5ceec907a1c18123530e92e794ad901a4
  rm -rf .git   # optional — see "why vendored" above
  cd checkpoints && ./download_ckpts.sh
  ```

**Installing the GPU-only Python dependencies** (torch/torchvision/etc. —
never needed for local dev, only on a machine actually running
`MITO_TRACKING_PROVIDER=sam2`): see `requirements-sam2.txt` at the repo
root and `progress/development.md`.
