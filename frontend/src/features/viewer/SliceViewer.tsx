import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchObjectUrl,
  getVolumeMeta,
  imageSlicePath,
  labelSlicePath,
  type Axis,
  type VolumeMeta,
} from "../../api/viewer";
import { useAsync } from "../../hooks/useAsync";
import CommitNumberInput from "./CommitNumberInput";
import DisplayKnobs from "./DisplayKnobs";
import { displayFilter } from "./displayAdjust";

// Bounded object-URL LRU (mirrors Cellable's MAX_SLICE_PIXMAP_CACHE = 256).
// Revoking on eviction keeps browser memory flat no matter how far you scroll.
const MAX_CACHED_SLICES = 256;
const PREFETCH_RADIUS = 3;

class BlobLRU {
  private map = new Map<string, string>();
  constructor(private limit: number) {}
  get(key: string) {
    const url = this.map.get(key);
    if (url) {
      this.map.delete(key);
      this.map.set(key, url);
    }
    return url;
  }
  set(key: string, url: string) {
    if (this.map.has(key)) URL.revokeObjectURL(this.map.get(key)!);
    this.map.set(key, url);
    while (this.map.size > this.limit) {
      const oldest = this.map.keys().next().value as string;
      URL.revokeObjectURL(this.map.get(oldest)!);
      this.map.delete(oldest);
    }
  }
  has(key: string) {
    return this.map.has(key);
  }
  clear() {
    for (const url of this.map.values()) URL.revokeObjectURL(url);
    this.map.clear();
  }
}

const AXES: Axis[] = ["z", "y", "x"];
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 8;
const clampZoom = (z: number) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));

