# `backend/volumes/` — Volume registration + HPC data discovery

Owns the `Volume` model (one image/label pair) and everything about getting
data *into* the app: scanning HPC directories, pairing image files with
mask files by filename convention, registering them as volumes, and
splitting a volume into z-range annotation tasks. The biggest and most
intricate file in the whole backend by logic-density is `services.py`
(867 lines) — most of it is filename-pairing heuristics, not business logic.

## Model (`models.py`)

**`Volume`** — one image (+ optional label) pair.
- `project` (denormalised from `dataset.project` — tasks/assignment/progress
  all query by project directly, so the two are kept in step by
  `register_volume`/`set_volume_dataset`, never edited independently).
- `dataset` — nullable, only for rows predating the `Dataset` model.
- `source_volume` / `chunk_id` — a "volume" in the registration sense is
  often a **chunk/crop** of a larger logical source volume; multiple chunks
  under the same dataset can share `source_volume`.
- Image: `image_path` (registered by reference, a path under
  `MITO_DATA_ROOT`) **or** `image_file` (uploaded `FileField`) — exactly one
  is normally set. `image_location` property returns whichever is set,
  file taking precedence.
- Label: same pattern (`label_path`/`label_file` → `label_location`), plus
  `label_type` (`none`/`prediction`/`proofread`/`partial` —
  `core.choices.LabelType`, drives what task type splitting produces).
- `shape_z/y/x`, `voxel_size_z/y/x` — best-effort, filled by
  `_try_autodetect_shape` from file headers (`core.utils`) if not supplied.
- `has_label` property: `label_type != NONE and (label_path or label_file)`.

**Data safety: be careful with anything that *writes* to
`image_location`/`label_location`.** A real
externally-referenced label file was overwritten during this project's
development because a write path didn't distinguish "the app's own copy"
from "a path registered by reference to someone else's data." The fix lives
in `annotation.services` (`_save_label_volume`/`_writable_label`), not
here, but the *reason* it's dangerous is this dual `path`/`file` pattern —
`label_path` can be **any absolute path on disk**, not necessarily
something this app owns.

`label_path` is the volume's **official, approved** label — in-app edits (paint or
SAM2 tracking) never touch it directly; they write to a separate *working*
copy (`annotation.label_paths.working_label_rel_path(volume)`,
`<project name>/<dataset name>/volume_<id>_labels.tif` **directly** under
`MITO_DATA_ROOT` — no extra `labels/` folder, no numeric id prefixes on the
directory names (a prior version had both; removed for
being unrecognizable/redundant) — organized to mirror the project → dataset
→ volume hierarchy the frontend shows, so the on-disk layout under `data/`
is legible to a backend developer). `label_path` only changes when a
manager **approves** an in-app submission
(`annotation.services.approve_submission` →
`_promote_working_label_to_official`) — see `backend/annotation/MODULE.md`'s
"Label persistence" section for the full split.

## Data registration pipeline (`services.py`)

The filename-pairing logic (`pair_by_case`, `detect_volume_pairs`,
`case_key`, `channel_index`, `_is_mask_name`, `_core_key`) exists so a
requester can point at a directory of files with **inconsistent naming**
(e.g. `sample01_em.tif` + `sample01_mask.tif`, or `case3.tif` +
`case3_label.tif`) and have them auto-paired by inferred "case" identity,
without a rigid naming convention. Rough shape:
1. `_stem`/`_name_tokens` normalize a filename to comparable tokens.
2. `_is_mask_name` flags likely-mask files by keyword (`mask`, `label`,
   `seg`, ...).
3. `_core_key` strips the mask-indicating tokens so an image/mask pair
   reduces to the same key.
4. `case_key`/`channel_index` handle multi-channel/multi-case naming.
5. `pair_by_case`/`detect_volume_pairs` produce the final `(image, mask)`
   pairs plus a list of unmatched files (surfaced to the user to resolve
   manually).

**Registration flow**, roughly:
1. `scan_data_sources(image_directory, mask_directory)` (or
   `scan_hpc_directory` for a single combined directory) — lists files,
   detects pairs, reads any `read_dataset_manifest` (a JSON manifest a
   directory can ship with pre-declared pairs/metadata, checked first —
   `_manifest_pairs_for` — before falling back to filename heuristics).
   Also `suggest_sibling_directories` — if you point at an image dir, it
   guesses where the matching mask dir might be (`_looks_like_mask_dir`/
   `_looks_like_image_dir`).
2. `register_dataset(created_by, dataset, volume, image_directory,
   mask_directory, pairs, files, label_type, metadata, project,
   annotation_type, reviewed)` — the actual write: creates/reuses the
   `Dataset`, creates one `Volume` per pair via `register_volume`.
3. `register_volume(project, name, image_path/file, label_path/file,
   label_type, file_format, voxel_size, metadata)` — creates the `Volume`
   row, autodetecting shape via `_try_autodetect_shape` if not given.
4. `update_volume_metadata(volume, **fields)` — the general-purpose editor
   used by `VolumeDetailView.update` (metadata merges, everything else
   replaces).

**Splitting into tasks:**
- `split_volume_by_frames(shape_z, z_step=16)` → list of `(z_start, z_end)`
  ranges. `MITO_DEFAULT_Z_STEP` (setting) is the default step.
- `infer_task_type(label_type, override=None)` →
  `core.choices.LABEL_TYPE_TO_TASK_TYPE` (e.g. a volume with `prediction`
  labels splits into `prediction_proofreading` tasks by default).
- `create_tasks_from_volume(volume, z_step, task_type, priority,
  instructions)` — creates one `AnnotationTask` per z-range. Requires the
  volume's project to be `manager_reviewed` (enforced in the view, not
  here — see `VolumeSplitView` below).

## API (`api.py`)

- `HpcScanView` — `POST /api/hpc/scan/`, requesters+managers
  (`CanRegisterData`). Wraps `scan_data_sources`.
- `RegisterDataView` — `POST /api/register-data/`, the shared
  requester/manager registration endpoint. Requesters may only register
  into **their own** projects (checked against `project.created_by_id`).
  Manager-registered data is `reviewed=True` on creation; requester data
  stays pending.
- `ProjectVolumesView` — list/create volumes under
  `/api/projects/<project_id>/volumes/`; same ownership check pattern.
- `VolumeDetailView` — retrieve/update/delete a single volume.
  - `get_object` re-checks ownership (managers, or the owning requester)
    on every access, not just list.
  - `update` blocks moving a volume to a dataset the caller doesn't own.
  - `destroy` — `?force=1` bypasses the `DeleteBlocked` guard (409 with
    `{"detail", "counts"}` otherwise), same pattern as `projects`.
- `VolumeDependentsView` — pre-delete warning data (`GET`).
- `VolumeSplitView` — `POST /api/volumes/<id>/split/`, **managers only**
  (`IsManager`, stricter than the other volume endpoints). Refuses
  (400) if `not volume.project.manager_reviewed` — this is where the
  review-gate is actually enforced, not in the model or service layer.

## Gotchas

- `image_location`/`label_location` are **properties**, not DB fields — you
  can't `.filter(image_location=...)` on them; filter on `image_path`/
  `image_file` directly if you need a queryset-level check.
- Requester ownership checks are duplicated across several views
  (`ProjectVolumesView.get_project`, `VolumeDetailView.get_object`,
  `RegisterDataView.post`) rather than centralized — if you add a new
  volume-touching endpoint, copy the `is_manager(user) or
  project.created_by_id == user.id` pattern rather than assuming a shared
  helper exists.
