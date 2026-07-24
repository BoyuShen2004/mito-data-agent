# `frontend/src/features/` — the annotation editor + provider launchers

Sub-features, each a self-contained folder. This is the module most worth
reading carefully if you're continuing annotation-editor work — read
alongside `backend/annotation/MODULE.md`, the backend half of `viewer/`.

## `viewer/` — the annotation UI

Both `/viewer/*` and `/editor/*` use `RequireAuth fullBleed` (global navbar
kept; no 1080px `.container`). `../pages/ViewerPage.tsx` builds
`.editor-shell` under that navbar so the canvas fills the remaining window.
Leave/home is navbar-only; the editor topbar carries only Annotate/View +
Submit.

Two rendering components share one approach (fit-to-window **or**
fit-to-width, CSS-filter brightness/contrast on a 0–100% scale via
`displayFilter`/`DisplayKnobs`, typeable slice index + zoom % via
`CommitNumberInput`, Ctrl/Cmd+wheel zoom, A/D/arrow navigation, bounded
blob-URL LRU caching), but serve different purposes:

- **`SliceViewer.tsx`** — read-only viewer, used **only** for
  `/viewer/volumes/:id` (`VolumeViewerPage`). Fetches raw intensity slices
  (once per axis+index, via `imageSlicePath`) plus, optionally, the
  colorized label overlay (`labelSlicePath`). Brightness/contrast are pure
  client-side CSS filters (50% = neutral) — **no network request on slider
  drag**. Default `zoom = 1` means *fit to viewport* (via container query
  units `100cqw`/`100cqh`), not native pixel size.
- **`AnnotationCanvas.tsx`** — the paint editor, and also the task viewer.
  `TaskViewerPage` mounts it for **both** `/editor/tasks/:id` (Annotate) and
  `/viewer/tasks/:id` (View) with an **`editable` prop**: `editable` mounts
  the tool chrome and enables all mutation; without it the same surface
  renders read-only (`data-mode="view"`, every paint/AI/box/seed path is
  inert). Edit access is gated in `ViewerPage.tsx` (`isManager ||
  task.assigned_to === user.id`).

### Shared knobs

- **`CommitNumberInput.tsx`** — draft-friendly number field (commit on
  Enter/blur, clamp to min/max); used for slice, zoom %, brightness %,
  contrast %.
- **`DisplayKnobs.tsx`** + **`displayAdjust.ts`** — Brightness/Contrast/Label
  opacity sliders with `N%` inputs; `displayFilter(b, c)` maps 50 → identity.

### `AnnotationCanvas.tsx` chrome — `annotate/`

The Annotate-only chrome lives under `viewer/annotate/` and mounts only when
`editable`:

- **`paintTools.ts`** — the `PaintTool` union + `AI_POINT_TOOLS` /
  `AI_PREVIEW_TOOLS` sets.
- **`AnnotateToolChrome.tsx`** — the horizontal mode-select tool strip +
  the per-tool contextual controls row.
- **`TrackRail.tsx`** — the left Track (SAM2) rail.

**Tools** (Cellable's vertical rail, rotated horizontal to keep the 2D
canvas large):

| Tool | Cellable equiv. | Behavior |
| --- | --- | --- |
| Select (V) | edit | Eyedropper — picks the clicked instance as `activeId`, never paints |
| Brush (B) | brush | Circular stamp of `activeId`; a live size-circle cursor follows the pointer (native cursor hidden) |
| Erase (E) | erase (circular) | Circular stamp of `0`; same size-circle cursor |
| Box Erase (R) | erase (box) | Drag a box, release clears that rectangle; full-image crosshair while active. mito-only (kept alongside circular Erase) |
| Point Mask (P) | `ai_mask` | Click positive points (Shift = negative); each re-predicts (`POST /tasks/:id/predict-mask/` mode `points`) into a green-fill + white-contour **proposal**. After ≥1 committed point the proposal **follows the cursor**. Commit (button/Enter/Ctrl-click/double-click) re-predicts committed-only then merges into the raster at `activeId`; Clear (Esc) discards; Alt+click removes one point |
| Box Mask (M) | `rectangle` + AI | Drag a box (crosshair while active); release predicts (mode `box`) the same proposal; Commit (Enter) / Clear (Esc). Always proposes then waits — never auto-commits on release; no cursor-follow |
| Boundary (O) | `ai_boundary` | Same UX as Point Mask, but mode `boundary` — backend returns a ring (`dilate ^ erode`) |
| Seeds (T) | `watershed_3d` | Click an instance to set the split target + first seed; more clicks (persist across slice nav) add seeds on the same label; Run Watershed (`POST /tasks/:id/watershed/`) writes the split to the working copy and reloads |

