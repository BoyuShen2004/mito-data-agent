import { useState } from "react";
import { Link } from "react-router-dom";
import {
  datasetDependents,
  deleteDataset,
  updateDataset,
  type Dataset,
} from "../api/datasets";
import type { DatasetMetadata } from "../types/project";
import type { Volume } from "../types/volume";
import { METADATA_FIELDS } from "../metadataFields";
import DeleteButton from "./DeleteButton";
import MetadataCard from "./MetadataCard";

/** The datasets in a project, each with the volume pairs registered under it. */
export default function DatasetsCard({
  datasets,
  volumes,
  onChanged,
}: {
  datasets: Dataset[];
  volumes: Volume[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);

  if (datasets.length === 0) {
    return (
      <div className="card">
        <h3>Datasets</h3>
        <p className="muted">
          No datasets yet. <Link to="/register-data">Register data</Link> to add
          one.
        </p>
      </div>
    );
  }

  return (
    <>
      {datasets.map((ds) => {
        // Volumes registered before datasets existed have no dataset link;
        // show them under the dataset only when they genuinely belong to it.
        const own = volumes.filter((v) => v.dataset === ds.id);
        return (
          <div className="card" key={ds.id}>
            <div className="row spread">
              <h3>
                {ds.name}{" "}
                <span className="muted" style={{ fontWeight: 400 }}>
                  · {own.length} volume pair{own.length === 1 ? "" : "s"}
                </span>
              </h3>
              <div className="row">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditing(editing === ds.id ? null : ds.id)}
                >
                  {editing === ds.id ? "Close" : "Edit"}
                </button>
                <DeleteButton
                  label={`dataset "${ds.name}"`}
                  dependents={() => datasetDependents(ds.id)}
                  onDelete={(force) => deleteDataset(ds.id, force)}
                  onDone={onChanged}
                />
              </div>
            </div>

            {ds.description && <p className="muted">{ds.description}</p>}
            <p className="muted mono-cell">
              images: {ds.image_directory || "—"}
              {ds.mask_directory ? ` · masks: ${ds.mask_directory}` : ""}
            </p>

            {editing === ds.id && (
              <DatasetEditForm
                dataset={ds}
                onSaved={() => {
                  setEditing(null);
                  onChanged();
                }}
              />
            )}

            {Object.keys(ds.metadata || {}).length > 0 && (
              <MetadataCard metadata={ds.metadata} title="Dataset metadata" />
            )}

            {own.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Volume pair</th>
                      <th>Label</th>
                      <th>Shape (z,y,x)</th>
                      <th>Voxel (z,y,x)</th>
                      <th>Tasks</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {own.map((v) => (
                      <tr key={v.id}>
                        <td>{v.name}</td>
                        <td>{v.has_label ? v.label_type : "—"}</td>
                        <td>
                          {v.shape_z ?? "?"},{v.shape_y ?? "?"},{v.shape_x ?? "?"}
                        </td>
                        <td>
                          {v.voxel_size_z != null ||
                          v.voxel_size_y != null ||
                          v.voxel_size_x != null
                            ? `${v.voxel_size_z ?? "?"},${v.voxel_size_y ?? "?"},${v.voxel_size_x ?? "?"}`
                            : "—"}
                        </td>
                        <td>{v.task_count}</td>
                        <td>
                          <Link to={`/volumes/${v.id}`}>Open</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

function DatasetEditForm({
  dataset,
  onSaved,
}: {
  dataset: Dataset;
  onSaved: () => void;
}) {
  const [name, setName] = useState(dataset.name);
  const [description, setDescription] = useState(dataset.description);
  const [imageDir, setImageDir] = useState(dataset.image_directory);
  const [maskDir, setMaskDir] = useState(dataset.mask_directory);
  const [meta, setMeta] = useState<DatasetMetadata>(dataset.metadata ?? {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      // Send blanks as null so clearing a field removes it server-side
      // rather than merging an empty string back in.
      const cleaned: DatasetMetadata = {};
      for (const f of METADATA_FIELDS) {
        const value = meta[f.key];
        cleaned[f.key] =
          typeof value === "string" && value.trim() ? value.trim() : null;
      }
      await updateDataset(dataset.id, {
        name,
        description,
        image_directory: imageDir,
        mask_directory: maskDir,
        metadata: cleaned,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="edit-form">
      {error && <div className="error">{error}</div>}
      <div className="row">
        <label className="field" style={{ flex: 1 }}>
          <span>Dataset name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 2 }}>
          <span>Description</span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
      </div>
      <div className="row">
        <label className="field" style={{ flex: 1 }}>
          <span>Image directory</span>
          <input value={imageDir} onChange={(e) => setImageDir(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Mask directory</span>
          <input value={maskDir} onChange={(e) => setMaskDir(e.target.value)} />
        </label>
      </div>
      <div className="grid">
        {METADATA_FIELDS.map((f) => (
          <label className="field" key={String(f.key)}>
            <span>{f.label}</span>
            <input
              value={(meta[f.key] as string) ?? ""}
              onChange={(e) =>
                setMeta((m) => ({ ...m, [f.key]: e.target.value }))
              }
            />
          </label>
        ))}
      </div>
      <button type="button" onClick={save} disabled={busy}>
        {busy ? "Saving…" : "Save dataset"}
      </button>
    </div>
  );
}
