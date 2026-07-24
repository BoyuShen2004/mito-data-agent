import { useMemo, useState } from "react";
import type { LabelLifecycleAction, LabelLifecycleState, LabelSummaryRow } from "../../api/viewer";
import { labelColorCss } from "./labelColor";

// Cellable-parity Labels panel — mirrors the "Filters Options" surface in
// cellable/labelme/app.py (~line 990: listFilterCombo / hideVerifiedCheckbox
// / solo+show-all buttons / sort buttons / verify+revert+reject buttons /
// labelStateStatsLabel), not just a thin id-filter box. Per
// progress/history/21-cellable-parity-followups.md: this replaced a v1
// version that only had search+solo+hide+delete — this round adds the
// state filter, hide-verified, sort, and lifecycle actions Cellable's user
// actually relies on.
export type LabelsScope = "slice" | "all";
type ShowFilter = "all" | "proposed" | "edited" | "verified" | "not_verified";
type SortMode = "id_asc" | "id_desc" | "size_asc" | "size_desc" | "state";

const STATE_DOT: Record<LabelLifecycleState, string> = {
  proposed: "○",
  edited: "◐",
  verified: "●",
};
const STATE_ORDER: Record<LabelLifecycleState, number> = { proposed: 0, edited: 1, verified: 2 };

/** Exact voxel count, visible on every row now (#31 item 1) — previously
 * only in a `title=` tooltip on "All" rows, not shown at all on "This
 * slice" rows. Compact `k` form above 10,000 (still exact below that,
 * where the digit count is short enough to just show outright). */
function formatVoxelCount(n: number): string {
  if (n >= 10000) return `${(n / 1000).toFixed(1)}k vox`;
  return `${n.toLocaleString()} vox`;
}