Point/Box/Boundary never write to the server themselves — the predicted
mask is a **proposal** (`aiPreviewRef`) the user explicitly commits, so a
bad/slow prediction never silently flattens into the raster. All three reset
on slice navigation (embeddings are per-slice) **and on switching tools**
(`clearAiPoints`, from a `paintTool`-watching effect that also aborts any
in-flight predict). Seeds deliberately does **not** reset (a split can be
seeded across several z's).

**Proposed-mask look** — green translucent fill (`AI_PREVIEW_FILL_ALPHA =
130`, ~0.5 alpha, matching Cellable's `label_opacity = 0.5` preview) plus an
opaque white contour (`strokeMaskContour` — walks mask pixels and strokes
each edge shared with a background/out-of-bounds neighbor; pixel-grid, since
there's no `skimage` in the browser).

**Cursor-follow live proposal (Point/Boundary only)** — Cellable re-predicts
`committed_points ∪ {cursor tip}` on every repaint. Ported as:
- **`aiTipRef`** — transient `{x, y, label}` (or `null`), never written into
  `aiPointsRef`; `null` until ≥1 point is committed; `label` flips on Shift
  every move.
- **`runPredictPointsWith(pts, opts)`** — the shared predict core every path
  calls (click, Alt-click, finalize, drag-release, live hover), sharing one
  `aiSeqRef`/`aiAbortRef` guard so a click and a hover predict can't corrupt
  each other. `opts.silent` skips busy/error state; `opts.live` doesn't
  abort in-flight and passes no `AbortSignal`.
- **Coalesced, not throttled** — `livePredictRef` (`{inFlight, dirty}`): at
  most one live predict in flight; a move mid-flight sets `dirty`; the
  `finally` fires exactly one follow-up for the current tip once it resolves
  (via `runPredictPointsWithRef`, read fresh to avoid a stale-closure
  self-call). An abort-every-move version froze the mask on a stale fill;
  coalescing replaced it — there is no `LIVE_PREDICT_THROTTLE_MS` anymore.
- `onPointerMove` updates `aiTipRef`, calls the cheap `renderCursorOverlay()`
  (tip vertex + a rubber-band line to it track the cursor every frame),
  then `scheduleLivePredict()`. The green fill only updates when a live
  predict lands — "keep last-good preview while in flight" falls out for
  free (`aiPreviewRef` is only overwritten by a successful response).
- **Drag a committed point** — clicking within ~10px of an existing point
  starts a drag (`draggingPointIdxRef`, a **separate** ref from `drawingRef`
  so it never falls into `onPointerUp`'s brush/box commit path); move
  live-predicts, release fires one final non-live predict.
  `nearestCommittedPointIndex()` is the shared hit-test for both drag-start
  and Alt+click-remove.
- **Finalize discards the tip** — `finalizeAiPoints()` (Enter/Ctrl-click/
  double-click) re-predicts committed-only then commits, so the committed
  mask can legitimately differ from the last hover frame.
- Leaving the canvas drops the tip and immediately re-predicts committed-only.

**Screen-constant prompt graphics** — prompt points, the proposal contour,
box rubber-band + corner handles + crosshair, and seed crosshairs are sized
from the canvas's real on-screen scale (`drawVectorOverlay` measures
`getBoundingClientRect().width / w` fresh every repaint, folding in both
`zoom` and fit-window/fit-width auto-scale, then `toImagePx`-converts a
desired on-screen size). The brush/erase size cursor is the one exception —
drawn at a **true** image-space radius (`brushSize`), since it must match
the actual stamp footprint. `renderOverlay`'s deps include `zoom`/`fitMode`
so markers rescale live.

**SAM fluency** — a debounced (~100ms) effect fires `warmEmbedding` for the
current slice (and its two neighbors, best-effort) whenever a Point/Box/
Boundary tool is active or newly selected. Stale-response guards: `aiSeqRef`
(monotonic counter) + `aiAbortRef` — every predict bumps the counter, aborts
what's running, and only applies its result if still current. Empty-mask
predicts clear the preview with a short status. `committingAiRef` guards
against a double Enter/click re-entering `commitAiPreview`. A ~100ms
slice-nav debounce (`[index, meta.data]` effect) means holding A/D fetches
only the settled slice; the previous slice stays visible until the new fetch
resolves (`loadSlice` swaps `imgRef`/`idsRef` only on resolve).

### Layout

**CSS-grid main row** (`.canvas-main-row`) — areas `"track main dock" /
"track main labels"`: a **left** Track (SAM2) rail (`.track-rail`), the
center 2D canvas (`main`), and a right column of `Labels3DPanel` (top,
`dock`) over `LabelsPanel` (bottom, `labels`). The right column is
`clamp(280px, 28vw, 340px)` (voxel sizes shown per row via
`.labels-row-size`); both side columns use `clamp()` so they shrink rather
than starve the canvas.

**Swap 3D ↔ Canvas** — the button on the 3D panel header toggles `swapped`,
which flips the grid via `.canvas-main-row[data-swapped="true"]` so the 3D
view fills the center and the 2D canvas shrinks into the dock cell.
CSS-only: neither panel is remounted, so the loaded slice and the 3D
pin/active-label selection survive the swap both ways. While swapped the 2D
surface is **view-only** — an early `return` on `swapped` in `onPointerDown`
(every mutation originates there), a `<fieldset disabled={swapped}>` around
the tool rows, and `!swapped` gates on context-menu + keyboard Undo/Redo.

**Track (SAM2)** is a persistent left rail, not a page/tab — you paint or
AI-mask the active instance with the normal tools, then Track propagates
*whatever that instance currently looks like on this slice* across a z-range
via fork-aware SAM2 (`POST /tasks/:id/track/`). SAM2 is strictly the
propagator; EfficientSAM (Point/Box/Boundary) is strictly the interactive
single-slice segmenter. The z-range defaults to `[zStart, zEnd - 1]`.

**Canvas-stability rule**: the mode-select row and the contextual row are
fixed-height + `nowrap` (scroll horizontally, never wrap) so switching tools
never changes their height. `.canvas-main-row` is the only thing that
flexes. The status readout is an absolute overlay **inside**
`.canvas-viewport` (`.canvas-status-overlay`), never a row beneath it — so it
costs no canvas height. There is no permanent hotkey footer (the map lives
in `development.md` + the "Tool hotkeys" section below).

### Architecture

An `<img>` (intensity, CSS-filtered) with a `<canvas>` overlay on top. The
overlay is **not** re-fetched as an image — it's rendered client-side from a
raw `Int32Array` of instance ids (`idsRef`, one per loaded slice, decoded
from RLE via `getLabelIds`) using the same color hash as the backend
(`labelColor()`), via `ctx.putImageData`. Painting mutates `idsRef` directly
(`paintAt`), re-renders, and only hits the network on stroke-end
(`onPointerUp` → `commit()` RLE-encodes the slice and `PUT`s it).

**Rendering is two passes**: `computeBaseImage()` does the `O(h·w)` per-pixel
loop (label colors + green proposal fill) and `putImageData`s it, caching the
`ImageData` in `imageDataRef` (reused every repaint, reallocated only when
`[h, w]` changes). `drawVectorOverlay()` draws everything else on top with
normal canvas ops (points, box rect + handles, white contour, crosshair,
brush circle, seed crosshairs) — a pure function of state.
`renderOverlay()` = both (call when the fill changed). `renderCursorOverlay()`
= re-blit the cached `imageDataRef` + `drawVectorOverlay()` only — used for
box-drag and hover-only cursor feedback, so scrubbing the mouse never re-pays
the label loop.

**Saving is always to a staging copy, not "the" label** — every `commit()`
persists to the volume's *working* label copy
(`backend/annotation/label_paths.py`), which nothing outside the editor sees
until a manager approves a submission referencing it; read-only viewers keep
showing the last *approved* state. `ViewerPage.tsx`'s "Submit for review"
button (next to this component, not inside it) creates the reviewable
checkpoint; a manager approving it promotes the staging copy to official.

**Default tool is Select** (`useState<PaintTool>("select")`) — opening a
task never starts mid-stroke or mid-AI-prompt. User requirement, do not
change.

**Tool hotkeys** (Cellable's `default_config.yaml`): `v`/`b`/`e`
Select/Brush/Erase, `p`/`m`/`o` Point/Box/Boundary, `t` Seeds, `r` Box Erase
(mito-only), `Ctrl/Cmd+Z` / `Ctrl/Cmd+Shift+Z` undo/redo. `Escape` clears the
proposal (and an in-progress Box drag) on any of Point/Box/Boundary, and
closes the context menu. The full map is in `development.md`.

**Label-lifecycle/visibility hotkeys** (all on `activeId`): `f` Verify,
`Shift+r` Revert (only if `can_revert`; bare `r` stays Box Erase — checked
via `e.shiftKey` + `e.key.toLowerCase()` so Caps Lock can't swap them),
`Delete` Reject (behind the same `window.confirm` the button uses — deletes
the label from the whole volume), `h` toggle Hide Verified, `s` Solo,
`Shift+s` Show all. All read `labelsSummaryRows`/`activeId` directly, the
same data the Filters Options buttons use.

**Busy indicator** — `aiLoading` drives a small pulsing `⋯` next to Commit;
only click/Alt-click/finalize/drag-release predicts set it (live hover
predicts pass `silent: true`), so it never flickers on mouse move.

**Right-click context menu** (`.canvas-context-menu`) — mode switches
always; Verify/Solo for the clicked label when over an actual label. Closes
on Escape or a click outside.

**Status readout** — z/x/y/intensity/label, written directly to
`statusReadoutRef.current.textContent` from every `onPointerMove` (never via
React state — pointer moves are too frequent for a re-render). Intensity
comes from `intensityCtxRef`, an offscreen canvas holding the *undisplayed*
(pre-CSS-filter) slice image, repopulated on the `<img>`'s `onLoad`.

**Wheel → z-slice** — plain wheel over the canvas changes the z-slice
(throttled ~40ms); Ctrl/Cmd+wheel zooms. `SliceViewer`'s plain wheel still
pans its native scrollable viewport — the two viewers' wheel behavior
genuinely diverges here.

**Label opacity** — a `DisplayKnobs` knob (`labelOpacity`, 0–100, default
100) scales committed overlay alpha only; the AI proposal fill is untouched.

**Track (SAM2)** RLE-encodes the active instance's current-slice footprint
as **true-runs** (not the label-id RLE format — see `../api/MODULE.md`),
calls `trackTaskFork` with the z-range, then reloads the slice (tracking
mutates the whole label volume server-side).

**Undo/redo** — client-side full-slice `Int32Array` snapshot stacks
(`undoStack`/`redoStack`, capped `MAX_UNDO = 20`), pushed before each
stroke/delete. Each undo/redo **re-commits to the server**, so it survives a
reload. Full-array snapshots, not shape-level deltas — simpler, hence the
depth cap.

### `LabelsPanel.tsx`

Two **scopes**:
- **This slice** — every unique nonzero id on the current slice
  (`uniqueInstances`, recomputed on slice load + after each commit, not per
  pointer-move). Per instance: swatch + state dot, click-to-activate, solo,
  hide, delete (clears just that instance from this slice through the undo
  stack), and a **3D** pin toggle.
- **All** (default) — every label in the volume's working copy + lifecycle
  state, from `GET /tasks/:id/labels-summary/`. Rows show a `z start–end`
  range; clicking activates + jumps (`onJumpToZ`) to `z_start`.

**Filters Options** (`filtersOpen`, `.labels-filters-popup`) applies to the
All scope: Show (All/Proposed/Edited/Verified/Not Verified), Hide Verified
(default on), Solo / Show All, Sort (ID/Size/State), and lifecycle actions on
the active label — Verify / Unverify (only if `verified`) / Revert (only if
`can_revert`) / Reject (behind `window.confirm`) → `onLifecycleAction` →
`POST /tasks/:id/labels/<id>/lifecycle/`. A state legend (`○N ◐N ●N`) + an
"M of N" count sit in the compact header. A text filter narrows either scope
by id substring (Enter jumps in All scope).

**Ownership**: `rows`/`rowsLoading` and `hideVerified` are owned by
`AnnotationCanvas`, not `LabelsPanel` (presentational). `hideVerified` also
gates the 2D overlay (`verifiedIds`/`renderOverlay`), so the data lives where
both consumers share it.

### `Labels3DPanel.tsx`

Plays the role of Cellable's `VTKSurfaceWidget`. Fetches a compact binary
per-label downsampled voxel grid from `GET /tasks/:id/labels-3d/?labels=...`
(`fetchLabels3D`) for the pinned ids (+ `activeId`), culls to surface voxels
client-side (`surfaceVoxels`), and renders one `THREE.InstancedMesh` cube per
surface voxel per label (`labelColor()`). **Not** a true iso-surface — see
`cellable_port/labels_3d.py` for why block-max-pooled surface voxels were the
smallest change giving real 3D shape feedback in a browser. Orbit/zoom via
three.js `OrbitControls`. Owns its own fetch (unlike `LabelsPanel`).

### `labelColor.ts`

`labelColor`/`labelColorCss` — deterministic id→color, shared by
`AnnotationCanvas`, `LabelsPanel`, `Labels3DPanel`; mirrors the backend's
`_label_color` in `slice_io.py`.

## `proofreading/`

`ProofreadingLaunch.tsx` + `api.ts` — a generic "Open Proofreading Tool"
panel reading whatever the configured proofreading provider reports, and
rendering an open-editor / open-viewer link or a reason it can't, plus a
"Download task descriptor" button when available. Used on `TaskDetailPage`
as a launcher into the editor.

## `lifecycle/`

`LifecycleTabs.tsx` + `api.ts` — an "All / New / To Proofread / Done" tab bar
backed by `GET /api/projects/lifecycle-counts/`. The classification lives on
the backend (`backend/core/lifecycle.py`); this only fetches counts + renders
tabs. Used by `RequesterDashboard`.

## Gotchas

- `AnnotationCanvas` and `SliceViewer` independently implement the same
  fit-to-window/CSS-filter pattern rather than sharing a base — fix a
  rendering bug in one, check the other. Their **wheel behavior genuinely
  diverges** (Annotate = z-slice, SliceViewer = pan); don't blindly "fix
  both the same way" for wheel changes.
- Visibility/solo (`hiddenIds`/`soloId`) and 3D pins (`pinned3D`) are
  client-side only, reset on unmount — no persistence across reload or
  between users. Persistent versions would need new backend fields.
- **Watershed seeds persist across slice navigation**; everything else that
  looks like in-progress input (AI points, preview, `aiTipRef`, box
  rectangle) resets on slice change. Check which kind you're touching.
- The proposal fill (`aiPreviewRef`) is composited inside `computeBaseImage`
  alongside label colors (one `putImageData`); every other overlay element
  is drawn *after*, in `drawVectorOverlay`, never via a second `putImageData`
  (which would wipe the fill). Call `renderOverlay()` if you changed
  `idsRef`/preview/visibility, `renderCursorOverlay()` for a hover-only
  redraw.
- `draggingPointIdxRef` (dragging a committed AI point) is a **separate** ref
  from `drawingRef` — a dragged point never touches `idsRef`, so it must
  never fall into `onPointerUp`'s `commit()` path. Check both refs if you
  touch `onPointerUp`.
- `intensityCtxRef` (status intensity) is repopulated from the `<img>`'s
  `onLoad`, not from `loadSlice` — don't assume it's valid the instant
  `loadSlice` resolves; the image may still be decoding.
