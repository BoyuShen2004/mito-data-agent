import type { PaintTool } from "./paintTools";
import { labelColorCss } from "../labelColor";

export type AnnotateSaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

/**
 * Top annotate chrome: tool strip + fixed-height tool-context row.
 * Annotate-only — View mode does not mount this module.
 */
export default function AnnotateToolChrome({
  disabled,
  paintTool,
  onPaintTool,
  dirty,
  status,
  sliceLoading,
  undoCount,
  redoCount,
  onSave,
  onUndo,
  onRedo,
  onDeleteSlice,
  brushSize,
  onBrushSize,
  eraserSize,
  onEraserSize,
  activeId,
  onActiveId,
  onNewInstance,
  aiError,
  aiPointCount,
  aiLoading,
  hasAiPreview,
  onFinalizeAiPoints,
  onCommitAiPreview,
  onClearAiPoints,
  wsTargetLabel,
  wsSeedCount,
  wsMessage,
  wsRunning,
  onClearWsSeeds,
  onRunWatershed,
}: {
  disabled: boolean;
  paintTool: PaintTool;
  onPaintTool: (t: PaintTool) => void;
  dirty: boolean;
  status: AnnotateSaveStatus;
  sliceLoading: boolean;
  undoCount: number;
  redoCount: number;
  onSave: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onDeleteSlice: () => void;
  brushSize: number;
  onBrushSize: (n: number) => void;
  eraserSize: number;
  onEraserSize: (n: number) => void;
  activeId: number;
  onActiveId: (id: number) => void;
  onNewInstance: () => void;
  aiError: string | null;
  aiPointCount: number;
  aiLoading: boolean;
  hasAiPreview: boolean;
  onFinalizeAiPoints: () => void;
  onCommitAiPreview: () => void;
  onClearAiPoints: () => void;
  wsTargetLabel: number | null;
  wsSeedCount: number;
  wsMessage: string | null;
  wsRunning: boolean;
  onClearWsSeeds: () => void;
  onRunWatershed: () => void;
}) {
  return (
    <fieldset className="tool-fieldset" disabled={disabled}>
      {/* Mode-select row — fixed height so switching tools never jumps the canvas. */}
      <div className="row canvas-toolrow tool-strip">
        <button
          className={paintTool === "select" ? "" : "secondary"}
          onClick={() => onPaintTool("select")}
          title="Pick the instance under the cursor (V)"
        >
          Select
        </button>
        <button
          className={paintTool === "brush" ? "" : "secondary"}
          onClick={() => onPaintTool("brush")}
          title="Paint the active instance (B)"
        >
          Brush
        </button>
        <button
          className={paintTool === "eraser" ? "" : "secondary"}
          onClick={() => onPaintTool("eraser")}
          title="Erase (circular) (E)"
        >
          Erase
        </button>
        <button
          className={paintTool === "box_eraser" ? "" : "secondary"}
          onClick={() => onPaintTool("box_eraser")}
          title="Drag a box to clear a region (R)"
        >
          Box Erase
        </button>
        <button
          className={paintTool === "point_mask" ? "" : "secondary"}
          onClick={() => onPaintTool("point_mask")}
          title="Point Mask (P)"
        >
          Point Mask
        </button>
        <button
          className={paintTool === "box_mask" ? "" : "secondary"}
          onClick={() => onPaintTool("box_mask")}
          title="Box Mask (M)"
        >
          Box Mask
        </button>
        <button
          className={paintTool === "boundary" ? "" : "secondary"}
          onClick={() => onPaintTool("boundary")}
          title="Boundary (O)"
        >
          Boundary
        </button>
        <button
          className={paintTool === "seeds" ? "" : "secondary"}
          onClick={() => onPaintTool("seeds")}
          title="Click seed points on one instance -> 3D watershed split (T)"
        >
          Seeds
        </button>
        <span className="spacer" />
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty || status === "saving"}
          title="Write this slice's labels to the on-disk mask under data/. Edits are local until you Save."
        >
          Save
        </button>
        <button className="secondary" onClick={onUndo} disabled={undoCount === 0}>
          Undo
        </button>
        <button className="secondary" onClick={onRedo} disabled={redoCount === 0}>
          Redo
        </button>
        <button className="secondary" onClick={onDeleteSlice}>
          Delete slice
        </button>
        <span className="muted">
          {status === "saving" && "Saving…"}
          {status === "saved" && "Saved"}
          {status === "dirty" && "Unsaved"}
          {status === "error" && "Save failed"}
          {status === "idle" && sliceLoading && "Loading…"}
        </span>
      </div>

      {/* Fixed-height context row — reserved even when Select has no knobs. */}
      <div className="row canvas-toolrow tool-context">
        {paintTool === "brush" && (
          <>
            <span className="muted">Brush size</span>
            <input
              type="range"
              min={1}
              max={40}
              value={brushSize}
              onChange={(e) => onBrushSize(Number(e.target.value))}
              title={`Brush size ${brushSize}`}
            />
          </>
        )}
        {paintTool === "eraser" && (
          <>
            <span className="muted">Erase size</span>
            <input
              type="range"
              min={1}
              max={40}
              value={eraserSize}
              onChange={(e) => onEraserSize(Number(e.target.value))}
              title={`Erase size ${eraserSize}`}
            />
          </>
        )}
        {(paintTool === "brush" || paintTool === "point_mask" || paintTool === "box_mask") && (
          <>
            <span className="muted">Active</span>
            <span
              style={{
                display: "inline-block",
                width: 12,
                height: 12,
                borderRadius: 3,
                background: labelColorCss(activeId),
                border: "1px solid var(--border)",
              }}
            />
            <input
              type="number"
              min={1}
              value={activeId}
              onChange={(e) => onActiveId(Math.max(1, Number(e.target.value)))}
              style={{ width: 56 }}
            />
            <button className="secondary" onClick={onNewInstance}>
              New
            </button>
          </>
        )}
        {(paintTool === "point_mask" || paintTool === "boundary") && (
          <>
            {aiError && <span className="error">{aiError}</span>}
            <button onClick={onFinalizeAiPoints} disabled={aiPointCount === 0}>
              Commit (Enter)
            </button>
            <button className="secondary" onClick={onClearAiPoints} disabled={aiPointCount === 0}>
              Clear (Esc)
            </button>
            {aiLoading && (
              <span className="muted ai-busy" title="Predicting…">
                ⋯
              </span>
            )}
          </>
        )}
        {paintTool === "box_mask" && (
          <>
            {aiError && <span className="error">{aiError}</span>}
            <button onClick={onCommitAiPreview} disabled={!hasAiPreview}>
              Commit (Enter)
            </button>
            <button className="secondary" onClick={onClearAiPoints} disabled={!hasAiPreview}>
              Clear (Esc)
            </button>
            {aiLoading && (
              <span className="muted ai-busy" title="Predicting…">
                ⋯
              </span>
            )}
          </>
        )}
        {paintTool === "seeds" && (
          <>
            <span className="muted">
              {wsTargetLabel != null
                ? `Target label ${wsTargetLabel} · ${wsSeedCount} seed(s)`
                : "Click an existing instance to start placing seeds"}
            </span>
            {wsMessage && <span className="muted">{wsMessage}</span>}
            <button className="secondary" onClick={onClearWsSeeds} disabled={wsSeedCount === 0}>
              Clear seeds
            </button>
            <button onClick={onRunWatershed} disabled={wsRunning || wsSeedCount === 0}>
              {wsRunning ? "Splitting…" : "Run Watershed"}
            </button>
          </>
        )}
        {paintTool === "box_eraser" && (
          <span className="muted">Drag a box on the canvas to clear that region.</span>
        )}
      </div>
    </fieldset>
  );
}
