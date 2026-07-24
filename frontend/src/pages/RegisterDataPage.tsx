import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  scanDataSources,
  registerData,
  type ScanResult,
  type DirSuggestion,
  type RegisterDataPair,
} from "../api/registerData";
import { listProjects } from "../api/projects";
import { useAsync } from "../hooks/useAsync";
import type { DatasetMetadata } from "../types/project";
import type { LabelType } from "../types";

const METADATA_FIELDS: { key: keyof DatasetMetadata; label: string }[] = [
  { key: "organism", label: "Organism / species" },
  { key: "tissue", label: "Tissue or organ" },
  { key: "cell_type", label: "Cell type" },
  { key: "imaging_modality", label: "Imaging modality" },
  { key: "imaging_instrument", label: "Imaging instrument / microscope" },
  { key: "experimental_condition", label: "Experimental condition" },
  { key: "sample_condition", label: "Sample condition" },
  { key: "dataset_source", label: "Dataset source" },
  { key: "publication", label: "Publication / reference" },
];

const LABEL_TYPES: LabelType[] = ["prediction", "proofread", "partial", "none"];

const NO_MASK = ""; // sentinel for the "image only" option

interface Row {
  image: string;
  mask: string; // "" = image only
  case: string;
  chunk_id: string;
  selected: boolean;
  matched: boolean; // paired automatically by the scan
}

// One directory configured for registration: it becomes a single dataset
// holding all of its selected volume pairs. Several of these can be queued up so
// many directories register into the same project in one go.
interface StagedDataset {
  dataset: string;
  volume: string;
  image_directory: string;
  mask_directory: string;
  label_type: LabelType;
  metadata: DatasetMetadata;
  pairs: RegisterDataPair[];
}

