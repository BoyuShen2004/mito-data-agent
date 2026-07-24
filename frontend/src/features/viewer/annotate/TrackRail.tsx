/**
 * Left rail: SAM2 track / propagate the active instance across a z-range.
 * Annotate-only — View mode does not mount this module.
 */
export default function TrackRail({
  hidden,
  disabled,
  activeId,
  activeColorCss,
  trackZFrom,
  trackZTo,
  axisLen,
  tracking,
  trackError,
  onTrackZFrom,
  onTrackZTo,
  onRunTracking,
}: {
  hidden: boolean;
  disabled: boolean;
  activeId: number;
  activeColorCss: string;
  trackZFrom: number;
  trackZTo: number;
  axisLen: number;
  tracking: boolean;
  trackError: string | null;
  onTrackZFrom: (z: number) => void;
  onTrackZTo: (z: number) => void;
  onRunTracking: () => void;
}) {
  return (
    <div className="card track-rail" hidden={hidden}>
      <div className="row spread labels-3d-header">
        <h3 style={{ margin: 0 }}>Track (SAM2)</h3>
      </div>
      <fieldset className="track-rail-body" disabled={disabled}>
        <p className="muted">Propagate the active instance across a z-range.</p>
        <div className="row" style={{ gap: 6 }}>
          <span
            style={{
              display: "inline-block",
              width: 12,
              height: 12,
              borderRadius: 3,
              background: activeColorCss,
              border: "1px solid var(--border)",
            }}
          />
          <span className="muted">{activeId}</span>
        </div>
        <span className="muted">z</span>
        <input
          type="number"
          value={trackZFrom}
          min={0}
          max={axisLen - 1}
          onChange={(e) => onTrackZFrom(Number(e.target.value))}
          style={{ width: 56 }}
        />
        <span className="muted">to</span>
        <input
          type="number"
          value={trackZTo}
          min={0}
          max={axisLen - 1}
          onChange={(e) => onTrackZTo(Number(e.target.value))}
          style={{ width: 56 }}
        />
        <button onClick={onRunTracking} disabled={tracking}>
          {tracking ? "Tracking…" : "Track (SAM2)"}
        </button>
        {trackError && <span className="error">{trackError}</span>}
      </fieldset>
    </div>
  );
}
