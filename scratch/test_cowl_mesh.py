import sys
sys.path.insert(0, ".")
import numpy as np
from pathlib import Path
from core.avatar_mesh import (
    _load_obj, _add_cranium, _add_neck, _OBJ, _check_landmarks,
    _vertex_normals, _unique_edges, LANDMARKS, _WIRE_STRIDE, _NECK_Z
)

def test_full_build():
    verts, faces = _load_obj(_OBJ)
    _check_landmarks(verts)
    n_face = len(verts)

    # Cowl Ears
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
    n_head = len(verts)
    verts, faces, fade = _add_neck(verts, faces)

    head_y = verts[:n_head, 1]
    crown, chin = head_y.max(), head_y.min()
    scale = 2.0 / (crown - chin)
    centre = np.array([0.0, (crown + chin) * 0.5, 0.0])
    verts = (verts - centre) * scale

    outward = verts - np.array([0.0, verts[:n_head, 1].mean(), 0.0])
    outward[n_head:] = verts[n_head:] - np.array([0.0, 0.0, _NECK_Z * scale])
    outward[n_head:, 1] = 0.0
    normals = _vertex_normals(verts, faces, outward)

    mouth_y = verts[LANDMARKS["lips_out"], 1].mean()
    chin_y = verts[:n_head, 1].min()
    jaw = np.clip((mouth_y - verts[:, 1]) / (mouth_y - chin_y), 0.0, 1.0) ** 0.8
    jaw *= np.clip(0.30 + 0.85 * (verts[:, 2] / 0.55), 0.0, 1.0)
    jaw[n_head:] = 0.0
    jaw[LANDMARKS["lips_in"][:10]] = 1.0
    jaw[LANDMARKS["lips_out"][:10]] = 0.95

    brow_y = verts[LANDMARKS["brow_l"] + LANDMARKS["brow_r"], 1].mean()
    brow = np.exp(-((verts[:, 1] - brow_y) / 0.115) ** 2)
    brow *= np.clip(verts[:, 2] / 0.35, 0.0, 1.0)
    brow *= np.exp(-(verts[:, 0] / 0.42) ** 2)
    brow[n_head:] = 0.0

    lip_c = verts[LANDMARKS["lips_out"]].mean(axis=0)
    lips = np.exp(-((verts[:, 1] - lip_c[1]) / 0.155) ** 2)
    lips *= np.exp(-(verts[:, 0] / 0.30) ** 2)
    lips *= np.clip(verts[:, 2] / 0.40, 0.0, 1.0)
    lips[n_head:] = 0.0

    edges = _unique_edges(faces)[::_WIRE_STRIDE]
    face_group = (faces >= n_head).all(axis=1).astype(np.int32)

    res = {
        "face_group": np.ascontiguousarray(1 - face_group, dtype=np.float32),
        "verts": np.ascontiguousarray(verts, dtype=np.float32),
        "normals": np.ascontiguousarray(normals, dtype=np.float32),
        "faces": np.ascontiguousarray(faces, dtype=np.int32),
        "edges": np.ascontiguousarray(edges, dtype=np.int32),
    }
    print("Full mesh build success! Verts:", len(res["verts"]), "Faces:", len(res["faces"]), "Edges:", len(res["edges"]))

if __name__ == "__main__":
    test_full_build()
