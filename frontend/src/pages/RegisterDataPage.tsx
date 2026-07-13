import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  scanHpcDirectory,
  registerData,
  type HpcFile,
} from "../api/registerData";
import type { DatasetMetadata } from "../types/project";

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

interface SelectedFile {
  file: HpcFile;
  selected: boolean;
  chunk_id: string;
}

export default function RegisterDataPage() {
  const { isManager } = useAuth();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState("");
  const [volume, setVolume] = useState("");
  const [directory, setDirectory] = useState("");
  const [metadata, setMetadata] = useState<DatasetMetadata>({});
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");

  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [scanned, setScanned] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const setMeta = (key: keyof DatasetMetadata, value: string) =>
    setMetadata((m) => ({ ...m, [key]: value }));

  const doScan = async () => {
    setScanning(true);
    setError(null);
    setNotice(null);
    try {
      const res = await scanHpcDirectory(directory);
      setFiles(
        res.files.map((f) => ({ file: f, selected: true, chunk_id: "" })),
      );
      setScanned(true);
      if (res.files.length === 0) {
        setNotice("No supported .tif / .tiff / .nii.gz files found here.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
      setFiles([]);
      setScanned(false);
    } finally {
      setScanning(false);
    }
  };

  const toggle = (i: number) =>
    setFiles((fs) =>
      fs.map((f, idx) => (idx === i ? { ...f, selected: !f.selected } : f)),
    );

  const setChunkId = (i: number, value: string) =>
    setFiles((fs) =>
      fs.map((f, idx) => (idx === i ? { ...f, chunk_id: value } : f)),
    );

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    const chosen = files.filter((f) => f.selected);
    if (!scanned) {
      setError("Scan the HPC directory first.");
      return;
    }
    if (chosen.length === 0) {
      setError("Select at least one file to register.");
      return;
    }
    // Clean, non-empty metadata only.
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
        metadata: meta,
        files: chosen.map((f) => ({
          name: f.file.name,
          chunk_id: f.chunk_id || undefined,
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
        <code>.nii.gz</code> files already stored on HPC. Resolution, shape, and
        mitochondria counts are derived from the files automatically.
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
            Multiple chunks/crops from the same source share one dataset and
            volume.
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

          {scanned && files.length > 0 && (
            <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
              <table>
                <thead>
                  <tr>
                    <th></th>
                    <th>File</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th>Chunk / crop id (optional)</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f, i) => (
                    <tr key={f.file.name}>
                      <td>
                        <input
                          type="checkbox"
                          checked={f.selected}
                          onChange={() => toggle(i)}
                        />
                      </td>
                      <td>{f.file.name}</td>
                      <td>{f.file.extension}</td>
                      <td>{f.file.size} B</td>
                      <td>
                        <input
                          value={f.chunk_id}
                          onChange={(e) => setChunkId(i, e.target.value)}
                          placeholder={f.file.name}
                          disabled={!f.selected}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
