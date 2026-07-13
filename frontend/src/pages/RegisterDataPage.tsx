import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  scanHpcDirectory,
  registerData,
  type HpcScanResult,
} from "../api/registerData";
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

const NO_MASK = ""; // sentinel for the "image only" mask option

interface Row {
  image: string;
  mask: string; // "" = image only
  chunk_id: string;
  selected: boolean;
  detected: boolean; // was auto-detected as a pair
}

export default function RegisterDataPage() {
  const { isManager } = useAuth();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState("");
  const [volume, setVolume] = useState("");
  const [directory, setDirectory] = useState("");
  const [labelType, setLabelType] = useState<LabelType>("prediction");
  const [metadata, setMetadata] = useState<DatasetMetadata>({});
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");

  const [allFiles, setAllFiles] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [scanned, setScanned] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const setMeta = (key: keyof DatasetMetadata, value: string) =>
    setMetadata((m) => ({ ...m, [key]: value }));

  const buildRows = (res: HpcScanResult): Row[] => {
    const pairRows: Row[] = res.pairs.map((p) => ({
      image: p.image,
      mask: p.mask,
      chunk_id: "",
      selected: true,
      detected: true,
    }));
    const unpairedRows: Row[] = res.unpaired.map((name) => ({
      image: name,
      mask: NO_MASK,
      chunk_id: "",
      selected: true,
      detected: false,
    }));
    return [...pairRows, ...unpairedRows];
  };

  const doScan = async () => {
    setScanning(true);
    setError(null);
    setNotice(null);
    try {
      const res = await scanHpcDirectory(directory);
      setAllFiles(res.files.map((f) => f.name));
      setRows(buildRows(res));
      setScanned(true);
      if (res.files.length === 0) {
        setNotice("No supported .tif / .tiff / .nii.gz files found here.");
      } else {
        setNotice(
          `Found ${res.files.length} file(s): ${res.pairs.length} image+mask ` +
            `pair(s) auto-detected, ${res.unpaired.length} unpaired.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
      setRows([]);
      setAllFiles([]);
      setScanned(false);
    } finally {
      setScanning(false);
    }
  };

  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const setAll = (selected: boolean) =>
    setRows((rs) => rs.map((r) => ({ ...r, selected })));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!scanned) {
      setError("Scan the HPC directory first.");
      return;
    }
    const chosen = rows.filter((r) => r.selected);
    if (chosen.length === 0) {
      setError("Select at least one image (or pair) to register.");
      return;
    }
    const meta: DatasetMetadata = {};
    for (const [k, v] of Object.entries(metadata)) {
      if (typeof v === "string" && v.trim()) meta[k] = v.trim();
    }
    if (description.trim()) meta.description = description.trim();
    if (notes.trim()) meta.notes = notes.trim();

    setBusy(true);
    try {
      const res = await registerData({
        dataset,
        volume,
        hpc_directory: directory,
        label_type: labelType,
        metadata: meta,
        pairs: chosen.map((r) => ({
          image: r.image,
          mask: r.mask || undefined,
          chunk_id: r.chunk_id || undefined,
        })),
      });
      navigate(`/projects/${res.project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="row spread">
        <h1>Register Data</h1>
        <span className="muted">
          {isManager ? "Manager" : "Requester"} · references HPC files (no upload)
        </span>
      </div>
      <p className="muted">
        Register references to <code>.tif</code>, <code>.tiff</code>, and{" "}
        <code>.nii.gz</code> files already on HPC. Image + mask pairs are
        auto-detected; you can also pair files manually or register images alone.
        Resolution, shape, and mitochondria counts are derived from the files.
      </p>

      {error && <div className="error">{error}</div>}
      {notice && <p className="muted">{notice}</p>}

      <form onSubmit={submit}>
        <div className="card">
          <h3>Dataset &amp; volume</h3>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Dataset name *</span>
              <input
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
                placeholder="e.g. MouseCortex_2024"
                required
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Volume name *</span>
              <input
                value={volume}
                onChange={(e) => setVolume(e.target.value)}
                placeholder="e.g. big_volume_01"
                required
              />
            </label>
          </div>
          <p className="muted">
            Multiple chunks/crops (and their masks) from the same source share
            one dataset and volume.
          </p>
        </div>

        <div className="card">
          <h3>HPC directory</h3>
          <div className="row">
            <label className="field" style={{ flex: 1, marginBottom: 0 }}>
              <span>Directory (absolute or relative to the data root)</span>
              <input
                value={directory}
                onChange={(e) => {
                  setDirectory(e.target.value);
                  setScanned(false);
                }}
                placeholder="/hpc/project/volumes or subfolder"
                required
              />
            </label>
            <button
              type="button"
              className="secondary"
              onClick={doScan}
              disabled={scanning || !directory.trim()}
              style={{ alignSelf: "flex-end" }}
            >
              {scanning ? "Scanning…" : "Scan directory"}
            </button>
          </div>

          {scanned && rows.length > 0 && (
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
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setAll(true)}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setAll(false)}
                  >
                    Clear
                  </button>
                </div>
              </div>

              <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
                <table>
                  <thead>
                    <tr>
                      <th></th>
                      <th>Image</th>
                      <th>Mask (label)</th>
                      <th>Chunk / crop id</th>
                      <th></th>
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
                        <td>{r.image}</td>
                        <td>
                          <select
                            value={r.mask}
                            disabled={!r.selected}
                            onChange={(e) => update(i, { mask: e.target.value })}
                          >
                            <option value={NO_MASK}>— image only —</option>
                            {allFiles
                              .filter((f) => f !== r.image)
                              .map((f) => (
                                <option key={f} value={f}>
                                  {f}
                                </option>
                              ))}
                          </select>
                        </td>
                        <td>
                          <input
                            value={r.chunk_id}
                            disabled={!r.selected}
                            onChange={(e) =>
                              update(i, { chunk_id: e.target.value })
                            }
                            placeholder={r.image}
                          />
                        </td>
                        <td>
                          {r.detected ? (
                            <span className="badge badge-green">pair</span>
                          ) : r.mask ? (
                            <span className="badge badge-blue">paired</span>
                          ) : (
                            <span className="badge badge-gray">image</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3>Metadata (optional)</h3>
          <p className="muted">
            Only details that cannot be derived from the files. All fields are
            optional.
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

        <button type="submit" disabled={busy}>
          {busy ? "Registering…" : "Register data"}
        </button>
      </form>
    </>
  );
}