export default function RegisterDataPage() {
  const { isManager } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // Data is registered *into* a project, which must already exist: arriving
  // from "New project" or a project's "Register more data" preselects it.
  const [projectId, setProjectId] = useState(params.get("project") ?? "");
  const projects = useAsync(() => listProjects(), []);
  const hasProjects = (projects.data ?? []).length > 0;

  const [dataset, setDataset] = useState("");
  const [volume, setVolume] = useState("");
  const [imageDir, setImageDir] = useState("");
  const [maskDir, setMaskDir] = useState("");
  const [labelType, setLabelType] = useState<LabelType>("prediction");
  const [metadata, setMetadata] = useState<DatasetMetadata>({});
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Directories queued up to register together, each becoming its own dataset.
  const [staged, setStaged] = useState<StagedDataset[]>([]);
  // Result of the last "Register" action (one entry per dataset registered),
  // shown as a success banner. A project can hold many datasets, so we stay on
  // the page afterwards instead of navigating straight to the project.
  const [lastResult, setLastResult] = useState<
    { dataset: string; count: number }[] | null
  >(null);

  const setMeta = (key: keyof DatasetMetadata, value: string) =>
    setMetadata((m) => ({ ...m, [key]: value }));

  const buildRows = (res: ScanResult): Row[] => [
    ...res.pairs.map((p) => ({
      image: p.image,
      mask: p.mask,
      case: p.case,
      chunk_id: "",
      selected: true,
      matched: true,
    })),
    // Images with no mask are still registerable on their own.
    ...res.unmatched_images.map((name) => ({
      image: name,
      mask: NO_MASK,
      case: name,
      chunk_id: "",
      selected: true,
      matched: false,
    })),
  ];

  // dataset.json already records what a requester would otherwise retype.
  const prefillFromManifest = (res: ScanResult) => {
    const meta = res.dataset_metadata || {};
    const text = (v: unknown) => (typeof v === "string" ? v : "");
    setMetadata((m) => ({
      ...m,
      ...(text(meta.publication) && !m.publication
        ? { publication: text(meta.publication) }
        : {}),
      ...(text(meta.dataset_source) && !m.dataset_source
        ? { dataset_source: text(meta.dataset_source) }
        : {}),
    }));
    setDescription((d) => d || text(meta.description));
    setDataset((d) => d || text(meta.dataset_source));
  };

  // Clear the dataset-specific inputs so the same project stays selected and the
  // form is ready for the next dataset.
  const resetForAnother = () => {
    setDataset("");
    setVolume("");
    setImageDir("");
    setMaskDir("");
    setLabelType("prediction");
    setMetadata({});
    setDescription("");
    setNotes("");
    setScan(null);
    setRows([]);
    setError(null);
  };

  const runScan = async (image: string, mask: string) => {
    setScanning(true);
    setError(null);
    setLastResult(null);
    try {
      const res = await scanDataSources(image, mask);
      setScan(res);
      setRows(buildRows(res));
      prefillFromManifest(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
      setScan(null);
      setRows([]);
    } finally {
      setScanning(false);
    }
  };

  // Quick-pick a sibling folder (labelsTr vs labelsTr-instance, Tr vs Ts).
  const pickDirectory = (role: "image" | "mask", s: DirSuggestion) => {
    if (role === "image") {
      setImageDir(s.path);
      runScan(s.path, maskDir);
    } else {
      setMaskDir(s.path);
      runScan(imageDir, s.path);
    }
  };

  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const setAll = (selected: boolean) =>
    setRows((rs) => rs.map((r) => ({ ...r, selected })));

  // Masks nothing is using yet — the only sensible options for a manual pair,
  // which keeps this list short instead of listing every file in the folder.
  const freeMasks = (row: Row): string[] => {
    if (!scan) return [];
    const taken = new Set(rows.filter((r) => r !== row && r.mask).map((r) => r.mask));
    return scan.mask_files
      .map((f) => f.name)
      .filter((name) => !taken.has(name) || name === row.mask);
  };

  // Collapse the current metadata inputs + manifest facts into what travels
  // with a dataset.
  const buildMeta = (): DatasetMetadata => {
    const meta: DatasetMetadata = {};
    for (const [k, v] of Object.entries(metadata)) {
      if (typeof v === "string" && v.trim()) meta[k] = v.trim();
    }
    if (description.trim()) meta.description = description.trim();
    if (notes.trim()) meta.notes = notes.trim();
    const manifestMeta = scan?.dataset_metadata || {};
    if (manifestMeta.label_classes) meta.label_classes = manifestMeta.label_classes;
    if (manifestMeta.channel_names) meta.channel_names = manifestMeta.channel_names;
    if (scan?.split) meta.split = scan.split;
    return meta;
  };

  // Turn the currently-scanned directory into a stageable dataset, or set an
  // error and return null when it is incomplete.
  const buildCurrentEntry = (): StagedDataset | null => {
    if (!scan) {
      setError("Scan a directory first.");
      return null;
    }
    const chosen = rows.filter((r) => r.selected);
    if (chosen.length === 0) {
      setError("Select at least one image to register.");
      return null;
    }
    if (!dataset.trim()) {
      setError("Enter a dataset name for this directory.");
      return null;
    }
    if (!volume.trim()) {
      setError("Enter a volume name for this directory.");
      return null;
    }
    return {
      dataset: dataset.trim(),
      volume: volume.trim(),
      image_directory: imageDir,
      mask_directory: maskDir,
      label_type: labelType,
      metadata: buildMeta(),
      pairs: chosen.map((r) => ({
        image: r.image,
        mask: r.mask || undefined,
        chunk_id: r.chunk_id || undefined,
      })),
    };
  };

  // Is the current form a complete directory ready to stage or register?
  const currentReady =
    !!scan && rows.some((r) => r.selected) && !!dataset.trim() && !!volume.trim();

  // Queue the current directory and reset the form for the next one.
  const stageCurrent = () => {
    setError(null);
    const entry = buildCurrentEntry();
    if (!entry) return;
    setStaged((s) => [...s, entry]);
    resetForAnother();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const removeStaged = (index: number) =>
    setStaged((s) => s.filter((_, i) => i !== index));

  // Register every queued directory plus the current one (if ready) into the
  // chosen project — one dataset per directory, in one action.
  const registerAll = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!projectId) {
      setError("Choose the project to register this data into.");
      return;
    }
    const entries = [...staged];
    if (scan && rows.some((r) => r.selected)) {
      const current = buildCurrentEntry();
      if (!current) return; // validation error already surfaced
      entries.push(current);
    }
    if (entries.length === 0) {
      setError("Add at least one directory to register.");
      return;
    }

    setBusy(true);
    const succeeded: { dataset: string; count: number }[] = [];
    const failed: { dataset: string; message: string }[] = [];
    let lastProjectId = Number(projectId);
    for (const entry of entries) {
      try {
        const res = await registerData({
          dataset: entry.dataset,
          volume: entry.volume,
          project: Number(projectId),
          image_directory: entry.image_directory,
          mask_directory: entry.mask_directory || undefined,
          label_type: entry.label_type,
          metadata: entry.metadata,
          pairs: entry.pairs,
        });
        lastProjectId = res.project.id;
        succeeded.push({ dataset: entry.dataset, count: res.volumes.length });
      } catch (err) {
        failed.push({
          dataset: entry.dataset,
          message: err instanceof Error ? err.message : "registration failed",
        });
      }
    }
    setBusy(false);
    setProjectId(String(lastProjectId));

    // Keep only the directories that failed, so they can be retried.
    const failedNames = new Set(failed.map((f) => f.dataset));
    setStaged((s) => s.filter((d) => failedNames.has(d.dataset)));

    if (succeeded.length > 0) {
      setLastResult(succeeded);
      resetForAnother();
    }
    if (failed.length > 0) {
      setError(
        "Some directories could not be registered: " +
          failed.map((f) => `${f.dataset} (${f.message})`).join("; "),
      );
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const stagedVolumeCount = staged.reduce((n, d) => n + d.pairs.length, 0);
  const registerCount = staged.length + (currentReady ? 1 : 0);

  // Wait for the project list before rendering. A <select> whose value is set
  // (from ?project=) before its <option>s exist cannot match it, and silently
  // falls back to blank — which would drop the preselection handed over by
  // "Create project & register data".
  if (projects.loading) return <p className="muted">Loading…</p>;

  const matchedCount = rows.filter((r) => r.matched).length;
  const imageOnly = rows.length - matchedCount;

  return (
    <>
      <div className="row spread">
        <h1>Register Data</h1>
        <span className="muted">
          {isManager ? "Manager" : "Requester"} · references HPC files (no upload)
        </span>
      </div>
      <p className="muted">
        Point at the folder holding the images and, if the masks live elsewhere,
        the folder holding those. Images and masks are matched by case name — so
        an nnU-Net layout (<code>imagesTr</code> + <code>labelsTr</code>) pairs
        itself. Resolution, shape, and mitochondria counts are read from the files.
        Each directory becomes its own dataset (holding all of its volumes); use{" "}
        <b>+ Add another directory</b> to queue several and register them into
        the same project at once.
      </p>

      {error && <div className="error">{error}</div>}

      {lastResult && lastResult.length > 0 && (
        <div className="card" style={{ borderColor: "var(--ok)" }}>
          <div className="row spread">
            <h3 style={{ margin: 0 }}>
              ✓ Registered {lastResult.length} dataset
              {lastResult.length === 1 ? "" : "s"} (
              {lastResult.reduce((n, d) => n + d.count, 0)} volume
              {lastResult.reduce((n, d) => n + d.count, 0) === 1 ? "" : "s"})
            </h3>
            <div className="row">
              <button
                type="button"
                className="secondary"
                onClick={() => setLastResult(null)}
              >
                Register more
              </button>
              {projectId && (
                <button
                  type="button"
                  onClick={() => navigate(`/projects/${projectId}`)}
                >
                  Go to project →
                </button>
              )}
            </div>
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            {lastResult.map((d) => `${d.dataset} (${d.count})`).join(", ")}. A
            project can hold many datasets — queue more directories below, or open
            the project when you are done.
          </p>
        </div>
      )}

      {staged.length > 0 && (
        <div className="card" style={{ borderColor: "var(--accent)" }}>
          <h3 style={{ marginTop: 0 }}>
            Queued to register · {staged.length} director
            {staged.length === 1 ? "y" : "ies"} / {stagedVolumeCount} volume
            {stagedVolumeCount === 1 ? "" : "s"}
          </h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Source volume</th>
                  <th>Image directory</th>
                  <th>Volumes</th>
                  <th>Label</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {staged.map((d, i) => (
                  <tr key={`${d.dataset}:${i}`}>
                    <td>{d.dataset}</td>
                    <td>{d.volume}</td>
                    <td className="mono-cell">{d.image_directory}</td>
                    <td>{d.pairs.length}</td>
                    <td>{d.label_type}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => removeStaged(i)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            Configure another directory below and add it, or register the queue
            now.
          </p>
        </div>
      )}

      {!hasProjects && (
        <div className="card">
          <h3>Create a project first</h3>
          <p className="muted">
            Data belongs to a project, and you do not have one yet. Projects
            describe the work — what is annotated, by when.
          </p>
          <Link to="/projects/new">
            <button type="button">+ New project</button>
          </Link>
        </div>
      )}

      <form onSubmit={registerAll}>
        <div className="card">
          <h3>Directories</h3>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Image directory *</span>
              <input
                value={imageDir}
                onChange={(e) => {
                  setImageDir(e.target.value);
                  setScan(null);
                }}
                placeholder="/…/nnUNet_raw/Dataset101/imagesTr"
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Mask directory (optional)</span>
              <input
                value={maskDir}
                onChange={(e) => {
                  setMaskDir(e.target.value);
                  setScan(null);
                }}
                placeholder="/…/nnUNet_raw/Dataset101/labelsTr"
              />
            </label>
            <button
              type="button"
              className="secondary"
              onClick={() => runScan(imageDir, maskDir)}
              disabled={scanning || !imageDir.trim()}
              style={{ alignSelf: "flex-end" }}
            >
              {scanning ? "Scanning…" : "Scan"}
            </button>
          </div>
          <p className="muted">
            Leave the mask directory empty for image-only data, or when masks sit
            beside the images in the same folder.
          </p>

          {scan && (scan.suggestions.masks.length > 0 ||
            scan.suggestions.images.length > 0) && (
            <div className="suggestions">
              {scan.suggestions.images.length > 1 && (
                <div className="row" style={{ alignItems: "center" }}>
                  <span className="muted suggest-label">Image sets:</span>
                  {scan.suggestions.images.map((s) => (
                    <button
                      type="button"
                      key={s.path}
                      className={`chip ${s.current ? "chip-active" : ""}`}
                      onClick={() => pickDirectory("image", s)}
                    >
                      {s.name} <span className="chip-count">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
              {scan.suggestions.masks.length > 0 && (
                <div className="row" style={{ alignItems: "center" }}>
                  <span className="muted suggest-label">Label sets:</span>
                  {scan.suggestions.masks.map((s) => (
                    <button
                      type="button"
                      key={s.path}
                      className={`chip ${
                        s.path === scan.mask_directory ? "chip-active" : ""
                      }`}
                      onClick={() => pickDirectory("mask", s)}
                    >
                      {s.name} <span className="chip-count">{s.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {scan && (
          <div className="card">
            <div className="row spread">
              <h3>
                Matched volumes{" "}
                <span className="muted" style={{ fontWeight: 400 }}>
                  ({matchedCount} paired
                  {imageOnly > 0 ? `, ${imageOnly} image-only` : ""})
                </span>
              </h3>
              <div className="row">
                {scan.pairing_source === "dataset.json" ? (
                  <span className="badge badge-green">paired from dataset.json</span>
                ) : (
                  <span className="badge badge-blue">paired by filename</span>
                )}
                {scan.split && (
                  <span className="badge badge-gray">{scan.split} split</span>
                )}
              </div>
            </div>

            {rows.length === 0 && (
              <p className="muted">
                No supported .tif / .tiff / .nii.gz files found in that image
                directory.
              </p>
            )}

            {scan.unmatched_masks.length > 0 && (
              <p className="muted">
                {scan.unmatched_masks.length} mask(s) had no matching image and
                will be ignored: {scan.unmatched_masks.slice(0, 4).join(", ")}
                {scan.unmatched_masks.length > 4 ? "…" : ""}
              </p>
            )}
            {scan.extra_channels.length > 0 && (
              <p className="muted">
                {scan.extra_channels.length} extra channel file(s) ignored;
                channel 0000 represents each volume.
              </p>
            )}

            {rows.length > 0 && (
              <>
                <div className="row spread" style={{ marginTop: "0.75rem" }}>
                  <label className="field" style={{ marginBottom: 0 }}>
                    <span>Label type for masks</span>
                    <select
                      value={labelType}
                      onChange={(e) => setLabelType(e.target.value as LabelType)}
                    >
                      {LABEL_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="row" style={{ alignSelf: "flex-end" }}>
                    <button type="button" className="secondary" onClick={() => setAll(true)}>
                      Select all
                    </button>
                    <button type="button" className="secondary" onClick={() => setAll(false)}>
                      Clear
                    </button>
                  </div>
                </div>

                <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
                  <table>
                    <thead>
                      <tr>
                        <th></th>
                        <th>Volume</th>
                        <th>Mask</th>
                        <th>Rename (optional)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={`${r.image}:${i}`}>
                          <td>
                            <input
                              type="checkbox"
                              checked={r.selected}
                              onChange={() => update(i, { selected: !r.selected })}
                            />
                          </td>
                          <td>
                            <div>
                              {r.case}
                              {!r.matched && (
                                <>
                                  {" "}
                                  <span className="badge badge-gray">no mask</span>
                                </>
                              )}
                            </div>
                            {/* The source file, shown small since the volume name
                                above is just this filename minus its channel
                                suffix — kept only so the exact file is verifiable. */}
                            <div
                              className="muted mono-cell"
                              style={{ fontSize: "0.8em" }}
                            >
                              {r.image}
                            </div>
                          </td>
                          <td>
                            {scan.mask_files.length === 0 ? (
                              <span className="muted">—</span>
                            ) : (
                              <select
                                value={r.mask}
                                disabled={!r.selected}
                                onChange={(e) => update(i, { mask: e.target.value })}
                              >
                                <option value={NO_MASK}>— image only —</option>
                                {freeMasks(r).map((f) => (
                                  <option key={f} value={f}>
                                    {f}
                                  </option>
                                ))}
                              </select>
                            )}
                          </td>
                          <td>
                            <input
                              value={r.chunk_id}
                              disabled={!r.selected}
                              onChange={(e) => update(i, { chunk_id: e.target.value })}
                              placeholder={r.case}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        <div className="card">
          <h3>Project &amp; dataset</h3>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Project *</span>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
              >
                <option value="">— select a project —</option>
                {(projects.data ?? []).map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Dataset name *</span>
              <input
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
                placeholder="e.g. MouseCortex_2024"
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Volume name *</span>
              <input
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
                placeholder="e.g. big_volume_01"
              />
            </label>
          </div>
          <p className="muted">
            Data is registered into an existing project.{" "}
            <Link to="/projects/new">Start a new project</Link> if this is new
            work. A project holds several datasets, and a dataset holds many
            image + mask volume pairs — registering under a dataset name that
            already exists in the chosen project adds these pairs to it.
          </p>
        </div>

        <div className="card">
          <h3>Metadata (optional)</h3>
          <p className="muted">
            Only details that cannot be derived from the files.
            {scan?.manifest_path
              ? " Some fields were prefilled from dataset.json."
              : " All fields are optional."}
          </p>
          <div className="grid">
            {METADATA_FIELDS.map((f) => (
              <label className="field" key={f.key}>
                <span>{f.label}</span>
                <input
                  value={(metadata[f.key] as string) ?? ""}
                  onChange={(e) => setMeta(f.key, e.target.value)}
                />
              </label>
            ))}
          </div>
          <label className="field">
            <span>Description</span>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Notes</span>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
        </div>

        <div className="row spread">
          <button
            type="button"
            className="secondary"
            onClick={stageCurrent}
            disabled={busy || !currentReady}
            title={
              currentReady
                ? "Queue this directory and start another"
                : "Scan a directory and name the dataset first"
            }
          >
            + Add another directory
          </button>
          <button type="submit" disabled={busy || registerCount === 0}>
            {busy
              ? "Registering…"
              : `Register ${registerCount} dataset${
                  registerCount === 1 ? "" : "s"
                }`}
          </button>
        </div>
      </form>
    </>
  );
}
