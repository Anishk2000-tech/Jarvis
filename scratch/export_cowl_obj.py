import sys
sys.path.insert(0, ".")
from pathlib import Path
from scratch.test_cowl_mesh import test_full_build
from core.avatar_mesh import _load_obj, _add_cranium, _add_neck, _OBJ
import numpy as np

def export_obj():
    verts, faces = _load_obj(_OBJ)

    def _add_cowl_ears(v: np.ndarray, f: np.ndarray):
        left_ear_base = [
            [-2.6, 7.2, -0.4],
            [-4.2, 6.9, -0.8],
            [-3.8, 6.4, -1.8],
            [-2.2, 6.7, -1.4],
        ]
        left_apex = [-3.8, 12.8, -1.0]

        right_ear_base = [
            [2.6, 7.2, -0.4],
            [4.2, 6.9, -0.8],
            [3.8, 6.4, -1.8],
            [2.2, 6.7, -1.4],
        ]
        right_apex = [3.8, 12.8, -1.0]

        nv = np.array(left_ear_base + [left_apex] + right_ear_base + [right_apex], dtype=np.float64)
        base = len(v)

        nf = [
            [base + 4, base + 0, base + 1],
            [base + 4, base + 1, base + 2],
            [base + 4, base + 2, base + 3],
            [base + 4, base + 3, base + 0],
            [base + 9, base + 6, base + 5],
            [base + 9, base + 7, base + 6],
            [base + 9, base + 8, base + 7],
            [base + 9, base + 5, base + 8],
        ]
        return np.vstack([v, nv]), np.vstack([f, np.array(nf, dtype=np.int64)])

    verts, faces = _add_cranium(verts, faces)
    verts, faces = _add_cowl_ears(verts, faces)
    verts, faces, _ = _add_neck(verts, faces)

    out_path = Path("core/batman_cowl.obj")
    lines = ["# Batman Cowl 3D Tactical Mesh for Alfred / Mark-LIV\n"]
    for v in verts:
        lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
    for f in faces:
        lines.append(f"f {f[0]+1} {f[1]+1} {f[2]+1}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Exported {out_path} ({len(verts)} verts, {len(faces)} faces)")

if __name__ == "__main__":
    export_obj()