export default function LabelsPanel({
  activeId,
  onSetActiveId,
  sliceInstances,
  rows,
  rowsLoading,
  hiddenIds,
  soloId,
  onToggleHidden,
  onToggleSolo,
  onResetVisibility,
  onDeleteInstance,
  pinnedIds,
  onTogglePinned,
  onPinMany,
  onJumpToZ,
  hideVerified,
  onHideVerifiedChange,
  onLifecycleAction,
  onRefresh,
  readOnly = false,
}: {
  activeId: number;
  onSetActiveId: (id: number) => void;
  sliceInstances: number[];
  rows: LabelSummaryRow[];
  rowsLoading: boolean;
  hiddenIds: Set<number>;
  soloId: number | null;
  onToggleHidden: (id: number) => void;
  onToggleSolo: (id: number) => void;
  onResetVisibility: () => void;
  onDeleteInstance: (id: number) => void;
  pinnedIds: Set<number>;
  onTogglePinned: (id: number) => void;
  /** Pin many label ids into the 3D view at once (This slice / All). */
  onPinMany: (ids: number[]) => void;
  onJumpToZ: (z: number) => void;
  hideVerified: boolean;
  onHideVerifiedChange: (v: boolean) => void;
  onLifecycleAction: (labelId: number, action: LabelLifecycleAction) => void;
  onRefresh: () => void;
  /** View mode: hide verify/reject/delete; keep browse / visibility / 3D pin. */
  readOnly?: boolean;
}) {
  const [scope, setScope] = useState<LabelsScope>("all");
  const [filterText, setFilterText] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showFilter, setShowFilter] = useState<ShowFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("id_asc");

  const rowsById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);

  const stats = useMemo(() => {
    const out = { total: rows.length, proposed: 0, edited: 0, verified: 0 };
    for (const r of rows) out[r.state] += 1;
    return out;
  }, [rows]);

  const filteredSlice = useMemo(() => {
    const q = filterText.trim();
    return sliceInstances.filter((id) => {
      if (q && !String(id).includes(q)) return false;
      if (hideVerified && rowsById.get(id)?.state === "verified") return false;
      return true;
    });
  }, [sliceInstances, filterText, hideVerified, rowsById]);

  const visibleAllRows = useMemo(() => {
    const q = filterText.trim();
    let list = rows.filter((r) => {
      if (q && !String(r.id).includes(q)) return false;
      if (hideVerified && r.state === "verified") return false;
      if (showFilter === "all") return true;
      if (showFilter === "not_verified") return r.state !== "verified";
      return r.state === showFilter;
    });
    list = [...list].sort((a, b) => {
      switch (sortMode) {
        case "id_asc":
          return a.id - b.id;
        case "id_desc":
          return b.id - a.id;
        case "size_asc":
          return a.voxel_count - b.voxel_count;
        case "size_desc":
          return b.voxel_count - a.voxel_count;
        case "state":
          return STATE_ORDER[a.state] - STATE_ORDER[b.state] || a.id - b.id;
        default:
          return 0;
      }
    });
    return list;
  }, [rows, filterText, hideVerified, showFilter, sortMode]);

  const activeRow = rowsById.get(activeId);

  const jumpToSearchMatch = () => {
    const id = Number(filterText.trim());
    if (!Number.isFinite(id)) return;
    const row = rowsById.get(id);
    if (row) {
      onSetActiveId(id);
      onJumpToZ(row.z_start);
    }
  };

  return (
    <div className="card labels-panel">
      <div className="row spread">
        <h3 style={{ margin: 0 }}>Labels</h3>
        {(hiddenIds.size > 0 || soloId != null) && (
          <button className="secondary" onClick={onResetVisibility}>
            Reset
          </button>
        )}
      </div>

      {/* Filters Options toggle + Hide Verified beside it (not buried in the
          dropdown) + state legend. Hide Verified defaults off so labels show. */}
      <div className="row spread labels-filters-header">
        <div className="row labels-filters-header-left">
          <button className="secondary" onClick={() => setFiltersOpen((v) => !v)}>
            Filters Options {filtersOpen ? "▲" : "▼"}
          </button>
          <label className="row labels-hide-verified" title="Hide Verified — H">
            <input
              type="checkbox"
              checked={hideVerified}
              onChange={(e) => onHideVerifiedChange(e.target.checked)}
            />
            Hide Verified
          </label>
        </div>
        <span className="muted labels-state-legend" title="○ Proposed  ◐ Edited  ● Verified">
          ○{stats.proposed} ◐{stats.edited} ●{stats.verified}
        </span>
      </div>

      {filtersOpen && (
        <div className="labels-filters-popup">
          <div className="row labels-filters-row">
            <span className="muted">Show:</span>
            <select value={showFilter} onChange={(e) => setShowFilter(e.target.value as ShowFilter)}>
              <option value="all">All</option>
              <option value="proposed">Proposed</option>
              <option value="edited">Edited</option>
              <option value="verified">Verified</option>
              <option value="not_verified">Not Verified</option>
            </select>
          </div>
          <div className="row labels-filters-row">
            <button className="secondary" title="Solo the active label — S" onClick={() => onToggleSolo(activeId)}>
              Solo
            </button>
            <button className="secondary" title="Show all labels — Shift+S" onClick={onResetVisibility}>
              Show All
            </button>
            {soloId != null && <span className="muted">Solo: {soloId}</span>}
          </div>
          <div className="row labels-filters-row">
            <button className="secondary" onClick={() => setSortMode("id_asc")}>
              ↑ ID
            </button>
            <button className="secondary" onClick={() => setSortMode("id_desc")}>
              ↓ ID
            </button>
            <button className="secondary" onClick={() => setSortMode("size_asc")}>
              ↑ Size
            </button>
            <button className="secondary" onClick={() => setSortMode("size_desc")}>
              ↓ Size
            </button>
            <button className="secondary" onClick={() => setSortMode("state")}>
              State
            </button>
          </div>
          {!readOnly && (
            <div className="row labels-filters-row">
              <button
                className="secondary"
                title="Verify the active label (a human has confirmed it's correct) — F"
                onClick={() => onLifecycleAction(activeId, "verify")}
              >
                ✓ Verify
              </button>
              <button
                className="secondary"
                title="Unverify the active label (move it back to Edited so it can be changed again)"
                disabled={activeRow?.state !== "verified"}
                onClick={() => onLifecycleAction(activeId, "unverify")}
              >
                ○ Unverify
              </button>
              <button
                className="secondary"
                title="Revert the active label to its proposed (AI-created) snapshot — Shift+R"
                disabled={!activeRow?.can_revert}
                onClick={() => onLifecycleAction(activeId, "revert")}
              >
                ⟲ Revert
              </button>
              <button
                className="secondary"
                title="Reject (delete) the active label from the whole volume — Delete"
                onClick={() => {
                  if (
                    window.confirm(
                      `Reject label ${activeId}? This deletes every voxel of this label from the whole volume.`,
                    )
                  ) {
                    onLifecycleAction(activeId, "reject");
                  }
                }}
              >
                ✗ Reject
              </button>
              <button className="secondary" onClick={onRefresh}>
                Refresh
              </button>
            </div>
          )}
          {readOnly && (
            <div className="row labels-filters-row">
              <button className="secondary" onClick={onRefresh}>
                Refresh
              </button>
            </div>
          )}
        </div>
      )}

      <div className="tabs labels-scope-tabs">
        <button
          className={`tab ${scope === "slice" ? "tab-active" : ""}`}
          onClick={() => setScope("slice")}
          title="Labels present on the current slice only"
        >
          This slice
        </button>
        <button
          className={`tab ${scope === "all" ? "tab-active" : ""}`}
          onClick={() => setScope("all")}
          title="Every label in the whole volume's working copy"
        >
          All
        </button>
      </div>
      <input
        type="text"
        placeholder="Search label ID… (Enter to jump)"
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") jumpToSearchMatch();
        }}
        style={{ margin: "0.5rem 0" }}
      />
      <div className="row spread labels-list-meta">
        <p className="muted labels-list-count">
          {scope === "slice"
            ? `${filteredSlice.length} label(s) on this slice`
            : rowsLoading
              ? "Loading…"
              : `${visibleAllRows.length} of ${rows.length} label(s)`}
        </p>
        {scope === "slice" ? (
          <button
            type="button"
            className="secondary labels-3d-bulk"
            disabled={filteredSlice.length === 0}
            title="Show every label on this slice in the 3D view"
            onClick={() => onPinMany(filteredSlice)}
          >
            3D slice
          </button>
        ) : (
          <button
            type="button"
            className="secondary labels-3d-bulk"
            disabled={rowsLoading || visibleAllRows.length === 0}
            title="Show every listed label in the 3D view"
            onClick={() => onPinMany(visibleAllRows.map((r) => r.id))}
          >
            3D all
          </button>
        )}
      </div>

      {scope === "slice" ? (
        <>
          {sliceInstances.length === 0 && <p className="muted">No instances on this slice.</p>}
          {sliceInstances.length > 0 && filteredSlice.length === 0 && (
            <p className="muted">No instance matches "{filterText}".</p>
          )}
          <ul className="labels-list">
            {filteredSlice.map((id) => (
              <li
                key={id}
                className="row spread"
                style={{ fontWeight: id === activeId ? 600 : 400 }}
              >
                <span
                  className="row"
                  style={{ gap: 6, alignItems: "center" }}
                  onClick={() => onSetActiveId(id)}
                >
                  <Swatch id={id} />
                  {id}
                  <StateDot row={rowsById.get(id)} />
                  <span className="muted labels-row-size">
                    {rowsById.has(id) ? formatVoxelCount(rowsById.get(id)!.voxel_count) : "—"}
                  </span>
                </span>
                <span className="row" style={{ gap: 4 }}>
                  <LabelViewButtons
                    id={id}
                    pinnedIds={pinnedIds}
                    soloId={soloId}
                    hiddenIds={hiddenIds}
                    onTogglePinned={onTogglePinned}
                    onToggleSolo={onToggleSolo}
                    onToggleHidden={onToggleHidden}
                  />
                  {!readOnly && (
                    <button
                      className="secondary"
                      title="Delete this instance from the current slice"
                      onClick={() => onDeleteInstance(id)}
                      style={{ padding: "1px 6px" }}
                    >
                      🗑
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          {!rowsLoading && rows.length === 0 && <p className="muted">Nothing painted in this volume yet.</p>}
          {rows.length > 0 && visibleAllRows.length === 0 && (
            <p className="muted">No label matches the current filters.</p>
          )}
          <ul className="labels-list">
            {visibleAllRows.map((row) => (
              <li
                key={row.id}
                className="row spread"
                style={{ fontWeight: row.id === activeId ? 600 : 400 }}
              >
                <span
                  className="row"
                  style={{ gap: 6, alignItems: "center", cursor: "pointer" }}
                  title={`${row.voxel_count} voxels · z ${row.z_start}–${row.z_end} · ${row.state} (${row.origin})`}
                  onClick={() => {
                    onSetActiveId(row.id);
                    onJumpToZ(row.z_start);
                  }}
                >
                  <Swatch id={row.id} />
                  {row.id}
                  <StateDot row={row} />
                  <span className="muted labels-row-size">{formatVoxelCount(row.voxel_count)}</span>
                  <span className="muted" style={{ fontSize: "0.68rem" }}>
                    z{row.z_start}
                    {row.z_end !== row.z_start ? `–${row.z_end}` : ""}
                  </span>
                </span>
                <span className="row" style={{ gap: 4 }}>
                  <LabelViewButtons
                    id={row.id}
                    pinnedIds={pinnedIds}
                    soloId={soloId}
                    hiddenIds={hiddenIds}
                    onTogglePinned={onTogglePinned}
                    onToggleSolo={onToggleSolo}
                    onToggleHidden={onToggleHidden}
                  />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Swatch({ id }: { id: number }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 12,
        height: 12,
        borderRadius: 3,
        background: labelColorCss(id),
        border: "1px solid var(--border)",
      }}
    />
  );
}

/** Shared 3D / Solo / Hide controls — same state on This slice and All, and
 * the same flags drive both the 2D canvas overlay and the 3D Labels fetch. */
function LabelViewButtons({
  id,
  pinnedIds,
  soloId,
  hiddenIds,
  onTogglePinned,
  onToggleSolo,
  onToggleHidden,
}: {
  id: number;
  pinnedIds: Set<number>;
  soloId: number | null;
  hiddenIds: Set<number>;
  onTogglePinned: (id: number) => void;
  onToggleSolo: (id: number) => void;
  onToggleHidden: (id: number) => void;
}) {
  const pinned = pinnedIds.has(id);
  const solo = soloId === id;
  const hidden = hiddenIds.has(id);
  return (
    <>
      <button
        type="button"
        className="secondary"
        title={pinned ? "Remove from 3D view" : "Show in 3D view"}
        onClick={() => onTogglePinned(id)}
        style={{ padding: "1px 6px", opacity: pinned ? 1 : 0.5 }}
      >
        3D
      </button>
      <button
        type="button"
        className="secondary"
        title={solo ? "Un-solo (2D + 3D)" : "Solo — show only this label on canvas and in 3D"}
        onClick={() => onToggleSolo(id)}
        style={{ padding: "1px 6px", opacity: solo ? 1 : 0.6 }}
      >
        {solo ? "◉" : "○"}
      </button>
      <button
        type="button"
        className="secondary"
        title={hidden ? "Show on canvas and in 3D" : "Hide on canvas and in 3D"}
        onClick={() => onToggleHidden(id)}
        style={{ padding: "1px 6px", opacity: hidden ? 0.4 : 1 }}
      >
        {hidden ? "🙈" : "👁"}
      </button>
    </>
  );
}

function StateDot({ row }: { row: LabelSummaryRow | undefined }) {
  if (!row) return null;
  return (
    <span className="muted" title={row.state}>
      {STATE_DOT[row.state]}
    </span>
  );
}
