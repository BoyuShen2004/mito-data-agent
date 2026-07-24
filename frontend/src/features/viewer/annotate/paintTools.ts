/** Annotate-only paint modes (Cellable-aligned shortcuts). */
export type PaintTool =
  | "select"
  | "brush"
  | "eraser"
  | "box_eraser"
  | "point_mask"
  | "box_mask"
  | "boundary"
  | "seeds";

export const AI_POINT_TOOLS: PaintTool[] = ["point_mask", "boundary"];
export const AI_PREVIEW_TOOLS: PaintTool[] = ["point_mask", "box_mask", "boundary"];
