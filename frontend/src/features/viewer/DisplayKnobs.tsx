import { clampPct } from "./displayAdjust";
import CommitNumberInput from "./CommitNumberInput";

interface Props {
  brightness: number;
  contrast: number;
  onBrightness: (n: number) => void;
  onContrast: (n: number) => void;
  /** Committed-label overlay opacity, 0–100 (100 = fully opaque, Cellable's
   * `label_opacity_slider` default) — #29 item U5. Optional so other
   * DisplayKnobs consumers (if any appear later) aren't forced to wire it. */
  labelOpacity?: number;
  onLabelOpacity?: (n: number) => void;
}

/** Labeled brightness/contrast (+ optional label opacity): slider + typeable 0–100% (50% = normal, opacity 100% = normal). */
export default function DisplayKnobs({
  brightness,
  contrast,
  onBrightness,
  onContrast,
  labelOpacity,
  onLabelOpacity,
}: Props) {
  return (
    <div className="display-knobs">
      <label className="display-knob" title="Brightness (0–100%, 50% is normal)">
        <span className="display-knob-label">Brightness</span>
        <input
          type="range"
          min={0}
          max={100}
          value={brightness}
          onChange={(e) => onBrightness(Number(e.target.value))}
        />
        <CommitNumberInput
          value={brightness}
          min={0}
          max={100}
          suffix="%"
          title="Brightness percent"
          onCommit={(n) => onBrightness(clampPct(n))}
        />
      </label>
      <label className="display-knob" title="Contrast (0–100%, 50% is normal)">
        <span className="display-knob-label">Contrast</span>
        <input
          type="range"
          min={0}
          max={100}
          value={contrast}
          onChange={(e) => onContrast(Number(e.target.value))}
        />
        <CommitNumberInput
          value={contrast}
          min={0}
          max={100}
          suffix="%"
          title="Contrast percent"
          onCommit={(n) => onContrast(clampPct(n))}
        />
      </label>
      {labelOpacity != null && onLabelOpacity && (
        <label className="display-knob" title="Committed label overlay opacity (0–100%, 100% is fully opaque)">
          <span className="display-knob-label">Label opacity</span>
          <input
            type="range"
            min={0}
            max={100}
            value={labelOpacity}
            onChange={(e) => onLabelOpacity(Number(e.target.value))}
          />
          <CommitNumberInput
            value={labelOpacity}
            min={0}
            max={100}
            suffix="%"
            title="Label opacity percent"
            onCommit={(n) => onLabelOpacity(clampPct(n))}
          />
        </label>
      )}
    </div>
  );
}
