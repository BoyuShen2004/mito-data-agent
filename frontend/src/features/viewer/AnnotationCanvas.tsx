import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  decodeRuns,
  encodeRuns,
  fetchObjectUrl,
  getLabelIds,
  getLabelState,
  getLabelsSummary,
  getVolumeMeta,
  imageSlicePath,
  predictBoundary,
  predictMaskFromBox,
  predictMaskFromPoints,
  putLabelIds,
  runWatershed,
  setLabelLifecycle,
  trackTaskFork,
  warmEmbedding,
  type LabelLifecycleAction,
  type LabelSummaryRow,
  type VolumeMeta,
  type WatershedSeed,
} from "../../api/viewer";
import { useAsync } from "../../hooks/useAsync";
import CommitNumberInput from "./CommitNumberInput";
import DisplayKnobs from "./DisplayKnobs";
import { displayFilter } from "./displayAdjust";
import { labelColor, labelColorCss } from "./labelColor";
import LabelsPanel from "./LabelsPanel";
import Labels3DPanel from "./Labels3DPanel";
import AnnotateToolChrome from "./annotate/AnnotateToolChrome";
import TrackRail from "./annotate/TrackRail";
import {
  AI_POINT_TOOLS,
  AI_PREVIEW_TOOLS,
  type PaintTool,
} from "./annotate/paintTools";

// Shared canvas for View + Annotate. Annotate-only chrome (tool strip,
// Track/SAM2) lives under `./annotate/` and mounts only when `editable`.
// Labels / 3D Labels sit on the right in both modes (resize / collapse).
//
// Tool set mirrors Cellable's left tool rail (app.py's `mode_actions` /
// canvas.py's `createMode`), laid out horizontally:
//   Select / Brush / Erase / Box Erase / Point Mask / Box Mask / Boundary / Seeds
// Track propagates the active instance across z via fork-aware SAM2.
// EfficientSAM (Point/Box/Boundary) is the interactive single-slice segmenter.

const MAX_UNDO = 20;
const LABEL_ALPHA = 150;
// Proposed-mask look, matching Cellable's AI preview (canvas.py paintEvent):
// green translucent fill (their `select_fill_color` + a temporary
// `label_opacity=0.5`) plus an opaque white contour (`select_line_color`,
// traced by `strokeMaskContour` above) — not the flat amber blob this used
// to be (progress/history/25-cellable-proposed-mask-fluency.md item A).
const AI_PREVIEW_FILL_ALPHA = 130; // ~0.5 of 255, same intent as Cellable's label_opacity
const AI_PREVIEW_CONTOUR_COLOR = "#ffffff";
const MIN_ZOOM = 0.8;
const MAX_ZOOM = 8;
const clampZoom = (z: number) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
/** Wheel zoom step — milder than Cellable's 1.1^(δ/120) so trackpads feel smooth. */
const WHEEL_ZOOM_BASE = 1.045;
/** +/- button step (~8% per click). */
const BUTTON_ZOOM_FACTOR = 1.08;
const SIDE_PANEL_DEFAULT = 320;
const SIDE_PANEL_MIN = 180;
const SIDE_PANEL_MAX = 520;
const SIDE_RAIL_W = 14;
const clampSidePanel = (w: number) =>
  Math.max(SIDE_PANEL_MIN, Math.min(SIDE_PANEL_MAX, Math.round(w)));

/** True-run RLE ([start, length] of contiguous truthy pixels) — the shape the
 * tracking endpoint expects for seed masks, distinct from the label-id RLE. */
function trueRunsRLE(mask: Uint8Array): [number, number][] {
  const runs: [number, number][] = [];
  let i = 0;
  while (i < mask.length) {
    if (mask[i]) {
      const start = i;
      while (i < mask.length && mask[i]) i++;
      runs.push([start, i - start]);
    } else {
      i++;
    }
  }
  return runs;
}

/** Unique nonzero instance ids present in a flat id array, sorted ascending. */
function uniqueInstances(ids: Int32Array): number[] {
  const set = new Set<number>();
  for (let i = 0; i < ids.length; i++) {
    const v = ids[i];
    if (v > 0) set.add(v);
  }
  return Array.from(set).sort((a, b) => a - b);
}

/** Cellable ports `skimage.measure.find_contours` (shape.py `_mask_outline_path`)
 * for a smooth sub-pixel iso-contour. This instead traces the exact pixel-grid
 * boundary (every edge between a mask=1 cell and a mask=0/out-of-bounds
 * neighbor) — same visual result (a crisp outline hugging the mask), avoids
 * marching-squares' saddle-point ambiguity, and is O(h*w) like the fill loop
 * it runs alongside. */
function strokeMaskContour(
  ctx: CanvasRenderingContext2D,
  mask: Uint8Array,
  h: number,
  w: number,
  lineWidth: number,
  color: string,
) {
  const at = (y: number, x: number) => (y < 0 || y >= h || x < 0 || x >= w ? 0 : mask[y * w + x]);
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      if (!mask[row + x]) continue;
      if (!at(y - 1, x)) {
        ctx.moveTo(x, y);
        ctx.lineTo(x + 1, y);
      }
      if (!at(y + 1, x)) {
        ctx.moveTo(x, y + 1);
        ctx.lineTo(x + 1, y + 1);
      }
      if (!at(y, x - 1)) {
        ctx.moveTo(x, y);
        ctx.lineTo(x, y + 1);
      }
      if (!at(y, x + 1)) {
        ctx.moveTo(x + 1, y);
        ctx.lineTo(x + 1, y + 1);
      }
    }
  }
  ctx.stroke();
  ctx.restore();
}

interface AiPoint {
  x: number;
  y: number;
  label: 0 | 1;
}

interface AiPreview {
  mask: Uint8Array; // 0/1, flat h*w
  shape: [number, number];
}

interface BoxDrag {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

interface WsSeed {
  z: number;
  y: number;
  x: number;
  label: number;
}

export default function AnnotationCanvas({
  taskId,
  volumeId,
  zStart,
  zEnd,
  editable = true,
}: {
  taskId: number;
  volumeId: number;
  zStart: number;
  zEnd: number;
  /** Annotate mounts tool strip / Track / Labels; View shares this canvas without them. */
  editable?: boolean;
}) {
  const meta = useAsync<VolumeMeta>(() => getVolumeMeta(volumeId), [volumeId]);
  const labelState = useAsync(() => getLabelState(taskId), [taskId]);

  const [index, setIndex] = useState(zStart);
  // Default Annotate mode is Select (V) — not Brush/Point Mask — so opening
  // a task never starts mid-AI-prompt or mid-stroke.
  const [paintTool, setPaintTool] = useState<PaintTool>("select");
  const [brushSize, setBrushSize] = useState(6);
  const [eraserSize, setEraserSize] = useState(6);
  const [activeId, setActiveId] = useState(1);
  const [brightness, setBrightness] = useState(50);
  const [contrast, setContrast] = useState(50);
  // Global committed-label opacity (0-100, Cellable's `label_opacity_slider`
  // — default 100 = fully opaque, matching Cellable's own default) — #29
  // item U5. Affects committed overlay alpha only; the AI proposal fill
  // stays at its own fixed ~0.5 regardless (#26 look, not user-tunable).
  const [labelOpacity, setLabelOpacity] = useState(100);
  const [zoom, setZoom] = useState(1);
  const [fitMode, setFitMode] = useState<"window" | "width">("window");
  const [status, setStatus] = useState<"idle" | "dirty" | "saving" | "saved" | "error">("idle");
  const [sliceLoading, setSliceLoading] = useState(true);
  // Edits stay local until Save — Cellable's dirty flag. Without Save, the
  // on-disk mask under data/ is unchanged.
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [instances, setInstances] = useState<number[]>([]);
  const [hiddenIds, setHiddenIds] = useState<Set<number>>(new Set());
  const [soloId, setSoloId] = useState<number | null>(null);
  const [undoCount, setUndoCount] = useState(0);
  const [redoCount, setRedoCount] = useState(0);

  // Point Mask / Box Mask / Boundary — accumulated prompt points + the
  // predicted preview mask, awaiting an explicit Commit (so a bad/slow
  // prediction never silently flattens into the raster before the user
  // sees it — Cellable's Shape stayed editable/undo-able until then too).
  // `aiLoading` drives a small busy indicator (#29 item U13) — only click/
  // box predicts ever set it (see `runPredictPointsWith`'s `silent` option),
  // never the live cursor-follow hover predicts, so it doesn't flicker on
  // every mouse move.
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [hasAiPreview, setHasAiPreview] = useState(false);
  const [aiPointCount, setAiPointCount] = useState(0);

  // Seeds (3D watershed) — persists across slice navigation on purpose
  // (seeds can span several z's before "Run Watershed", like Cellable's
  // watershed_3d mode).
  const [wsSeeds, setWsSeeds] = useState<WsSeed[]>([]);
  const [wsTargetLabel, setWsTargetLabel] = useState<number | null>(null);
  const [wsRunning, setWsRunning] = useState(false);
  const [wsMessage, setWsMessage] = useState<string | null>(null);

  // Track (SAM2) — propagates the active instance's current-slice shape
  // across a z-range via fork-aware SAM2. Not a paint mode: always visible,
  // always uses whatever the active instance currently looks like on this
  // slice (painted by hand, AI-masked, or already-tracked — doesn't matter).
  const [trackZFrom, setTrackZFrom] = useState(zStart);
  const [trackZTo, setTrackZTo] = useState(Math.max(zStart, zEnd - 1));
  const [tracking, setTracking] = useState(false);
  const [trackError, setTrackError] = useState<string | null>(null);

  // Minimal right-click context menu (#29 item U15) — screen position to
  // place it at, plus the label id under the cursor (if any) so Verify/Solo
  // only show up when right-clicking an actual label.
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; labelId: number | null } | null>(null);

