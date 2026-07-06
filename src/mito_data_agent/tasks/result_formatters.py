"""Task-specific chat response formatters."""

from __future__ import annotations


def format_list_local_data(summary: dict) -> str | None:
    inventory = summary.get("local_data_inventory") or {}
    data_dir = inventory.get("data_dir", "unknown")
    volumes = inventory.get("volumes") or []
    lines = [
        f"**Data directory:** `{data_dir}`",
        f"**Volumes found:** {len(volumes)}",
    ]

    if not volumes:
        lines.append("\nNo annotated volumes found.")
    else:
        lines.append("")
        for vol in volumes:
            vol_id = vol.get("volume_id", "unknown")
            lines.append(f"### {vol_id}")
            if vol.get("raw_file_path"):
                lines.append(f"- **Raw:** `{vol['raw_file_path']}`")
                if vol.get("raw_shape_xyz"):
                    lines.append(f"  - Shape (x,y,z): {vol['raw_shape_xyz']}")
            if vol.get("label_file_path"):
                lines.append(f"- **Label:** `{vol['label_file_path']}`")
                if vol.get("label_shape_xyz"):
                    lines.append(f"  - Shape (x,y,z): {vol['label_shape_xyz']}")
                if vol.get("num_mito") is not None:
                    lines.append(f"  - # Mito (non-zero labels): {vol['num_mito']}")
            for w in vol.get("warnings") or []:
                lines.append(f"  - ⚠ {w}")

    unpaired = inventory.get("unpaired_files") or []
    if unpaired:
        lines.append("\n**Unpaired files:**")
        for path in unpaired:
            lines.append(f"- `{path}`")

    if summary.get("execution_report_path"):
        lines.append(f"\n**Report:** `{summary['execution_report_path']}`")

    warnings = summary.get("warnings", [])
    dir_warnings = inventory.get("warnings") or []
    all_warnings = dir_warnings + [w for w in warnings if w not in dir_warnings]
    if all_warnings:
        lines.append(f"\n**Warnings ({len(all_warnings)}):**")
        for w in all_warnings[:8]:
            lines.append(f"- {w}")

    lines.append("\n_Local inventory — scan only._")
    return "\n".join(lines)
