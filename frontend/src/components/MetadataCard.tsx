import type { DatasetMetadata } from "../types/project";

// Human-readable labels for the optional biomedical metadata fields. Rendered
// in this order; anything else present in the JSON is shown afterwards.
const LABELS: Record<string, string> = {
  organism: "Organism / species",
  tissue: "Tissue or organ",
  cell_type: "Cell type",
  imaging_modality: "Imaging modality",
  imaging_instrument: "Imaging instrument / microscope",
  experimental_condition: "Experimental condition",
  sample_condition: "Sample condition",
  dataset_source: "Dataset source",
  publication: "Publication / reference",
  description: "Description",
  notes: "Notes",
};

export default function MetadataCard({
  metadata,
  title = "Metadata",
}: {
  metadata?: DatasetMetadata | null;
  title?: string;
}) {
  const entries = Object.entries(metadata ?? {}).filter(
    ([, v]) => v !== null && v !== undefined && String(v).trim() !== "",
  );

  const ordered = [
    ...Object.keys(LABELS).filter((k) => k in (metadata ?? {})),
    ...entries.map(([k]) => k).filter((k) => !(k in LABELS)),
  ];
  const seen = new Set<string>();

  return (
    <div className="card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className="muted">No metadata recorded.</p>
      ) : (
        <table>
          <tbody>
            {ordered.map((key) => {
              if (seen.has(key)) return null;
              seen.add(key);
              const value = (metadata ?? {})[key];
              if (value === null || value === undefined || String(value).trim() === "")
                return null;
              return (
                <tr key={key}>
                  <th>{LABELS[key] ?? key.replace(/_/g, " ")}</th>
                  <td>{String(value)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