export default function SliceViewer({ volumeId }: { volumeId: number }) {
  const meta = useAsync<VolumeMeta>(() => getVolumeMeta(volumeId), [volumeId]);

  const [axis, setAxis] = useState<Axis>("z");
  const [index, setIndex] = useState(0);
  // Brightness/contrast are purely client-side (CSS filter on the decoded
  // image) on a 0–100 scale — 50 is neutral. Scrubbing never re-fetches.
  const [brightness, setBrightness] = useState(50);
  const [contrast, setContrast] = useState(50);
  const [showLabels, setShowLabels] = useState(true);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [labelUrl, setLabelUrl] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  // "window" = classic fit-to-viewport (Cellable's fitWindow); "width" = fill
  // the horizontal space and let the viewport scroll vertically (fitWidth).
  const [fitMode, setFitMode] = useState<"window" | "width">("window");

  const cache = useRef(new BlobLRU(MAX_CACHED_SLICES));
  const labelCache = useRef(new BlobLRU(MAX_CACHED_SLICES));

  const axisLen = useMemo(() => {
    if (!meta.data) return 1;
    return meta.data.shape[axis];
  }, [meta.data, axis]);

  // Clamp + reset index to the middle when the axis (and its length) changes.
  useEffect(() => {
    if (meta.data) setIndex(Math.floor(meta.data.shape[axis] / 2));
  }, [meta.data, axis]);

  const loadImage = useCallback(
    async (a: Axis, i: number, signal?: AbortSignal): Promise<string> => {
      const k = `${a}:${i}`;
      const cached = cache.current.get(k);
      if (cached) return cached;
      const url = await fetchObjectUrl(
        imageSlicePath(volumeId, { axis: a, index: i }),
        signal,
      );
      cache.current.set(k, url);
      return url;
    },
    [volumeId],
  );

  const loadLabel = useCallback(
    async (a: Axis, i: number, signal?: AbortSignal): Promise<string | null> => {
      if (!meta.data?.has_label) return null;
      const k = `${a}:${i}`;
      const cached = labelCache.current.get(k);
      if (cached) return cached;
      try {
        const url = await fetchObjectUrl(labelSlicePath(volumeId, a, i), signal);
        labelCache.current.set(k, url);
        return url;
      } catch {
        return null;
      }
    },
    [volumeId, meta.data],
  );

  // Load the current slice, then prefetch neighbours so A/D scrolling is
  // smooth. Every run gets its own AbortController, cancelled the moment a
  // newer axis/index supersedes it (on the next run, or on unmount) — without
  // this, navigating quickly (fast scrubbing, or leaving the page) leaves a
  // pile of now-irrelevant multi-MB fetches in flight, starving the ones that
  // are actually still needed and making the app feel stuck.
  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    (async () => {
      try {
        const img = await loadImage(axis, index, controller.signal);
        if (alive) setImgUrl(img);
        const lab = showLabels ? await loadLabel(axis, index, controller.signal) : null;
        if (alive) setLabelUrl(lab);
        for (let d = 1; d <= PREFETCH_RADIUS; d++) {
          for (const n of [index + d, index - d]) {
            if (n >= 0 && n < axisLen) {
              loadImage(axis, n, controller.signal).catch(() => {});
              if (showLabels) loadLabel(axis, n, controller.signal).catch(() => {});
            }
          }
        }
      } catch {
        // Superseded (aborted) or a genuine fetch failure — either way there's
        // nothing to show for this now-stale round.
      }
    })();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [axis, index, axisLen, showLabels, loadImage, loadLabel]);

  // Clear caches (and free memory) when the volume changes/unmounts.
  const cacheRef = cache.current;
  const labelCacheRef = labelCache.current;
  useEffect(() => {
    return () => {
      cacheRef.clear();
      labelCacheRef.clear();
    };
  }, [cacheRef, labelCacheRef]);
  useEffect(() => {
    cache.current.clear();
    labelCache.current.clear();
  }, [volumeId]);

  const step = useCallback(
    (delta: number) => setIndex((i) => Math.max(0, Math.min(axisLen - 1, i + delta))),
    [axisLen],
  );

  // Cellable-style A/D (and arrows) to move through slices.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key === "a" || e.key === "ArrowLeft") step(-1);
      else if (e.key === "d" || e.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  // Slider drags fire many onChange events; only the latest per animation
  // frame is applied, so a fast drag never queues up a backlog of state
  // updates (this — not network — was the other source of jank).
  const rafRef = useRef<number | null>(null);
  const scheduleIndex = useCallback((next: number) => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => setIndex(next));
  }, []);
  useEffect(() => () => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
  }, []);

  // Wheel over the canvas zooms (Ctrl/Cmd+scroll, the standard image-viewer
  // convention) and never touches which z-slice is showing. A plain scroll is
  // left alone entirely — not preventDefault'd — so the browser's native
  // scrolling on the viewport's overflow:auto box pans around the current
  // slice once it's zoomed in past the viewport size. Slice navigation stays
  // on A/D/arrow keys, the slider, and the ◀/▶ buttons.
  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom((z) => clampZoom(z + (e.deltaY > 0 ? -0.1 : 0.1)));
  }, []);

  if (meta.loading) return <p className="muted">Loading volume…</p>;
  if (meta.error) return <div className="error">{meta.error}</div>;
  if (!meta.data) return null;

  const { shape } = meta.data;
  const filter = displayFilter(brightness, contrast);

  return (
    <div className="canvas-root">
      <div className="row spread canvas-toolrow" style={{ flexWrap: "wrap" }}>
        <div className="row" style={{ gap: "0.35rem" }}>
          <span className="muted">Plane</span>
          {AXES.map((a) => (
            <button
              key={a}
              className={a === axis ? "" : "secondary"}
              onClick={() => setAxis(a)}
            >
              {a === "z" ? "Axial (z)" : a === "y" ? "Coronal (y)" : "Sagittal (x)"}
            </button>
          ))}
        </div>
        <div className="row" style={{ gap: "0.35rem" }}>
          {meta.data.has_label && (
            <label className="row" style={{ gap: 4 }}>
              <input
                type="checkbox"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
              />
              <span className="muted">Labels</span>
            </label>
          )}
        </div>
      </div>

      <div className="canvas-main-row">
        <div onWheel={onWheel} className="canvas-viewport">
          {/* zoom=1 fits the whole slice in the viewport (no cropping) in
              "window" mode, or fills the width in "width" mode; the transform
              then scales further from that fit baseline. */}
          <div
            className="canvas-stage"
            style={{
              transform: `scale(${zoom})`,
              transformOrigin: fitMode === "window" ? "center" : "top left",
            }}
          >
            {imgUrl && (
              <img
                src={imgUrl}
                alt={`slice ${index}`}
                style={{
                  imageRendering: "pixelated",
                  filter,
                }}
              />
            )}
            {showLabels && labelUrl && (
              <img
                src={labelUrl}
                alt="labels"
                style={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  imageRendering: "pixelated",
                  pointerEvents: "none",
                }}
              />
            )}
          </div>
        </div>
      </div>

      <div className="canvas-controls">
        <div className="row canvas-toolrow" style={{ flexWrap: "wrap" }}>
          <button className="secondary" onClick={() => step(-1)}>
            ◀
          </button>
          <input
            type="range"
            min={0}
            max={axisLen - 1}
            value={index}
            onChange={(e) => scheduleIndex(Number(e.target.value))}
            style={{ flex: 1, minWidth: 80, maxWidth: "none" }}
            title={`${axis} ${index + 1}/${axisLen}`}
          />
          <button className="secondary" onClick={() => step(1)}>
            ▶
          </button>
          <span className="muted slice-index" style={{ whiteSpace: "nowrap" }}>
            {axis}{" "}
            <CommitNumberInput
              value={index + 1}
              min={1}
              max={axisLen}
              title={`Go to ${axis} slice (1–${axisLen})`}
              widthCh={Math.max(3, String(axisLen).length)}
              onCommit={(n) => scheduleIndex(n - 1)}
            />
            /{axisLen}
          </span>
          <button className="secondary" onClick={() => setZoom((z) => clampZoom(z - 0.25))}>
            −
          </button>
          <CommitNumberInput
            value={Math.round(zoom * 100)}
            min={Math.round(MIN_ZOOM * 100)}
            max={Math.round(MAX_ZOOM * 100)}
            suffix="%"
            title="Zoom percent"
            widthCh={4}
            onCommit={(pct) => setZoom(clampZoom(pct / 100))}
          />
          <button className="secondary" onClick={() => setZoom((z) => clampZoom(z + 0.25))}>
            +
          </button>
          <button
            className={fitMode === "window" ? "" : "secondary"}
            title="Fit the whole slice inside the viewport"
            onClick={() => {
              setFitMode("window");
              setZoom(1);
            }}
          >
            Fit window
          </button>
          <button
            className={fitMode === "width" ? "" : "secondary"}
            title="Fill the viewport width; scroll vertically if needed"
            onClick={() => {
              setFitMode("width");
              setZoom(1);
            }}
          >
            Fit width
          </button>
        </div>
        <DisplayKnobs
          brightness={brightness}
          contrast={contrast}
          onBrightness={setBrightness}
          onContrast={setContrast}
        />
      </div>
      <p
        className="canvas-hint"
        title={`shape z${shape.z} · y${shape.y} · x${shape.x} · Ctrl/Cmd+scroll zoom · scroll pan · A/D slice`}
      >
        z{shape.z} · y{shape.y} · x{shape.x} · Ctrl/Cmd+scroll zoom · A/D slice
      </p>
    </div>
  );
}