  // Swap 3D ↔ Canvas (#31 item 5) — swapped = the 3D Labels view fills the
  // large center pane and the 2D canvas shrinks into the small dock slot,
  // view-only (no paint/AI/box/seed — see `onPointerDown`'s `swapped` guard
  // below). `pinned3D`/`activeId` (and therefore `label3DIds`) are untouched
  // by this toggle, so the 3D selection survives swapping either direction.
  const [swapped, setSwapped] = useState(false);
  // Excel-style side docks: drag to resize; collapse to a thin reopen strip.
  const [leftPanelW, setLeftPanelW] = useState(SIDE_PANEL_DEFAULT);
  const [rightPanelW, setRightPanelW] = useState(SIDE_PANEL_DEFAULT);
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);

  // Zoom uses layout size + cursor/center anchoring. While Cmd/Ctrl is held,
  // native scroll is locked so the wheel only zooms (never pans or changes z).

  // Labels panel: whole-volume lifecycle summary (state/origin per id,
  // shared with 2D "Hide Verified" rendering) + 3D panel pinned ids.
  const [labelsSummaryRows, setLabelsSummaryRows] = useState<LabelSummaryRow[]>([]);
  const [labelsSummaryLoading, setLabelsSummaryLoading] = useState(false);
  // Default OFF so all labels are visible on open (Hide Verified is an
  // opt-in filter, sitting beside Filters Options — not buried inside it).
  const [hideVerified, setHideVerified] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [pinned3D, setPinned3D] = useState<Set<number>>(new Set());
  const [labelsRefreshToken, setLabelsRefreshToken] = useState(0);

  const imgRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  /** Non-scrolling shell — fit size is measured here so scrollbar gutters
   * inside the viewport cannot change the fit base mid-zoom. */
  const shellRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  /** Fit baseline (zoom=1 size + pad). Frozen across zoom — only Fit / open / real shell resize recomputes it. */
  const fitBaseRef = useRef<{ w: number; h: number; padX: number; padY: number }>({
    w: 0,
    h: 0,
    padX: 0,
    padY: 0,
  });
  const lastShellRef = useRef({ w: 0, h: 0 });
  /** Keep image point under the cursor/center stable across a zoom step. */
  const zoomAnchorRef = useRef<{
    offsetX: number;
    offsetY: number;
    localX: number;
    localY: number;
    oldW: number;
  } | null>(null);
  /** While Cmd/Ctrl is held, pin scroll here so the wheel cannot pan. */
  const cmdScrollLockRef = useRef<{ left: number; top: number } | null>(null);
  const stageLayoutRef = useRef<{
    stageW: number;
    stageH: number;
    contentW: number;
    contentH: number;
    stageLeft: number;
    stageTop: number;
  } | null>(null);
  /** Pending Fit window / Fit width — applied after the next stage layout. */
  const pendingFitRef = useRef<"window" | "width" | null>(null);
  /**
   * Center once on page entry. Stays true across early shell resizes (Annotate
   * side rails settling) so we don't lock scroll before the final canvas size.
   * Cleared after a stable center, or as soon as the user zooms/pans/Fits.
   */
  const needsOpenCenterRef = useRef(true);

  // View ↔ Annotate remounts usually, but if `editable` flips in place, re-run
  // the one-shot open center for the new chrome width.
  useEffect(() => {
    needsOpenCenterRef.current = true;
    fitBaseRef.current = { w: 0, h: 0, padX: 0, padY: 0 };
    lastShellRef.current = { w: 0, h: 0 };
    setFitEpoch((e) => e + 1);
  }, [editable]);
  /** Bumped on every Fit click so re-fitting at zoom=1 / same mode still relayouts. */
  const [fitEpoch, setFitEpoch] = useState(0);
  const [stageLayout, setStageLayout] = useState<{
    stageW: number;
    stageH: number;
    contentW: number;
    contentH: number;
    stageLeft: number;
    stageTop: number;
  } | null>(null);
  stageLayoutRef.current = stageLayout;
  const idsRef = useRef<Int32Array | null>(null); // current slice, flat h*w
  const shapeRef = useRef<[number, number]>([0, 0]); // [h, w]
  const imageDataRef = useRef<ImageData | null>(null); // reused across renders to avoid per-stroke allocation
  const undoStack = useRef<Int32Array[]>([]);
  const redoStack = useRef<Int32Array[]>([]);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<[number, number] | null>(null);
  const nextIdRef = useRef(1);
  const aiPointsRef = useRef<AiPoint[]>([]);
  const aiPreviewRef = useRef<AiPreview | null>(null);
  const boxDragRef = useRef<BoxDrag | null>(null);
  // Last hovered image-space pixel (null when the pointer is off-canvas) —
  // drives the box/box-erase crosshair (#25 item D) and the brush/erase
  // size cursor (#25 item G), both redrawn via the cheap `renderCursorOverlay`
  // path below rather than the full per-pixel label recompute.
  const hoverPosRef = useRef<[number, number] | null>(null);
  // The Point Mask/Boundary transient cursor tip (#27) — Cellable's `line`
  // rubber-band tip: null until ≥1 point is committed (no preview at all
  // before the first click, matching Cellable's `if not self.current:
  // return`), then tracks the cursor with label flipped by Shift on every
  // move. Not in `aiPointsRef` — it's never committed until a click/Ctrl-
  // click/Enter promotes it.
  const aiTipRef = useRef<AiPoint | null>(null);
  // Cursor-follow live predict (#27), coalesced over HTTP (#28/#29) — an
  // earlier version aborted the in-flight predict on every pointer move
  // (Cellable's own "predict on every repaint" is an in-process call, not a
  // network round trip); that left the green mask visibly frozen, since the
  // constantly-superseded request never got a chance to land. Coalescing
  // instead: at most one predict in flight at a time, `dirty` marks that a
  // newer tip arrived while it was running, and the `finally` below fires
  // exactly one follow-up request for the latest position once the current
  // one finishes — never a queue, never an abort-storm. Both live and
  // committed-only predicts still share the single `aiSeqRef`/`aiAbortRef`
  // guard above, so a click can never be overwritten by a stale hover
  // response or vice versa.
  const livePredictRef = useRef<{ inFlight: boolean; dirty: boolean }>({
    inFlight: false,
    dirty: false,
  });
  // `runPredictPointsWith` chains its own follow-up call from inside its
  // `finally` block (see `livePredictRef.dirty` above) — going through a ref
  // instead of calling itself by name sidesteps a stale-closure trap: a
  // `useCallback`'s own body captures the closure that existed when *that*
  // instance was created, but a ref is always read fresh, so a chained call
  // always dispatches through whichever version of the function is current.
  const runPredictPointsWithRef = useRef<(pts: AiPoint[], opts?: { silent?: boolean; live?: boolean }) => Promise<void>>(
    async () => undefined,
  );
  // Which committed prompt point (index into `aiPointsRef`) is being
  // dragged, if any (#29 item U8) — `null` when not dragging. A separate
  // ref from `drawingRef` on purpose: `drawingRef` drives the generic
  // brush-stroke/box-drag commit path in `onPointerUp`, and a dragged AI
  // prompt point must never fall into that path (it doesn't touch `idsRef`
  // at all, so there's nothing to `commit()` to the server).
  const draggingPointIdxRef = useRef<number | null>(null);
  // Offscreen canvas holding the *undisplayed* (no CSS brightness/contrast
  // filter) intensity image for the current slice — repopulated whenever
  // the `<img>` finishes loading a new slice (its `onLoad`). Lets the
  // status readout (#29 item U3) read a per-pixel intensity value via
  // `getImageData` without re-fetching or re-decoding anything.
  const intensityCtxRef = useRef<CanvasRenderingContext2D | null>(null);
  // Direct DOM write for the status readout — updated on every pointer move
  // over the canvas, which is far too high-frequency to route through React
  // state (same reasoning as the overlay canvas itself: see `renderOverlay`/
  // `renderCursorOverlay` above).
  const statusReadoutRef = useRef<HTMLSpanElement | null>(null);
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const prevPaintToolRef = useRef<PaintTool>("select");
  // Guards a rapid click/re-box from letting an older, slower predict
  // response overwrite a newer one (Cellable: "keep last-good preview
  // until the newer one arrives") — each predict call captures the
  // post-increment sequence number and checks it's still current before
  // applying its result; a superseded call's abort() also drops the
  // network request itself. `committingAiRef` is a second, narrower guard
  // against a double Enter/click re-entering `commitAiPreview` mid-flight
  // (Cellable's `_finaliseInProgress`).
  const aiSeqRef = useRef(0);
  const aiAbortRef = useRef<AbortController | null>(null);
  const committingAiRef = useRef(false);

  useEffect(() => {
    if (labelState.data) {
      nextIdRef.current = labelState.data.next_label_id;
      setActiveId(labelState.data.next_label_id);
    }
  }, [labelState.data]);

  const axisLen = meta.data?.shape.z ?? 1;

  const refreshLabelsSummary = useCallback(() => {
    setLabelsSummaryLoading(true);
    getLabelsSummary(taskId)
      .then((res) => setLabelsSummaryRows(res.labels))
      .finally(() => setLabelsSummaryLoading(false));
  }, [taskId]);

  useEffect(() => {
    refreshLabelsSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshLabelsSummary, labelsRefreshToken]);

  // Cellable's "Hide Verified" checkbox hides VERIFIED labels from the
  // 2D (and 3D) views, not just the Labels list — needs the whole-volume
  // state summary above, not just what's decoded on this slice.
  const verifiedIds = useMemo(
    () => new Set(labelsSummaryRows.filter((r) => r.state === "verified").map((r) => r.id)),
    [labelsSummaryRows],
  );

  // Heavy pass: recompute the per-pixel label/preview fill (labels + the
  // green AI-preview fill) and blit it. Only needed when that fill actually
  // changed (ids, preview mask, visibility, active id, ...) — reuses the
  // same ImageData/backing buffer across calls (cuts GC churn to zero for
  // the common case of painting on a slice whose dimensions haven't
  // changed since the last frame).
  const computeBaseImage = useCallback(() => {
    const canvas = overlayRef.current;
    const ids = idsRef.current;
    const [h, w] = shapeRef.current;
    if (!canvas || !ids || h === 0 || w === 0) return null;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    let image = imageDataRef.current;
    if (!image || image.width !== w || image.height !== h) {
      image = ctx.createImageData(w, h);
      imageDataRef.current = image;
    }
    const showAiPreview = AI_PREVIEW_TOOLS.includes(paintTool);
    const preview = showAiPreview ? aiPreviewRef.current : null;
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const o = i * 4;
      if (preview && preview.mask[i]) {
        // Proposed mask = green translucent fill (Cellable's
        // select_fill_color + preview label_opacity≈0.5); the opaque white
        // contour is a vector overlay drawn on top, see drawVectorOverlay.
        image.data[o] = 0;
        image.data[o + 1] = 255;
        image.data[o + 2] = 0;
        image.data[o + 3] = AI_PREVIEW_FILL_ALPHA;
        continue;
      }
      const suppressed =
        id <= 0 ||
        (soloId != null ? id !== soloId : hiddenIds.has(id)) ||
        (hideVerified && verifiedIds.has(id));
      if (suppressed) {
        image.data[o + 3] = 0;
        continue;
      }
      const [r, g, b] = labelColor(id);
      image.data[o] = r;
      image.data[o + 1] = g;
      image.data[o + 2] = b;
      // Global committed-label opacity (#29 item U5, Cellable's
      // `label_opacity_slider`) — scales the committed alpha only; the AI
      // proposal fill above is intentionally untouched by it.
      image.data[o + 3] = Math.round((id === activeId ? 220 : LABEL_ALPHA) * (labelOpacity / 100));
    }
    ctx.putImageData(image, 0, 0);
    return { ctx, canvas, w, h };
  }, [activeId, hiddenIds, soloId, hideVerified, verifiedIds, paintTool, labelOpacity]);

  // Vector overlays on top of whatever fill is already blitted — proper
  // alpha compositing (unlike a second putImageData, which would replace
  // rather than blend). Sized in **screen space**, not image space —
  // Cellable's `shape.py` draws vertices/pen strokes at a constant
  // on-screen size regardless of zoom (`point_size≈8`, `PEN_WIDTH≈2`); a
  // fixed image-space radius would shrink to sub-pixel on a large EM slice
  // at fit-window. `scale` here is the *actual* rendered-CSS-pixels-per-
  // image-pixel ratio (folds in both the explicit zoom control *and* the
  // fit-window/fit-width auto-scaling, which `zoom` alone doesn't capture),
  // measured fresh every repaint via the canvas's real layout box.
  //
  // Deliberately callable on its own (see `renderCursorOverlay` below) so
  // high-frequency pointer moves (box crosshair, brush/erase size cursor)
  // never have to pay for `computeBaseImage`'s O(h*w) label recompute —
  // they just re-blit the cached ImageData and redraw these vectors.
  const drawVectorOverlay = useCallback(
    (ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, w: number, h: number) => {
      const screenRect = canvas.getBoundingClientRect();
      const scale = screenRect.width > 0 ? screenRect.width / w : 1;
      const toImagePx = (screenPx: number) => screenPx / Math.max(scale, 0.001);
      const pointRadius = toImagePx(4); // ~8px on-screen diameter
      const penWidth = Math.max(toImagePx(2), 0.5);

      // Proposed-mask contour: opaque white outline of the AI preview,
      // Cellable's `select_line_color` (shape.py `_mask_outline_path`).
      const preview = AI_PREVIEW_TOOLS.includes(paintTool) ? aiPreviewRef.current : null;
      if (preview) {
        strokeMaskContour(ctx, preview.mask, h, w, Math.max(toImagePx(2.5), 0.5), AI_PREVIEW_CONTOUR_COLOR);
      }

      if (AI_POINT_TOOLS.includes(paintTool)) {
        // Rubber-band: a thin line from the last committed point to the
        // cursor tip, redrawn every move (#29 item U1 — Cellable's `self.line`
        // in `mouseMoveEvent`/`paintEvent`). Colored by the tip's own label so
        // a Shift-held negative tip reads as red the same way its dot does.
        const lastCommitted = aiPointsRef.current[aiPointsRef.current.length - 1];
        const tip = aiTipRef.current;
        if (lastCommitted && tip) {
          ctx.beginPath();
          ctx.moveTo(lastCommitted.x, lastCommitted.y);
          ctx.lineTo(tip.x, tip.y);
          ctx.strokeStyle = tip.label === 1 ? "#22c55e" : "#ef4444";
          ctx.lineWidth = Math.max(toImagePx(1.5), 0.5);
          ctx.stroke();
        }
        // Committed points, then the transient cursor tip (#27) — same
        // vertex style for both (Cellable's `line` tip is itself a `Shape`
        // painted identically to the committed points, not visually
        // distinguished) so the "pixel-identical feel" the user asked for
        // isn't undercut by mito inventing its own look for the tip.
        const pts = tip ? [...aiPointsRef.current, tip] : aiPointsRef.current;
        for (const p of pts) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, pointRadius, 0, Math.PI * 2);
          // Positive: bright green fill. Negative: solid red — both with a
          // dark contrasting stroke so they stay legible over any tissue
          // color/brightness, matching Cellable's "obvious, not just tinted."
          ctx.fillStyle = p.label === 1 ? "#22c55e" : "#ef4444";
          ctx.fill();
          ctx.lineWidth = penWidth * 0.6;
          ctx.strokeStyle = p.label === 1 ? "#052e12" : "#450a0a";
          ctx.stroke();
        }
      }
      if (paintTool === "box_mask" || paintTool === "box_eraser") {
        const box = boxDragRef.current;
        if (box) {
          const bx = Math.min(box.x0, box.x1);
          const by = Math.min(box.y0, box.y1);
          const bw = Math.abs(box.x1 - box.x0);
          const bh = Math.abs(box.y1 - box.y0);
          const color = paintTool === "box_mask" ? "#f59e0b" : "#38bdf8";
          ctx.strokeStyle = color;
          ctx.lineWidth = penWidth;
          ctx.strokeRect(bx, by, bw, bh);
          // Corner handles — a thin rectangle outline reads as "maybe
          // decorative" at a glance; filled corner squares are what actually
          // reads as "an active rubber-band selection" (Cellable's vertex
          // handles serve the same purpose).
          const hs = toImagePx(5);
          ctx.fillStyle = color;
          for (const [cx, cy] of [
            [bx, by],
            [bx + bw, by],
            [bx, by + bh],
            [bx + bw, by + bh],
          ] as const) {
            ctx.fillRect(cx - hs, cy - hs, hs * 2, hs * 2);
          }
        }
        // Full-image axis-aligned crosshair while box_mask/box_eraser is
        // active, Cellable-style (canvas.py's `_crosshair` — enabled for
        // its `rectangle`/`erase` modes) — not just a CSS `cursor:
        // crosshair`, which disappears the instant the pointer leaves the
        // browser's hit-test for the cursor icon (#25 item D).
        const hover = hoverPosRef.current;
        if (hover) {
          const [hy, hx] = hover;
          ctx.strokeStyle = "#22c55e";
          ctx.lineWidth = Math.max(toImagePx(1), 0.5);
          ctx.beginPath();
          ctx.moveTo(0, hy);
          ctx.lineTo(w, hy);
          ctx.moveTo(hx, 0);
          ctx.lineTo(hx, h);
          ctx.stroke();
        }
      }
      if (paintTool === "brush" || paintTool === "eraser") {
        // Live brush/erase size cursor — a circle at the stamp radius
        // (image-space, so it matches the actual paint/erase footprint),
        // screen-visible stroke (#25 item G).
        const hover = hoverPosRef.current;
        if (hover) {
          const [hy, hx] = hover;
          ctx.strokeStyle = paintTool === "brush" ? "#22c55e" : "#38bdf8";
          ctx.lineWidth = Math.max(toImagePx(1.5), 0.5);
          ctx.beginPath();
          ctx.arc(hx, hy, paintTool === "brush" ? brushSize : eraserSize, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      if (paintTool === "seeds") {
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = penWidth;
        const arm = toImagePx(7);
        for (const s of wsSeeds) {
          if (s.z !== index) continue;
          ctx.beginPath();
          ctx.moveTo(s.x - arm, s.y);
          ctx.lineTo(s.x + arm, s.y);
          ctx.moveTo(s.x, s.y - arm);
          ctx.lineTo(s.x, s.y + arm);
          ctx.stroke();
        }
      }
    },
    [paintTool, wsSeeds, index, brushSize, eraserSize],
  );

  const renderOverlay = useCallback(() => {
    const base = computeBaseImage();
    if (!base) return;
    drawVectorOverlay(base.ctx, base.canvas, base.w, base.h);
    // zoom/fitMode aren't read directly in this body, but a zoom/fit change
    // alters the canvas's on-screen size, which changes `scale` inside
    // drawVectorOverlay's toImagePx — including them here forces this
    // callback to change identity so the `useEffect(renderOverlay)` below
    // re-fires and point/contour/crosshair sizing stays screen-constant
    // instead of stale from before the resize.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [computeBaseImage, drawVectorOverlay, zoom, fitMode]);

  // Cheap pass for high-frequency pointer moves: re-blit the cached fill
  // (no O(h*w) label recompute) and redraw only the vectors. Used for box
  // rubber-band dragging and hover-only cursor feedback (crosshair, brush
  // size circle) so scrubbing the mouse around never re-touches the label
  // loop unless the underlying ids/preview actually changed.
  const renderCursorOverlay = useCallback(() => {
    const canvas = overlayRef.current;
    const image = imageDataRef.current;
    const [h, w] = shapeRef.current;
    if (!canvas || !image || h === 0 || w === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.putImageData(image, 0, 0);
    drawVectorOverlay(ctx, canvas, w, h);
  }, [drawVectorOverlay]);

  const refreshInstances = useCallback(() => {
    const ids = idsRef.current;
    setInstances(ids ? uniqueInstances(ids) : []);
  }, []);

  // undoStack/redoStack are refs (mutated imperatively so painting doesn't
  // trigger a re-render on every stroke) — call after any mutation so the
  // Undo/Redo buttons' enabled state actually reflects them.
  const syncHistoryCounts = useCallback(() => {
    setUndoCount(undoStack.current.length);
    setRedoCount(redoStack.current.length);
  }, []);

  const loadSlice = useCallback(
    async (i: number, signal?: AbortSignal) => {
      if (!meta.data) return;
      setSliceLoading(true);
      try {
        const [imgUrl, resp] = await Promise.all([
          fetchObjectUrl(imageSlicePath(volumeId, { axis: "z", index: i }), signal),
          getLabelIds(taskId, "z", i),
        ]);
        if (imgRef.current) imgRef.current.src = imgUrl;
        const [h, w] = resp.shape;
        shapeRef.current = [h, w];
        idsRef.current = decodeRuns(resp.runs, h * w);
        undoStack.current = [];
        redoStack.current = [];
        // AI prompt points/preview are slice-specific (the underlying image
        // embedding is per-slice) — discard them on navigation, same as
        // Cellable resets `currentAIPromptPoints` on slice change.
        aiPointsRef.current = [];
        aiPreviewRef.current = null;
        aiTipRef.current = null;
        livePredictRef.current = { inFlight: false, dirty: false };
        draggingPointIdxRef.current = null;
        setHasAiPreview(false);
        setAiPointCount(0);
        setAiError(null);
        boxDragRef.current = null;
        setStatus("idle");
        setTrackError(null);
        dirtyRef.current = false;
        setDirty(false);
        renderOverlay();
        refreshInstances();
        syncHistoryCounts();
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) throw e;
      } finally {
        setSliceLoading(false);
      }
    },
    [meta.data, volumeId, taskId, renderOverlay, refreshInstances, syncHistoryCounts],
  );

  // Debounced (~100ms, Cellable's `_sliceLoadTimer` idea — see
  // progress/history/23-cellable-parity-ort-and-prompt-ux.md) + a fresh
  // AbortController per attempt, cancelled the moment a newer index
  // supersedes it (or the component unmounts). Holding A/D or dragging the
  // slider fast used to fire one slice+label fetch per intermediate index;
  // now only the index the user actually settles on triggers a fetch.
  // `loadSlice` itself only swaps `imgRef`/`idsRef` once its fetch
  // resolves, so the previous slice's image+overlay stay visible the whole
  // time — no blank flash while debounced or in flight. Brush/erase strokes
  // never go through this path at all (they mutate `idsRef` directly and
  // commit on pointer-up), so painting itself is never debounced.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      loadSlice(index, controller.signal);
    }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, meta.data]);

  // Warm the EfficientSAM embedding (encoder-only, see
  // `services.warm_ai_embedding`) whenever the slice settles while an AI
  // tool is active, *or* when switching into one on the current slice —
  // fire-and-forget, same ~100ms coalescing as the slice load above so
  // scrubbing quickly doesn't fire a warm request per intermediate index.
  // Also opportunistically warms the two neighboring slices (Cellable's
  // `pre_compute_tiff_sam_feature.py` background-fills nearby slices too) —
  // best-effort only, failures ignored, aborted the same way on cleanup.
  useEffect(() => {
    if (!AI_PREVIEW_TOOLS.includes(paintTool) || !meta.data) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      warmEmbedding(taskId, "z", index, controller.signal).catch(() => {});
      if (index > 0) warmEmbedding(taskId, "z", index - 1, controller.signal).catch(() => {});
      if (index < axisLen - 1) warmEmbedding(taskId, "z", index + 1, controller.signal).catch(() => {});
    }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [taskId, index, paintTool, axisLen, meta.data]);

  useEffect(() => {
    renderOverlay();
  }, [renderOverlay]);

  const markDirty = useCallback(() => {
    dirtyRef.current = true;
    setDirty(true);
    setStatus("dirty");
  }, []);

  const saveLabels = useCallback(
    async (origin: "manual" | "ai" = "manual") => {
      const ids = idsRef.current;
      const [h, w] = shapeRef.current;
      if (!ids) return;
      setStatus("saving");
      try {
        const runs = encodeRuns(ids as unknown as Uint32Array);
        const res = await putLabelIds(taskId, "z", index, [h, w], runs, origin);
        nextIdRef.current = res.next_label_id;
        dirtyRef.current = false;
        setDirty(false);
        setStatus("saved");
        refreshInstances();
        setLabelsRefreshToken((v) => v + 1);
      } catch {
        setStatus("error");
      }
    },
    [taskId, index, refreshInstances],
  );

  /** Navigate to another slice; discard unsaved local edits after confirm. */
  const requestIndex = useCallback((next: number) => {
    const clamped = Math.max(0, Math.min(axisLen - 1, next));
    if (clamped === index) return;
    if (dirtyRef.current) {
      if (!window.confirm("Discard unsaved changes on this slice? Click Save first to keep them.")) {
        return;
      }
      dirtyRef.current = false;
      setDirty(false);
    }
    setIndex(clamped);
  }, [axisLen, index]);

  // Widened past `React.PointerEvent` (structurally: any event with
  // clientX/clientY) so the same conversion serves pointer moves/clicks
  // *and* the right-click context menu (#29 item U15), which fires a
  // `React.MouseEvent`.
  const pixelFromEvent = useCallback((e: { clientX: number; clientY: number }): [number, number] | null => {
    const canvas = overlayRef.current;
    const [h, w] = shapeRef.current;
    if (!canvas || h === 0 || w === 0) return null;
    const rect = canvas.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
    return [Math.floor(ny * h), Math.floor(nx * w)];
  }, []);

  // Index into `aiPointsRef` of the committed point nearest an image-space
  // click, if any is within `toleranceScreenPx` on-screen pixels — shared by
  // Alt+click-to-remove (#25 item E) and drag-to-move (#29 item U8) so both
  // "clicked on an existing point" checks use the exact same hit-test.
  const nearestCommittedPointIndex = useCallback((px: number, py: number, toleranceScreenPx: number): number => {
    const pts = aiPointsRef.current;
    if (pts.length === 0) return -1;
    const canvas = overlayRef.current;
    const [, w] = shapeRef.current;
    const rect = canvas?.getBoundingClientRect();
    const scale = rect && rect.width > 0 ? rect.width / w : 1;
    const tolerance = toleranceScreenPx / Math.max(scale, 0.001);
    let nearestIdx = -1;
    let nearestDist = Infinity;
    pts.forEach((p, i) => {
      const d = Math.hypot(p.x - px, p.y - py);
      if (d < nearestDist) {
        nearestDist = d;
        nearestIdx = i;
      }
    });
    return nearestIdx >= 0 && nearestDist <= tolerance ? nearestIdx : -1;
  }, []);

  const paintAt = useCallback(
    (py: number, px: number, value: number, target: Int32Array, radius: number) => {
      const [h, w] = shapeRef.current;
      const y0 = Math.max(0, py - radius);
      const y1 = Math.min(h - 1, py + radius);
      const x0 = Math.max(0, px - radius);
      const x1 = Math.min(w - 1, px + radius);
      const r2 = radius * radius;
      for (let y = y0; y <= y1; y++) {
        const dy = y - py;
        for (let x = x0; x <= x1; x++) {
          const dx = x - px;
          if (dx * dx + dy * dy <= r2) target[y * w + x] = value;
        }
      }
    },
    [],
  );

  const strokeTo = useCallback(
    (py: number, px: number) => {
      const ids = idsRef.current;
      const last = lastPointRef.current;
      const steps = last ? Math.max(1, Math.ceil(Math.hypot(py - last[0], px - last[1]))) : 1;
      if (ids) {
        for (let s = 0; s <= steps; s++) {
          const t = steps === 0 ? 1 : s / steps;
          const y = last ? Math.round(last[0] + (py - last[0]) * t) : py;
          const x = last ? Math.round(last[1] + (px - last[1]) * t) : px;
          if (paintTool === "brush") paintAt(y, x, activeId, ids, brushSize);
          else if (paintTool === "eraser") paintAt(y, x, 0, ids, eraserSize);
        }
      }
      lastPointRef.current = [py, px];
      renderOverlay();
    },
    [paintTool, activeId, brushSize, eraserSize, paintAt, renderOverlay],
  );

  // --- Point Mask / Boundary: accumulate prompt points, live-predict ------
  //
  // Every predict call is sequence-guarded: a rapid extra click (or a new
  // box drag) starts a new sequence number and aborts whatever was still
  // in flight, and any response — success, failure, or an aborted-request
  // exception — is only applied if its sequence number is still current.
  // This is what keeps overlapping predicts from corrupting each other
  // (Cellable's own predicts are effectively serialized by the Qt event
  // loop calling `_finaliseImpl`/paintEvent one at a time; a browser has no
  // such guarantee once two `fetch`es are in flight together).

  // Shared core: predict from an explicit point set. Used two ways —
  // committed-only (`runPredictPoints`, the click/Alt-click/finalize path)
  // and committed∪{live cursor tip} (`scheduleLivePredict`, #27's
  // cursor-follow). Both share one `aiSeqRef`/`aiAbortRef` pair so whichever
  // call is most recent always wins regardless of which path fired it —
  // a click predict racing a hover predict can't corrupt either's result.
  const runPredictPointsWith = useCallback(
    async (pts: AiPoint[], opts?: { silent?: boolean; live?: boolean }) => {
      const silent = opts?.silent === true;
      const live = opts?.live === true;
      // Click/finalize always cancel whatever was in flight. Live coalesced
      // predicts do not abort each other — that was why the mask felt frozen
      // (every move killed the in-flight request; only a stale last-good fill
      // remained on screen).
      if (!live) {
        aiAbortRef.current?.abort();
        livePredictRef.current = { inFlight: false, dirty: false };
      }
      if (pts.length === 0) {
        aiPreviewRef.current = null;
        setHasAiPreview(false);
        renderOverlay();
        return;
      }
      const controller = new AbortController();
      if (!live) aiAbortRef.current = controller;
      const seq = ++aiSeqRef.current;
      const points: [number, number][] = pts.map((p) => [p.x, p.y]);
      const pointLabels = pts.map((p) => p.label);
      if (!silent) {
        setAiLoading(true);
        setAiError(null);
      }
      try {
        const res =
          paintTool === "boundary"
            ? await predictBoundary(taskId, "z", index, points, pointLabels, live ? undefined : controller.signal)
            : await predictMaskFromPoints(taskId, "z", index, points, pointLabels, live ? undefined : controller.signal);
        if (aiSeqRef.current !== seq && !live) return;
        // Live path: apply if this is still the latest live seq OR no newer
        // click bumped the counter past us mid-flight.
        if (live && aiSeqRef.current !== seq) {
          // A click/clear happened — discard.
          return;
        }
        const [h, w] = res.shape;
        const mask = decodeRuns(res.runs, h * w);
        if (!mask.some((v) => v !== 0)) {
          if (!live) {
            aiPreviewRef.current = null;
            setHasAiPreview(false);
            setAiError("No mask found for these points — try adding another point.");
          }
          return;
        }
        aiPreviewRef.current = { mask: Uint8Array.from(mask), shape: [h, w] };
        setHasAiPreview(true);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (aiSeqRef.current !== seq) return;
        if (!silent) setAiError(e instanceof Error ? e.message : "Prediction failed");
      } finally {
        if (!silent && aiSeqRef.current === seq) setAiLoading(false);
        renderOverlay();
        if (live) {
          const st = livePredictRef.current;
          st.inFlight = false;
          if (st.dirty) {
            st.dirty = false;
            const committed = aiPointsRef.current;
            if (committed.length > 0) {
              const tip = aiTipRef.current;
              st.inFlight = true;
              void runPredictPointsWithRef.current(tip ? [...committed, tip] : committed, {
                silent: true,
                live: true,
              });
            }
          }
        }
      }
    },
    [taskId, index, paintTool, renderOverlay],
  );
  runPredictPointsWithRef.current = runPredictPointsWith;

  // Committed-only predict (no cursor tip) — click / Alt-click / Enter path.
  const runPredictPoints = useCallback(
    () => runPredictPointsWith(aiPointsRef.current),
    [runPredictPointsWith],
  );

  // Cursor-follow: coalesce to latest tip (Cellable paintEvent feel over HTTP).
  const scheduleLivePredict = useCallback(() => {
    const pts = aiPointsRef.current;
    if (pts.length === 0) return;
    const st = livePredictRef.current;
    if (st.inFlight) {
      st.dirty = true;
      return;
    }
    st.inFlight = true;
    st.dirty = false;
    const tip = aiTipRef.current;
    void runPredictPointsWith(tip ? [...pts, tip] : pts, { silent: true, live: true });
  }, [runPredictPointsWith]);

  const runPredictBox = useCallback(
    async (box: [[number, number], [number, number]]) => {
      aiAbortRef.current?.abort();
      const controller = new AbortController();
      aiAbortRef.current = controller;
      const seq = ++aiSeqRef.current;
      setAiLoading(true);
      setAiError(null);
      try {
        const res = await predictMaskFromBox(taskId, "z", index, box, controller.signal);
        if (aiSeqRef.current !== seq) return;
        const [h, w] = res.shape;
        const mask = decodeRuns(res.runs, h * w);
        if (!mask.some((v) => v !== 0)) {
          aiPreviewRef.current = null;
          setHasAiPreview(false);
          setAiError("No mask found for this box — try a tighter/looser box.");
          return;
        }
        aiPreviewRef.current = { mask: Uint8Array.from(mask), shape: [h, w] };
        setHasAiPreview(true);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (aiSeqRef.current !== seq) return;
        setAiError(e instanceof Error ? e.message : "Prediction failed");
      } finally {
        if (aiSeqRef.current === seq) setAiLoading(false);
        renderOverlay();
      }
    },
    [taskId, index, renderOverlay],
  );

  const commitAiPreview = useCallback(() => {
    // Re-entrancy guard (Cellable's `_finaliseInProgress`): a double
    // Enter/click while this is running must not double-apply the same
    // preview or double-fire the commit PUT.
    if (committingAiRef.current) return;
    const preview = aiPreviewRef.current;
    const ids = idsRef.current;
    if (!preview || !ids) return;
    committingAiRef.current = true;
    try {
      if (undoStack.current.length >= MAX_UNDO) undoStack.current.shift();
      undoStack.current.push(ids.slice());
      redoStack.current = [];
      for (let i = 0; i < ids.length; i++) if (preview.mask[i]) ids[i] = activeId;
      aiPreviewRef.current = null;
      aiPointsRef.current = [];
      aiTipRef.current = null;
      aiSeqRef.current += 1; // drop any predict still in flight for this prompt
      aiAbortRef.current?.abort();
      setHasAiPreview(false);
      setAiPointCount(0);
      renderOverlay();
      refreshInstances();
      syncHistoryCounts();
      markDirty();
    } finally {
      committingAiRef.current = false;
    }
  }, [activeId, renderOverlay, refreshInstances, syncHistoryCounts, markDirty]);

  // Enter/Ctrl-click/double-click finalize: match Cellable exactly — a
  // fresh committed-only predict, THEN commit that (not whatever the last
  // hover frame happened to show) — see #27 item L4. No-ops with no
  // committed points; `commitAiPreview` itself no-ops if the fresh predict
  // came back empty.
  const finalizeAiPoints = useCallback(async () => {
    if (aiPointsRef.current.length === 0) return;
    await runPredictPoints();
    commitAiPreview();
  }, [runPredictPoints, commitAiPreview]);

  const clearAiPoints = useCallback(() => {
    aiAbortRef.current?.abort();
    aiSeqRef.current += 1;
    aiPointsRef.current = [];
    aiPreviewRef.current = null;
    aiTipRef.current = null;
    livePredictRef.current = { inFlight: false, dirty: false };
    draggingPointIdxRef.current = null;
    // Also cancels an in-progress Box Mask rubber-band — Escape must clear
    // Box the same as Point/Boundary (#25 item C.2/C.5), and this is also
    // the function the "leave an AI tool" effect below calls.
    boxDragRef.current = null;
    drawingRef.current = false;
    setHasAiPreview(false);
    setAiPointCount(0);
    setAiError(null);
    setAiLoading(false);
    renderOverlay();
  }, [renderOverlay]);

  // Leaving an AI tool (Point/Box/Boundary) for any other tool clears its
  // proposal/points and aborts an in-flight predict; entering a (possibly
  // different) AI tool always starts clean (#25 item H).
  useEffect(() => {
    if (prevPaintToolRef.current === paintTool) return;
    prevPaintToolRef.current = paintTool;
    clearAiPoints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paintTool]);

  const applyBoxErase = useCallback(
    (y0: number, y1: number, x0: number, x1: number) => {
      const ids = idsRef.current;
      const [h, w] = shapeRef.current;
      if (!ids) return;
      if (undoStack.current.length >= MAX_UNDO) undoStack.current.shift();
      undoStack.current.push(ids.slice());
      redoStack.current = [];
      const cy1 = Math.min(h - 1, y1);
      const cx1 = Math.min(w - 1, x1);
      for (let y = Math.max(0, y0); y <= cy1; y++) {
        for (let x = Math.max(0, x0); x <= cx1; x++) ids[y * w + x] = 0;
      }
      renderOverlay();
      refreshInstances();
      syncHistoryCounts();
      markDirty();
    },
    [renderOverlay, refreshInstances, syncHistoryCounts, markDirty],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Swapped = the 2D canvas is the small, view-only preview (#31 item
      // 5) — every mutation this component ever makes (paint, erase, AI
      // points, box drag, seeds, even the Select eyedropper) originates
      // from this handler, so blocking it here alone is sufficient to make
      // the canvas fully inert; nothing downstream (`onPointerMove`'s drag/
      // live-predict branches, `onDoubleClick`) can activate without a
      // prior `onPointerDown` having set up its state first.
      // View mode and Swap both freeze mutations on the 2D surface.
      if (!editable || swapped) return;
      if (e.button !== 0) return;
      const pt = pixelFromEvent(e);
      if (!pt) return;
      const [py, px] = pt;
      const ids = idsRef.current;

      // Select tool (or Shift+click, except while placing AI points — there
      // Shift means "negative point") = eyedropper, never paints.
      if (paintTool === "select" || (e.shiftKey && !AI_POINT_TOOLS.includes(paintTool))) {
        if (ids) {
          const [, w] = shapeRef.current;
          const picked = ids[py * w + px];
          if (picked > 0) setActiveId(picked);
        }
        return;
      }

      if (AI_POINT_TOOLS.includes(paintTool)) {
        if (e.altKey) {
          // Alt+click an existing prompt point removes it and re-predicts
          // (or clears the preview if none remain) — Cellable-level prompt
          // editing fluency (#25 item E).
          const nearestIdx = nearestCommittedPointIndex(px, py, 12);
          if (nearestIdx >= 0) {
            const next = aiPointsRef.current.slice();
            next.splice(nearestIdx, 1);
            aiPointsRef.current = next;
            setAiPointCount(next.length);
            renderOverlay();
            runPredictPoints();
          }
          return;
        }
        if (!e.ctrlKey && !e.metaKey) {
          // Clicking on (not near-but-off) an existing committed point
          // drags it instead of adding a new one — Cellable-level vertex
          // drag for AI prompts (#29 item U8). Re-predicts live while
          // dragging (cheap — same coalesced path as the cursor tip) and
          // once more, non-live, on release.
          const dragIdx = nearestCommittedPointIndex(px, py, 10);
          if (dragIdx >= 0) {
            draggingPointIdxRef.current = dragIdx;
            aiTipRef.current = null; // no phantom hover tip while dragging a committed point
            (e.target as Element).setPointerCapture(e.pointerId);
            renderCursorOverlay();
            return;
          }
        }
        // Plain click pins the cursor tip as a new committed point — the
        // tip itself resets to null; the very next pointermove repopulates
        // it at the (possibly unchanged) cursor position, so the free-
        // floating marker "continues from the new last point" (Cellable's
        // `addPoint(line.points[1])`) without drawing a duplicate dot on
        // top of the just-committed one in the meantime.
        aiPointsRef.current = [...aiPointsRef.current, { x: px, y: py, label: e.shiftKey ? 0 : 1 }];
        aiTipRef.current = null;
        setAiPointCount(aiPointsRef.current.length);
        renderOverlay();
        // Ctrl/Cmd+click = add this point and immediately finalize, same as
        // Cellable's "Ctrl+LeftClick ends" (#25 item C.3) — `finalizeAiPoints`
        // itself re-predicts committed-only then commits, so this doesn't
        // double-predict; a plain click instead runs the normal (non-
        // finalizing) committed-only predict for live feedback.
        if (e.ctrlKey || e.metaKey) finalizeAiPoints();
        else runPredictPoints();
        return;
      }

      if (paintTool === "box_mask" || paintTool === "box_eraser") {
        boxDragRef.current = { x0: px, y0: py, x1: px, y1: py };
        drawingRef.current = true;
        (e.target as Element).setPointerCapture(e.pointerId);
        renderOverlay();
        return;
      }

      if (paintTool === "seeds") {
        if (!ids) return;
        const [, w] = shapeRef.current;
        const label = ids[py * w + px];
        if (wsSeeds.length === 0) {
          if (label <= 0) {
            setWsMessage("Click on a labeled region (not background) to place the first seed.");
            return;
          }
          setWsTargetLabel(label);
          setWsSeeds([{ z: index, y: py, x: px, label }]);
          setWsMessage(null);
        } else {
          if (label !== wsTargetLabel) {
            setWsMessage(
              `Clicked label ${label}, but seeds are on label ${wsTargetLabel}. Clear seeds or click that label.`,
            );
            return;
          }
          setWsSeeds((prev) => [...prev, { z: index, y: py, x: px, label }]);
          setWsMessage(null);
        }
        renderOverlay();
        return;
      }

      // Brush / Erase (circular) — existing painting flow.
      if (ids) {
        if (undoStack.current.length >= MAX_UNDO) undoStack.current.shift();
        undoStack.current.push(ids.slice());
        redoStack.current = [];
        syncHistoryCounts();
      }
      drawingRef.current = true;
      lastPointRef.current = null;
      (e.target as Element).setPointerCapture(e.pointerId);
      strokeTo(py, px);
    },
    [
      editable,
      swapped,
      pixelFromEvent,
      paintTool,
      wsSeeds,
      wsTargetLabel,
      index,
      strokeTo,
      syncHistoryCounts,
      renderOverlay,
      renderCursorOverlay,
      runPredictPoints,
      finalizeAiPoints,
      nearestCommittedPointIndex,
    ],
  );

  // Double-click finalizes a Point/Boundary proposal, same as Cellable's
  // `double_click: close` (#25 item C.4) — scoped to Point/Boundary (not
  // Box) to match Cellable's own `mouseDoubleClickEvent`, which only closes
  // its click-accumulated point modes.
  const onDoubleClick = useCallback(() => {
    // `finalizeAiPoints` itself no-ops with zero committed points and
    // re-derives whether there's anything to commit, so this doesn't need
    // to duplicate a `hasAiPreview`/`aiPointCount` gate (#27 item L4).
    if (AI_POINT_TOOLS.includes(paintTool)) finalizeAiPoints();
  }, [paintTool, finalizeAiPoints]);

  // Minimal right-click context menu (#29 item U15) — mode switches always,
  // plus Verify/Solo when right-clicking on an actual label. Deliberately
  // small (Cellable's own canvas context menu is a handful of items, not a
  // full command palette).
  const onContextMenu = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      if (!editable || swapped) return;
      const pt = pixelFromEvent(e);
      const ids = idsRef.current;
      let labelId: number | null = null;
      if (pt && ids) {
        const [, w] = shapeRef.current;
        const v = ids[pt[0] * w + pt[1]];
        if (v > 0) labelId = v;
      }
      setContextMenu({ x: e.clientX, y: e.clientY, labelId });
    },
    [editable, swapped, pixelFromEvent],
  );

  // Close the context menu on any click outside it (or Escape, handled in
  // the keydown effect above).
  useEffect(() => {
    if (!contextMenu) return;
    const onPointerDownOutside = (e: PointerEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    window.addEventListener("pointerdown", onPointerDownOutside);
    return () => window.removeEventListener("pointerdown", onPointerDownOutside);
  }, [contextMenu]);

  // Repopulates `intensityCtxRef` from the currently displayed `<img>` —
  // called from the `<img>`'s own `onLoad`, so it always has this slice's
  // actual pixels (not last slice's, not a blank canvas) by the time a
  // pointer move needs to read from it. Deliberately reads the *undisplayed*
  // image (before CSS brightness/contrast), matching "intensity from the
  // displayed slice" in the brief without also needing to bake the CSS
  // filter into a canvas read (browsers don't expose the post-filter pixels
  // via `getImageData` anyway — filters are compositor-side).
  const updateIntensityCanvas = useCallback(() => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;
    const canvas = intensityCtxRef.current?.canvas ?? document.createElement("canvas");
    if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(img, 0, 0);
    intensityCtxRef.current = ctx;
  }, []);

  // Status readout under the canvas (#29 item U3, Cellable's status bar
  // `"Mouse is at: slice=…, x=…, y=…, intensity=…, label=…"`) — a direct DOM
  // write (`statusReadoutRef`), not React state, since pointer moves fire
  // far too often to route through a re-render (same reasoning as the
  // overlay canvas itself). Intensity reads the *undisplayed* slice image
  // (`intensityCtxRef`, populated on every slice load's `<img>` onLoad) —
  // "from the displayed slice" per the brief, deliberately not the raw
  // backend array, so no extra fetch is needed just for this readout.
  const updateStatusReadout = useCallback(
    (pt: [number, number] | null) => {
      const el = statusReadoutRef.current;
      if (!el) return;
      if (!pt) {
        el.textContent = "";
        return;
      }
      const [py, px] = pt;
      const ids = idsRef.current;
      const [, w] = shapeRef.current;
      const label = ids ? ids[py * w + px] : 0;
      let intensity: number | string = "–";
      const ictx = intensityCtxRef.current;
      if (ictx) {
        try {
          intensity = ictx.getImageData(px, py, 1, 1).data[0];
        } catch {
          intensity = "–";
        }
      }
      el.textContent = `z ${index + 1} · x ${px}, y ${py} · intensity ${intensity} · label ${label > 0 ? label : "–"}`;
    },
    [index],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const pt = pixelFromEvent(e);
      hoverPosRef.current = pt;
      updateStatusReadout(pt);
      if (draggingPointIdxRef.current != null) {
        // Dragging a committed AI prompt point (#29 item U8) — update its
        // position in place and live-predict (cheap, coalesced — same path
        // as the cursor tip); a final non-live predict fires on release.
        if (pt) {
          const idx = draggingPointIdxRef.current;
          const pts = aiPointsRef.current;
          if (idx < pts.length) {
            const next = pts.slice();
            next[idx] = { ...next[idx], x: pt[1], y: pt[0] };
            aiPointsRef.current = next;
          }
        }
        renderCursorOverlay();
        scheduleLivePredict();
        return;
      }
      if (paintTool === "box_mask" || paintTool === "box_eraser") {
        if (drawingRef.current && boxDragRef.current && pt) {
          boxDragRef.current = { ...boxDragRef.current, x1: pt[1], y1: pt[0] };
        }
        // Rubber-band drag + crosshair are both cheap re-blit + vector
        // redraws — never touch the O(h*w) label recompute mid-drag.
        renderCursorOverlay();
        return;
      }
      if (paintTool === "brush" || paintTool === "eraser") {
        if (drawingRef.current && pt) strokeTo(pt[0], pt[1]);
        else renderCursorOverlay(); // just move the size-cursor circle
        return;
      }
      if (AI_POINT_TOOLS.includes(paintTool)) {
        // Cursor-follow live proposal (#27) — no tip (and no preview at
        // all) until ≥1 point is committed, matching Cellable's `if not
        // self.current: return`. `renderCursorOverlay` moves the tip vertex
        // immediately every move (smooth tracking); `scheduleLivePredict`
        // is throttled and only actually updates the green fill once its
        // (possibly delayed) network response lands.
        aiTipRef.current = pt && aiPointsRef.current.length > 0 ? { x: pt[1], y: pt[0], label: e.shiftKey ? 0 : 1 } : null;
        renderCursorOverlay();
        scheduleLivePredict();
        return;
      }
    },
    [pixelFromEvent, updateStatusReadout, paintTool, strokeTo, renderCursorOverlay, scheduleLivePredict],
  );

  const onPointerUp = useCallback(() => {
    if (draggingPointIdxRef.current != null) {
      // Drag ends — re-predict once more, non-live, so the settled position
      // gets a real (not last-coalesced-frame) proposal (#29 item U8).
      draggingPointIdxRef.current = null;
      runPredictPoints();
      return;
    }
    if (paintTool === "box_mask" || paintTool === "box_eraser") {
      const box = boxDragRef.current;
      drawingRef.current = false;
      if (!box) return;
      const x0 = Math.min(box.x0, box.x1);
      const x1 = Math.max(box.x0, box.x1);
      const y0 = Math.min(box.y0, box.y1);
      const y1 = Math.max(box.y0, box.y1);
      const hasArea = x1 > x0 && y1 > y0;
      if (paintTool === "box_eraser") {
        boxDragRef.current = null;
        if (hasArea) applyBoxErase(y0, y1, x0, x1);
        else renderOverlay();
      } else {
        boxDragRef.current = null;
        if (hasArea) runPredictBox([[x0, y0], [x1, y1]]);
        else renderOverlay();
      }
      return;
    }
    if (!drawingRef.current) return;
    drawingRef.current = false;
    lastPointRef.current = null;
    markDirty();
  }, [paintTool, applyBoxErase, runPredictBox, renderOverlay, markDirty, runPredictPoints]);

  const onPointerLeave = useCallback(() => {
    hoverPosRef.current = null;
    updateStatusReadout(null);
    // A drag in progress when the pointer leaves still needs the same
    // release handling `onPointerUp` gives it (clear the drag ref,
    // re-predict once more) — `onPointerUp()` below already covers this
    // since it's the same function, just also reachable via leave.
    onPointerUp();
    // Tip leaves the canvas (#27 item 5) — drop it and immediately (not
    // throttled — this is a discrete leave, not a move stream) re-predict
    // committed-only so the proposal snaps back rather than sitting on a
    // stale off-canvas tip until the next move.
    if (AI_POINT_TOOLS.includes(paintTool) && aiTipRef.current) {
      aiTipRef.current = null;
      runPredictPoints();
    }
    renderCursorOverlay();
  }, [onPointerUp, paintTool, runPredictPoints, renderCursorOverlay, updateStatusReadout]);

  const undo = useCallback(() => {
    const ids = idsRef.current;
    const prev = undoStack.current.pop();
    if (!prev || !ids) return;
    redoStack.current.push(ids.slice());
    idsRef.current = prev;
    renderOverlay();
    refreshInstances();
    syncHistoryCounts();
    markDirty();
  }, [renderOverlay, refreshInstances, syncHistoryCounts, markDirty]);

  const redo = useCallback(() => {
    const ids = idsRef.current;
    const next = redoStack.current.pop();
    if (!next || !ids) return;
    undoStack.current.push(ids.slice());
    idsRef.current = next;
    renderOverlay();
    refreshInstances();
    syncHistoryCounts();
    markDirty();
  }, [renderOverlay, refreshInstances, syncHistoryCounts, markDirty]);

  const deleteSlice = useCallback(() => {
    const ids = idsRef.current;
    if (!ids || !ids.some((v) => v > 0)) return;
    if (!window.confirm("Clear all instances from this slice? This only affects the current slice — other slices are untouched.")) {
      return;
    }
    if (undoStack.current.length >= MAX_UNDO) undoStack.current.shift();
    undoStack.current.push(ids.slice());
    redoStack.current = [];
    ids.fill(0);
    renderOverlay();
    refreshInstances();
    syncHistoryCounts();
    markDirty();
  }, [renderOverlay, refreshInstances, syncHistoryCounts, markDirty]);

  // Clear just one instance's pixels from the current slice — a more
  // surgical delete than "Delete Slice", matching Cellable's per-shape
  // delete from the label list. Still goes through the same undo stack.
  const deleteInstance = useCallback(
    (id: number) => {
      const ids = idsRef.current;
      if (!ids) return;
      if (undoStack.current.length >= MAX_UNDO) undoStack.current.shift();
      undoStack.current.push(ids.slice());
      redoStack.current = [];
      for (let i = 0; i < ids.length; i++) if (ids[i] === id) ids[i] = 0;
      renderOverlay();
      refreshInstances();
      syncHistoryCounts();
      markDirty();
      setActiveId((cur) => (cur === id ? nextIdRef.current : cur));
    },
    [renderOverlay, refreshInstances, syncHistoryCounts, markDirty],
  );

  const clearWsSeeds = useCallback(() => {
    setWsSeeds([]);
    setWsTargetLabel(null);
    setWsMessage(null);
    renderOverlay();
  }, [renderOverlay]);

  const runWatershedNow = useCallback(async () => {
    if (!wsTargetLabel || wsSeeds.length === 0) return;
    setWsRunning(true);
    setWsMessage(null);
    try {
      const seeds: WatershedSeed[] = wsSeeds.map(({ z, y, x }) => ({ z, y, x }));
      const result = await runWatershed(taskId, wsTargetLabel, seeds);
      setWsSeeds([]);
      setWsTargetLabel(null);
      setWsMessage(
        `Split label ${result.target_label}: added ${result.new_label_ids.length} new label(s)` +
          (result.new_label_ids.length ? ` (${result.new_label_ids.join(", ")}).` : "."),
      );
      await loadSlice(index);
      setLabelsRefreshToken((v) => v + 1);
    } catch (e) {
      setWsMessage(e instanceof Error ? e.message : "Watershed failed");
    } finally {
      setWsRunning(false);
    }
  }, [taskId, wsTargetLabel, wsSeeds, index, loadSlice]);

  // --- Track (SAM2): propagate the active instance's current-slice shape -

  const runTracking = useCallback(async () => {
    const ids = idsRef.current;
    const [h, w] = shapeRef.current;
    if (!ids) return;
    const mask = new Uint8Array(h * w);
    let any = false;
    for (let i = 0; i < ids.length; i++) {
      if (ids[i] === activeId) {
        mask[i] = 1;
        any = true;
      }
    }
    if (!any) {
      setTrackError(`Paint or AI-mask instance ${activeId} on this slice first, then Track.`);
      return;
    }
    setTracking(true);
    setTrackError(null);
    try {
      await trackTaskFork(
        taskId,
        [{ z: index, rle: trueRunsRLE(mask), shape: [h, w] }],
        [Math.min(trackZFrom, trackZTo), Math.max(trackZFrom, trackZTo)],
      );
      await loadSlice(index);
      setLabelsRefreshToken((v) => v + 1);
    } catch (e) {
      setTrackError(e instanceof Error ? e.message : "Tracking failed");
    } finally {
      setTracking(false);
    }
  }, [taskId, index, activeId, trackZFrom, trackZTo, loadSlice]);

  const jump = useCallback(
    (delta: number) => requestIndex(index + delta),
    [requestIndex, index],
  );

  const jumpToZ = useCallback(
    (z: number) => requestIndex(z),
    [requestIndex],
  );

  const handleLifecycleAction = useCallback(
    async (labelId: number, action: LabelLifecycleAction) => {
      setLifecycleError(null);
      try {
        await setLabelLifecycle(taskId, labelId, action);
        if (action === "revert" || action === "reject") {
          await loadSlice(index);
        }
        setLabelsRefreshToken((v) => v + 1);
      } catch (e) {
        setLifecycleError(e instanceof Error ? e.message : `Failed to ${action} label ${labelId}`);
      }
    },
    [taskId, index, loadSlice],
  );

  const toggleHidden = useCallback((id: number) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSolo = useCallback((id: number) => {
    setSoloId((prev) => (prev === id ? null : id));
  }, []);

  const resetVisibility = useCallback(() => {
    setHiddenIds(new Set());
    setSoloId(null);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const activeRow = labelsSummaryRows.find((r) => r.id === activeId);
      // Undo/Redo mutate the raster the same way painting does, so they
      // must respect the swap guard too (#31 item 5) — otherwise Ctrl+Z
      // could revert a stroke from before the user swapped into 3D view
      // even though the Undo *button* is grayed out via the tool fieldset.
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (editable && !swapped) redo();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        if (editable && !swapped) undo();
      } else if (e.key === "a" || e.key === "ArrowLeft") jump(-1);
      else if (e.key === "d" || e.key === "ArrowRight") jump(1);
      // Annotate-only hotkeys below.
      else if (!editable || swapped) {
        /* z-nav only in View */
      } else if (e.key === "v") setPaintTool("select");
      else if (e.key === "b") setPaintTool("brush");
      else if (e.key === "e") setPaintTool("eraser");
      else if (e.key === "p") setPaintTool("point_mask");
      else if (e.key === "m") setPaintTool("box_mask");
      else if (e.key === "o") setPaintTool("boundary");
      else if (e.key === "r") setPaintTool("box_eraser");
      else if (e.key === "t") setPaintTool("seeds"); // #29 item U7 (Cellable: T = watershed_3d)
      // Label-lifecycle/visibility hotkeys (#29 items U9/U10/U11/U12) — all
      // operate on the currently active label, matching what the Filters
      // Options buttons already do; checked via `e.key.toLowerCase()` +
      // `e.shiftKey` (not the raw shifted `e.key`) so caps-lock can't
      // silently swap which one fires.
      else if (!e.shiftKey && e.key.toLowerCase() === "f") {
        // F = Verify (V stays Select — #29 item U9, do not remap V).
        handleLifecycleAction(activeId, "verify");
      } else if (e.shiftKey && e.key.toLowerCase() === "r") {
        // Shift+R = Revert (bare R stays Box Erase — #29 item U10).
        if (activeRow?.can_revert) handleLifecycleAction(activeId, "revert");
      } else if (e.key === "Delete") {
        // Delete = Reject, behind the same confirm as the Filters Options
        // button — a keystroke must never skip that safety check (#29 item
        // U10, progress/history/04-incident-data-safety.md).
        if (window.confirm(`Reject label ${activeId}? This deletes every voxel of this label from the whole volume.`)) {
          handleLifecycleAction(activeId, "reject");
        }
      } else if (!e.shiftKey && e.key.toLowerCase() === "h") {
        setHideVerified((v) => !v); // #29 item U11
      } else if (!e.shiftKey && e.key.toLowerCase() === "s") {
        toggleSolo(activeId); // #29 item U12
      } else if (e.shiftKey && e.key.toLowerCase() === "s") {
        resetVisibility(); // #29 item U12 ("show all")
      } else if (e.key === "Enter" && AI_POINT_TOOLS.includes(paintTool)) {
        // Point/Boundary: re-predict committed-only, then commit that —
        // never whatever the last hover frame happened to show (#27 item
        // L4, Cellable's `finalise()` semantics).
        finalizeAiPoints();
      } else if (e.key === "Enter" && paintTool === "box_mask") {
        if (hasAiPreview) commitAiPreview();
      } else if (e.key === "Escape" && AI_PREVIEW_TOOLS.includes(paintTool)) {
        // Esc clears the AI proposal on ALL AI tools, including Box (#25
        // item C.2) — clearAiPoints also cancels an in-progress Box
        // rubber-band drag.
        clearAiPoints();
      } else if (e.key === "Escape" && contextMenu) {
        setContextMenu(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    editable,
    swapped,
    undo,
    redo,
    jump,
    paintTool,
    hasAiPreview,
    commitAiPreview,
    finalizeAiPoints,
    clearAiPoints,
    activeId,
    labelsSummaryRows,
    handleLifecycleAction,
    toggleSolo,
    resetVisibility,
    contextMenu,
  ]);

  // While Cmd/Ctrl is held: lock scroll so trackpad cannot pan mid-zoom.
  useEffect(() => {
    const syncLock = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const vp = viewportRef.current;
      if (mod && vp) {
        if (!cmdScrollLockRef.current) {
          cmdScrollLockRef.current = { left: vp.scrollLeft, top: vp.scrollTop };
        }
      } else {
        cmdScrollLockRef.current = null;
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Meta" || e.key === "Control") syncLock(e);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Meta" || e.key === "Control") syncLock(e);
      // keyup on Meta clears e.metaKey before this fires in some browsers
      if ((e.key === "Meta" || e.key === "Control") && !e.metaKey && !e.ctrlKey) {
        cmdScrollLockRef.current = null;
      }
    };
    const onBlur = () => {
      cmdScrollLockRef.current = null;
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  // Native wheel (non-passive) so preventDefault actually blocks scroll while Cmd held.
  // Re-bind when the viewport mounts (it is absent during the loading shell).
  useEffect(() => {
    if (meta.loading || meta.error || !meta.data) return;
    const vp = viewportRef.current;
    if (!vp) return;

    const onScroll = () => {
      const lock = cmdScrollLockRef.current;
      if (!lock) return;
      if (vp.scrollLeft !== lock.left) vp.scrollLeft = lock.left;
      if (vp.scrollTop !== lock.top) vp.scrollTop = lock.top;
    };

    const onWheel = (e: WheelEvent) => {
      if (drawingRef.current) return;
      if (!(e.ctrlKey || e.metaKey)) {
        // Plain wheel pans — treat as user view adjustment.
        if (needsOpenCenterRef.current && (e.deltaX !== 0 || e.deltaY !== 0)) {
          needsOpenCenterRef.current = false;
        }
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      needsOpenCenterRef.current = false;

      // Freeze pan for this Cmd gesture; zoom toward the cursor so the image
      // does not appear to crawl upward (freezing raw pixels alone does that).
      const layout = stageLayoutRef.current;
      const factor = Math.pow(WHEEL_ZOOM_BASE, -e.deltaY / 100);
      if (layout && layout.stageW > 0) {
        const rect = vp.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const offsetY = e.clientY - rect.top;
        const sx = vp.scrollLeft + offsetX;
        const sy = vp.scrollTop + offsetY;
        zoomAnchorRef.current = {
          offsetX,
          offsetY,
          localX: sx - layout.stageLeft,
          localY: sy - layout.stageTop,
          oldW: layout.stageW,
        };
      }
      // Keep scroll locked at the pre-event position until layout applies the anchor.
      cmdScrollLockRef.current = { left: vp.scrollLeft, top: vp.scrollTop };
      setZoom((z) => clampZoom(z * factor));
    };

    vp.addEventListener("scroll", onScroll);
    vp.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      vp.removeEventListener("scroll", onScroll);
      vp.removeEventListener("wheel", onWheel);
    };
  }, [meta.loading, meta.error, meta.data]);

  /** Scroll so the stage matches Fit window (centered) or Fit width (top-pinned when tall). */
  const applyFitScroll = useCallback(
    (
      vp: HTMLDivElement,
      layout: {
        stageW: number;
        stageH: number;
        stageLeft: number;
        stageTop: number;
      },
      mode: "window" | "width",
    ) => {
      const left = layout.stageLeft - (vp.clientWidth - layout.stageW) / 2;
      const top =
        mode === "width" && layout.stageH > vp.clientHeight + 0.5
          ? layout.stageTop
          : layout.stageTop - (vp.clientHeight - layout.stageH) / 2;
      vp.scrollLeft = left;
      vp.scrollTop = top;
    },
    [],
  );

  // Stage size = frozen fit-base × zoom. Recomputing the fit base on every
  // zoom step amplified tiny shell/subpixel changes when zoomed in deep and
  // felt like the canvas was auto-adjusting — freeze the baseline instead.
  const layoutStage = useCallback(() => {
    const shell = shellRef.current;
    const img = imgRef.current;
    if (!shell || !img?.naturalWidth || !img.naturalHeight) return;
    const vw = shell.clientWidth;
    const vh = shell.clientHeight;
    if (vw <= 0 || vh <= 0) return;

    const shellChanged =
      Math.abs(lastShellRef.current.w - vw) > 1 ||
      Math.abs(lastShellRef.current.h - vh) > 1;
    // Never refit mid-zoom-anchor (would fight cursor anchoring).
    const allowShellRefit = shellChanged && !zoomAnchorRef.current;
    const mustRefit =
      pendingFitRef.current != null ||
      needsOpenCenterRef.current ||
      fitBaseRef.current.w <= 0 ||
      allowShellRefit;

    if (mustRefit) {
      const nw = img.naturalWidth;
      const nh = img.naturalHeight;
      let fitW: number;
      let fitH: number;
      if (fitMode === "width") {
        fitW = vw;
        fitH = nh * (vw / nw);
      } else {
        const s = Math.min(vw / nw, vh / nh);
        fitW = nw * s;
        fitH = nh * s;
      }
      fitBaseRef.current = {
        w: fitW,
        h: fitH,
        padX: vw / 2,
        padY: vh / 2,
      };
      lastShellRef.current = { w: vw, h: vh };
    }

    const { w: fitW, h: fitH, padX, padY } = fitBaseRef.current;
    const next = {
      stageW: fitW * zoom,
      stageH: fitH * zoom,
      contentW: fitW * zoom + padX * 2,
      contentH: fitH * zoom + padY * 2,
      stageLeft: padX,
      stageTop: padY,
    };

    const shouldFit =
      pendingFitRef.current != null || needsOpenCenterRef.current;
    const fitModeForScroll = pendingFitRef.current ?? fitMode;
    if (shouldFit) {
      flushSync(() => {
        setStageLayout(next);
      });
      const wasPendingFit = pendingFitRef.current != null;
      pendingFitRef.current = null;
      const vp = viewportRef.current;
      if (vp) {
        applyFitScroll(vp, next, fitModeForScroll);
        // Annotate chrome can still be settling (rails/panels). Re-center for
        // a couple of frames; only then drop needsOpenCenter — never again
        // unless the user clicks Fit.
        const shellW = vw;
        const shellH = vh;
        requestAnimationFrame(() => {
          const vp2 = viewportRef.current;
          const layout2 = stageLayoutRef.current;
          const shell2 = shellRef.current;
          if (!vp2 || !layout2) return;
          applyFitScroll(vp2, layout2, fitModeForScroll);
          requestAnimationFrame(() => {
            const shell3 = shellRef.current;
            const vp3 = viewportRef.current;
            const layout3 = stageLayoutRef.current;
            if (!shell3 || !vp3 || !layout3) return;
            const settled =
              Math.abs(shell3.clientWidth - shellW) <= 1 &&
              Math.abs(shell3.clientHeight - shellH) <= 1 &&
              (!shell2 ||
                (Math.abs(shell2.clientWidth - shellW) <= 1 &&
                  Math.abs(shell2.clientHeight - shellH) <= 1));
            applyFitScroll(vp3, layout3, fitModeForScroll);
            if (wasPendingFit || settled) {
              needsOpenCenterRef.current = false;
            }
            // If not settled, leave needsOpenCenter true — ResizeObserver will
            // refit+recenter once the side rails finish resizing the shell.
          });
        });
      } else if (wasPendingFit) {
        needsOpenCenterRef.current = false;
      }
    } else {
      setStageLayout((prev) => {
        if (
          prev &&
          Math.abs(prev.stageW - next.stageW) < 0.5 &&
          Math.abs(prev.stageH - next.stageH) < 0.5 &&
          Math.abs(prev.stageLeft - next.stageLeft) < 0.5 &&
          Math.abs(prev.stageTop - next.stageTop) < 0.5 &&
          Math.abs(prev.contentW - next.contentW) < 0.5 &&
          Math.abs(prev.contentH - next.contentH) < 0.5
        ) {
          return prev;
        }
        return next;
      });
    }
  }, [zoom, fitMode, fitEpoch, applyFitScroll]);

  const requestFit = useCallback((mode: "window" | "width") => {
    zoomAnchorRef.current = null;
    cmdScrollLockRef.current = null;
    needsOpenCenterRef.current = false;
    pendingFitRef.current = mode;
    setFitMode(mode);
    setZoom(1);
    setFitEpoch((e) => e + 1);
  }, []);

  useLayoutEffect(() => {
    layoutStage();
    const shell = shellRef.current;
    if (!shell) return;
    const ro = new ResizeObserver(() => layoutStage());
    ro.observe(shell);
    return () => ro.disconnect();
  }, [layoutStage]);

  useLayoutEffect(() => {
    const vp = viewportRef.current;
    const layout = stageLayout;
    if (!vp || !layout) return;

    const anchor = zoomAnchorRef.current;
    if (anchor && anchor.oldW > 0) {
      zoomAnchorRef.current = null;
      pendingFitRef.current = null;
      needsOpenCenterRef.current = false;
      const factor = layout.stageW / anchor.oldW;
      const left = layout.stageLeft + anchor.localX * factor - anchor.offsetX;
      const top = layout.stageTop + anchor.localY * factor - anchor.offsetY;
      vp.scrollLeft = left;
      vp.scrollTop = top;
      if (cmdScrollLockRef.current) {
        cmdScrollLockRef.current = { left: vp.scrollLeft, top: vp.scrollTop };
      }
    }
  }, [stageLayout]);

  /** Full-height side rail: drag to resize, click (no drag) to collapse/expand. */
  const beginSideRail = useCallback(
    (side: "left" | "right", e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      const handle = e.currentTarget;
      handle.setPointerCapture(e.pointerId);
      const startX = e.clientX;
      const startW = side === "left" ? leftPanelW : rightPanelW;
      const open = side === "left" ? leftPanelOpen : rightPanelOpen;
      let dragged = false;
      const onMove = (ev: PointerEvent) => {
        const dx = ev.clientX - startX;
        if (!dragged && Math.abs(dx) < 4) return;
        dragged = true;
        if (side === "left") {
          if (!open) setLeftPanelOpen(true);
          setLeftPanelW(clampSidePanel(open ? startW + dx : SIDE_PANEL_DEFAULT + dx));
        } else {
          if (!open) setRightPanelOpen(true);
          setRightPanelW(clampSidePanel(open ? startW - dx : SIDE_PANEL_DEFAULT - dx));
        }
      };
      const onUp = (ev: PointerEvent) => {
        handle.releasePointerCapture(ev.pointerId);
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        if (!dragged) {
          if (side === "left") setLeftPanelOpen((v) => !v);
          else setRightPanelOpen((v) => !v);
        }
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
    },
    [leftPanelW, rightPanelW, leftPanelOpen, rightPanelOpen],
  );

  const gridLeftW = leftPanelOpen ? leftPanelW : 0;
  const gridRightW = rightPanelOpen ? rightPanelW : 0;

  /** +/- zoom toward viewport center; does not change z. */
  const applyZoom = useCallback(
    (nextRaw: number) => {
      const vp = viewportRef.current;
      const layout = stageLayoutRef.current;
      const next = clampZoom(nextRaw);
      if (next === zoom) return;
      needsOpenCenterRef.current = false;
      if (vp && layout && layout.stageW > 0) {
        const offsetX = vp.clientWidth / 2;
        const offsetY = vp.clientHeight / 2;
        const sx = vp.scrollLeft + offsetX;
        const sy = vp.scrollTop + offsetY;
        zoomAnchorRef.current = {
          offsetX,
          offsetY,
          localX: sx - layout.stageLeft,
          localY: sy - layout.stageTop,
          oldW: layout.stageW,
        };
      }
      setZoom(next);
    },
    [zoom],
  );

  const newInstance = useCallback(() => {
    setActiveId(nextIdRef.current);
    setPaintTool("brush");
  }, []);

  const togglePinned3D = useCallback((id: number) => {
    setPinned3D((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  /** Bulk-pin labels into the 3D view (This slice / All one-click). Adds to
   * the existing pin set — does not clear other pins. */
  const pinManyTo3D = useCallback((ids: number[]) => {
    if (ids.length === 0) return;
    setPinned3D((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (id > 0) next.add(id);
      }
      return next;
    });
  }, []);

  // Labels in the 3D panel follow the same visibility rules as the 2D
  // canvas: Solo = exclusive; Hide / Hide Verified remove from both views.
  // Only explicitly pinned ids are shown (plus Solo's target) — the active
  // id is NOT auto-injected, so the "3D" button state matches what's drawn.
  const label3DIds = useMemo(() => {
    if (soloId != null && soloId > 0) {
      if (hideVerified && verifiedIds.has(soloId)) return [];
      return [soloId];
    }
    const ids: number[] = [];
    for (const id of pinned3D) {
      if (id <= 0) continue;
      if (hiddenIds.has(id)) continue;
      if (hideVerified && verifiedIds.has(id)) continue;
      ids.push(id);
    }
    ids.sort((a, b) => a - b);
    return ids;
  }, [pinned3D, soloId, hiddenIds, hideVerified, verifiedIds]);

  const filter = displayFilter(brightness, contrast);
  // Brush/Erase draw their own size-circle cursor and Box Mask/Box Erase
  // their own crosshair (#25 items D/G, in drawVectorOverlay) — hide the
  // native OS cursor for those so it doesn't sit on top of/compete with the
  // custom one, Cellable-style ("the drawn feedback IS the cursor").
  const cursor = useMemo(() => {
    if (!editable || swapped) return "default"; // view-only / swapped
    if (paintTool === "select") return "pointer";
    if (["brush", "eraser", "box_mask", "box_eraser"].includes(paintTool)) return "none";
    return "crosshair";
  }, [editable, swapped, paintTool]);

  // Equal-width z-page and zoom% number inputs (#31 item 3) — both share
  // this one `widthCh`, big enough for the zoom's "100%"-scale values and
  // for the z index of any real volume (grows with `axisLen`'s digit count
  // instead of silently truncating a 5-digit z on a very deep volume).
  const metricInputWidthCh = Math.max(4, String(axisLen).length);

  if (meta.loading) return <p className="muted">Loading volume…</p>;
  if (meta.error) return <div className="error">{meta.error}</div>;
  if (!meta.data) return null;

  return (
    <div className="canvas-root">
      {editable && (
        <AnnotateToolChrome
          disabled={swapped}
          paintTool={paintTool}
          onPaintTool={setPaintTool}
          dirty={dirty}
          status={status}
          sliceLoading={sliceLoading}
          undoCount={undoCount}
          redoCount={redoCount}
          onSave={() => void saveLabels("manual")}
          onUndo={undo}
          onRedo={redo}
          onDeleteSlice={deleteSlice}
          brushSize={brushSize}
          onBrushSize={setBrushSize}
          eraserSize={eraserSize}
          onEraserSize={setEraserSize}
          activeId={activeId}
          onActiveId={setActiveId}
          onNewInstance={newInstance}
          aiError={aiError}
          aiPointCount={aiPointCount}
          aiLoading={aiLoading}
          hasAiPreview={hasAiPreview}
          onFinalizeAiPoints={finalizeAiPoints}
          onCommitAiPreview={commitAiPreview}
          onClearAiPoints={clearAiPoints}
          wsTargetLabel={wsTargetLabel}
          wsSeedCount={wsSeeds.length}
          wsMessage={wsMessage}
          wsRunning={wsRunning}
          onClearWsSeeds={clearWsSeeds}
          onRunWatershed={runWatershedNow}
        />
      )}

      <div
        className="canvas-main-row"
        data-swapped={swapped ? "true" : "false"}
        data-mode={editable ? "annotate" : "view"}
        style={{
          gridTemplateColumns: editable
            ? `${gridLeftW}px ${SIDE_RAIL_W}px minmax(0, 1fr) ${SIDE_RAIL_W}px ${gridRightW}px`
            : `minmax(0, 1fr) ${SIDE_RAIL_W}px ${gridRightW}px`,
        }}
      >
        {editable && (
          <TrackRail
            hidden={!leftPanelOpen}
            disabled={swapped}
            activeId={activeId}
            activeColorCss={labelColorCss(activeId)}
            trackZFrom={trackZFrom}
            trackZTo={trackZTo}
            axisLen={axisLen}
            tracking={tracking}
            trackError={trackError}
            onTrackZFrom={setTrackZFrom}
            onTrackZTo={setTrackZTo}
            onRunTracking={runTracking}
          />
        )}

        {editable && (
          <div
            className={`side-rail side-rail-left${leftPanelOpen ? "" : " side-rail-collapsed"}`}
            title={leftPanelOpen ? "Drag to resize · click to hide Track" : "Click to show Track · drag to open"}
            onPointerDown={(e) => beginSideRail("left", e)}
          />
        )}

        {/* 2D canvas — layout-size zoom; status lives outside the scrollport. */}
        <div className="card canvas-panel">
          <div className="row spread labels-3d-header">
            <h3 style={{ margin: 0 }}>Canvas</h3>
            <span className="muted labels-3d-status">
              {!editable || swapped ? "View only" : `${instances.length} label(s) on slice`}
            </span>
            <button
              type="button"
              className="secondary labels-3d-swap"
              title={
                swapped
                  ? "Swap back — restore the 2D canvas to the center"
                  : "Swap — enlarge 3D Labels"
              }
              onClick={() => setSwapped((v) => !v)}
            >
              Swap
            </button>
          </div>
          <div ref={shellRef} className="canvas-viewport-shell">
            <div ref={viewportRef} className="canvas-viewport">
              <div
                className="canvas-scroll-content"
                style={
                  stageLayout
                    ? { width: stageLayout.contentW, height: stageLayout.contentH }
                    : undefined
                }
              >
                <div
                  className="canvas-stage"
                  style={
                    stageLayout
                      ? {
                          width: stageLayout.stageW,
                          height: stageLayout.stageH,
                          left: stageLayout.stageLeft,
                          top: stageLayout.stageTop,
                        }
                      : undefined
                  }
                >
                  {/* eslint-disable-next-line jsx-a11y/alt-text */}
                  <img
                    ref={imgRef}
                    onLoad={() => {
                      updateIntensityCanvas();
                      layoutStage();
                    }}
                    style={{
                      display: "block",
                      width: "100%",
                      height: "100%",
                      imageRendering: "pixelated",
                      filter,
                      userSelect: "none",
                    }}
                  />
                  <canvas
                    ref={overlayRef}
                    onPointerDown={onPointerDown}
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onPointerLeave={onPointerLeave}
                    onDoubleClick={onDoubleClick}
                    onContextMenu={onContextMenu}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      imageRendering: "pixelated",
                      cursor,
                      touchAction: "none",
                    }}
                  />
                </div>
              </div>
            </div>
            <div className="canvas-status-overlay">
              <span ref={statusReadoutRef} />
            </div>
            {swapped && (
              <div className="canvas-swap-overlay" aria-live="polite">
                {editable ? "View only — Swap to annotate" : "Swap to enlarge canvas"}
              </div>
            )}
          </div>
        </div>

        <div
          className={`side-rail side-rail-right${rightPanelOpen ? "" : " side-rail-collapsed"}`}
          title={
            rightPanelOpen
              ? "Drag to resize · click to hide 3D / Labels"
              : "Click to show 3D / Labels · drag to open"
          }
          onPointerDown={(e) => beginSideRail("right", e)}
        />

        <Labels3DPanel
          taskId={taskId}
          labelIds={label3DIds}
          refreshKey={labelsRefreshToken}
          swapped={swapped}
          onToggleSwap={() => setSwapped((v) => !v)}
        />

        <div className="labels-panel-slot">
          <LabelsPanel
            activeId={activeId}
            onSetActiveId={setActiveId}
            sliceInstances={instances}
            rows={labelsSummaryRows}
            rowsLoading={labelsSummaryLoading}
            hiddenIds={hiddenIds}
            soloId={soloId}
            onToggleHidden={toggleHidden}
            onToggleSolo={toggleSolo}
            onResetVisibility={resetVisibility}
            onDeleteInstance={deleteInstance}
            pinnedIds={pinned3D}
            onTogglePinned={togglePinned3D}
            onPinMany={pinManyTo3D}
            onJumpToZ={jumpToZ}
            hideVerified={hideVerified}
            onHideVerifiedChange={setHideVerified}
            onLifecycleAction={handleLifecycleAction}
            onRefresh={() => setLabelsRefreshToken((v) => v + 1)}
            readOnly={!editable}
          />
          {editable && lifecycleError && (
            <p className="error labels-lifecycle-error">{lifecycleError}</p>
          )}
        </div>
      </div>

      <div className="canvas-controls">
        <div className="row canvas-toolrow" style={{ flexWrap: "wrap" }}>
          <button className="secondary" onClick={() => jump(-10)}>
            ◀◀
          </button>
          <button className="secondary" onClick={() => jump(-1)}>
            ◀
          </button>
          <input
            type="range"
            min={0}
            max={axisLen - 1}
            value={index}
            onChange={(e) => requestIndex(Number(e.target.value))}
            style={{ flex: 1, minWidth: 80, maxWidth: "none" }}
            title={`z ${index + 1}/${axisLen}`}
          />
          <button className="secondary" onClick={() => jump(1)}>
            ▶
          </button>
          <button className="secondary" onClick={() => jump(10)}>
            ▶▶
          </button>
          <span className="muted slice-index" style={{ whiteSpace: "nowrap" }}>
            z{" "}
            <CommitNumberInput
              value={index + 1}
              min={1}
              max={axisLen}
              title={`Go to z slice (1–${axisLen})`}
              widthCh={metricInputWidthCh}
              onCommit={(n) => requestIndex(n - 1)}
            />
            /{axisLen}
          </span>
          <button
            className="secondary"
            onClick={() => applyZoom(zoom / BUTTON_ZOOM_FACTOR)}
          >
            −
          </button>
          <CommitNumberInput
            value={Math.round(zoom * 100)}
            min={Math.round(MIN_ZOOM * 100)}
            max={Math.round(MAX_ZOOM * 100)}
            suffix="%"
            title="Zoom percent (80%–800%)"
            widthCh={metricInputWidthCh}
            onCommit={(pct) => applyZoom(pct / 100)}
          />
          <button
            className="secondary"
            onClick={() => applyZoom(zoom * BUTTON_ZOOM_FACTOR)}
          >
            +
          </button>
          <button
            className={fitMode === "window" ? "" : "secondary"}
            title="Fit the whole slice inside the viewport"
            onClick={() => requestFit("window")}
          >
            Fit window
          </button>
          <button
            className={fitMode === "width" ? "" : "secondary"}
            title="Fill the viewport width; scroll vertically if needed"
            onClick={() => requestFit("width")}
          >
            Fit width
          </button>
        </div>
        <DisplayKnobs
          brightness={brightness}
          contrast={contrast}
          onBrightness={setBrightness}
          onContrast={setContrast}
          labelOpacity={labelOpacity}
          onLabelOpacity={setLabelOpacity}
        />
      </div>
      {/* No permanent hotkey-hint footer here (#31 item 2 — deliberately
          removed; it was costing a full-width row without adding anything
          the status overlay + docs don't already cover). The full hotkey
          map lives in progress/development.md and
          progress/frontend/features/MODULE.md, not in the live chrome. The
          status readout itself moved to an absolute overlay inside
          `.canvas-viewport` above, so it no longer costs a row either. */}

      {editable && contextMenu && (
        <div
          ref={contextMenuRef}
          className="canvas-context-menu"
          style={{ position: "fixed", left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            className="danger"
            title="Discard the current Point/Box/Boundary proposal without committing (Esc)"
            onClick={() => {
              clearAiPoints();
              setContextMenu(null);
            }}
          >
            Cancel
          </button>
          {(
            [
              ["select", "Select"],
              ["brush", "Brush"],
              ["eraser", "Erase"],
              ["point_mask", "Point Mask"],
              ["box_mask", "Box Mask"],
              ["boundary", "Boundary"],
            ] as [PaintTool, string][]
          ).map(([tool, label]) => (
            <button
              key={tool}
              className="secondary"
              onClick={() => {
                setPaintTool(tool);
                setContextMenu(null);
              }}
            >
              {label}
            </button>
          ))}
          {contextMenu.labelId != null && (
            <>
              <hr />
              <button
                className="secondary"
                onClick={() => {
                  const id = contextMenu.labelId as number;
                  setActiveId(id);
                  handleLifecycleAction(id, "verify");
                  setContextMenu(null);
                }}
              >
                ✓ Verify label {contextMenu.labelId}
              </button>
              <button
                className="secondary"
                onClick={() => {
                  toggleSolo(contextMenu.labelId as number);
                  setContextMenu(null);
                }}
              >
                ○ Solo label {contextMenu.labelId}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
