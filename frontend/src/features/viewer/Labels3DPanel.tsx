import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fetchLabels3D } from "../../api/viewer";
import { labelColor } from "./labelColor";

// Cellable-parity 3D labels view — plays the role `VTKSurfaceWidget` plays
// locally (Qt + VTK marching-cubes iso-surfaces), reimplemented for the
// browser. See `backend/annotation/cellable_port/labels_3d.py`'s docstring
// for why this renders block-max-pooled surface voxels as instanced cubes
// rather than a true marching-cubes mesh.
export default function Labels3DPanel({
  taskId,
  labelIds,
  refreshKey,
  swapped,
  onToggleSwap,
}: {
  taskId: number;
  labelIds: number[];
  refreshKey: number;
  swapped?: boolean;
  onToggleSwap?: () => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const groupRef = useRef<THREE.Group | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "empty" | "error">("empty");
  const [stats, setStats] = useState<{ labels: number; voxels: number } | null>(null);

  // Scene / camera / renderer — once per mount (layout so groupRef is ready
  // before the fetch effect below runs on the same commit).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0d10);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    camera.position.set(80, 80, 80);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const light = new THREE.DirectionalLight(0xffffff, 1.1);
    light.position.set(1, 1.4, 0.6);
    scene.add(light);
    scene.add(new THREE.AmbientLight(0xffffff, 0.45));
    scene.add(new THREE.GridHelper(200, 20, 0x334155, 0x1f2937));

    const group = new THREE.Group();
    scene.add(group);
    groupRef.current = group;

    let frame = 0;
    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const tick = () => {
      frame = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      groupRef.current = null;
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
    };
  }, []);

  // Fetch + rebuild meshes when the pin set / refresh token changes.
  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    let cancelled = false;

    const clearGroup = () => {
      while (group.children.length) {
        const child = group.children.pop()!;
        group.remove(child);
        if (child instanceof THREE.Mesh) {
          child.geometry.dispose();
          const mat = child.material;
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else mat.dispose();
        }
      }
    };

    const load = async () => {
      if (labelIds.length === 0) {
        clearGroup();
        if (!cancelled) {
          setStatus("empty");
          setStats(null);
        }
        return;
      }
      setStatus("loading");
      try {
        const data = await fetchLabels3D(taskId, labelIds);
        if (cancelled) return;
        clearGroup();
        const [dz, dy, dx] = data.shape;
        let voxelCount = 0;
        let labelCount = 0;
        for (const [id, grid] of data.grids) {
          const voxels = surfaceVoxels(grid, dz, dy, dx);
          voxelCount += voxels.length;
          if (voxels.length === 0) continue;
          labelCount += 1;
          const geometry = new THREE.BoxGeometry(1, 1, 1);
          const [r, g, b] = labelColor(id);
          const material = new THREE.MeshLambertMaterial({
            color: new THREE.Color(r / 255, g / 255, b / 255),
            transparent: true,
            opacity: 0.85,
          });
          const mesh = new THREE.InstancedMesh(geometry, material, voxels.length);
          const dummy = new THREE.Object3D();
          voxels.forEach(([z, y, x], i) => {
            dummy.position.set(x - dx / 2, -(y - dy / 2), z - dz / 2);
            dummy.updateMatrix();
            mesh.setMatrixAt(i, dummy.matrix);
          });
          mesh.instanceMatrix.needsUpdate = true;
          group.add(mesh);
        }
        setStats({ labels: labelCount, voxels: voxelCount });
        setStatus("idle");
      } catch {
        if (!cancelled) setStatus("error");
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [taskId, labelIds, refreshKey]);

  const statusText =
    status === "loading"
      ? "Loading…"
      : status === "empty"
        ? "No labels selected"
        : status === "error"
          ? "Preview failed"
          : stats
            ? `${stats.labels} label(s) · ${stats.voxels} shapes`
            : "No labels selected";

  return (
    <div className="card labels-3d-panel">
      <div className="row spread labels-3d-header">
        <h3 style={{ margin: 0 }}>3D Labels</h3>
        <span className="muted labels-3d-status">{statusText}</span>
        {onToggleSwap && (
          <button
            type="button"
            className="secondary labels-3d-swap"
            title={
              swapped
                ? "Swap back — restore the editable 2D canvas to the center"
                : "Swap — enlarge 3D (2D editing pauses until you swap back)"
            }
            onClick={onToggleSwap}
          >
            Swap
          </button>
        )}
      </div>
      <div ref={containerRef} className="labels-3d-view" />
    </div>
  );
}

/** Voxels of `grid` that have at least one empty/out-of-bounds 6-neighbour. */
function surfaceVoxels(
  grid: Uint8Array,
  dz: number,
  dy: number,
  dx: number,
): [number, number, number][] {
  const at = (z: number, y: number, x: number) =>
    z >= 0 && z < dz && y >= 0 && y < dy && x >= 0 && x < dx
      ? grid[(z * dy + y) * dx + x]
      : 0;
  const out: [number, number, number][] = [];
  for (let z = 0; z < dz; z++) {
    for (let y = 0; y < dy; y++) {
      for (let x = 0; x < dx; x++) {
        if (!at(z, y, x)) continue;
        if (
          !at(z - 1, y, x) ||
          !at(z + 1, y, x) ||
          !at(z, y - 1, x) ||
          !at(z, y + 1, x) ||
          !at(z, y, x - 1) ||
          !at(z, y, x + 1)
        ) {
          out.push([z, y, x]);
        }
      }
    }
  }
  return out;
}
