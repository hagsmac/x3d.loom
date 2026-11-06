"""A generated studio environment for the look-v2 Site scenes: six cube-map faces (PNG), no photograph, no download.

  python3 -I kit/examples/zinc_studio_env.py OUT_DIR [SIZE]

Defined in the camera's frame (the viewer looks down -Z): a warm softbox up and to the left on the viewer's side,
a dim cool panel to the right, a warm rim strip behind the subject, over a dark navy room that is darker below. The
scene's EnvironmentLight rotates it by the first Viewpoint's orientation, so the highlights face the camera. It is
look, not data. Deterministic: the same SIZE always writes the same bytes.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# face -> (forward, right, up) in the cube's frame (X3D: front faces -Z, back +Z, left -X, right +X, top +Y, bottom -Y)
FACES = {"front": ((0, 0, -1), (1, 0, 0), (0, 1, 0)), "back": ((0, 0, 1), (-1, 0, 0), (0, 1, 0)),
         "left": ((-1, 0, 0), (0, 0, -1), (0, 1, 0)), "right": ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
         "top": ((0, 1, 0), (1, 0, 0), (0, 0, 1)), "bottom": ((0, -1, 0), (1, 0, 0), (0, 0, -1))}
LIGHTS = [  # direction (towards the light), colour, angular radius (rad), softness (rad)
    ((-0.5, 0.6, 0.62), (1.0, 0.95, 0.86), 0.42, 0.22),   # key softbox, viewer's side, upper left
    ((0.0, 1.0, 0.1), (0.75, 0.85, 0.95), 0.5, 0.35),     # overhead panel
    ((0.75, -0.05, 0.5), (0.35, 0.62, 0.85), 0.35, 0.3),  # cool fill panel, right
    ((0.35, 0.45, -0.82), (1.0, 0.72, 0.4), 0.18, 0.12),  # warm rim strip, behind
]


def face(size, fwd, right, up):
    s = (np.arange(size) + 0.5) / size * 2 - 1
    u, v = np.meshgrid(s, -s)  # image top is +up
    d = np.stack([fwd[i] + u * right[i] + v * up[i] for i in range(3)], -1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    y = d[..., 1:2]
    room = np.where(y > 0, 0.10 + 0.12 * y, 0.06 + 0.03 * y) * np.array([0.55, 0.85, 1.0])
    img = room.copy()
    for ld, col, rad, soft in LIGHTS:
        ld = np.array(ld) / np.linalg.norm(ld)
        ang = np.arccos(np.clip(d @ ld, -1, 1))[..., None]
        w = np.clip((rad + soft - ang) / soft, 0, 1) ** 2
        img += w * np.array(col)
    img = np.clip(img, 0, 1) ** (1 / 2.2)
    return Image.fromarray((img * 255 + 0.5).astype(np.uint8), "RGB")


if __name__ == "__main__":
    out = Path(sys.argv[1]); size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    out.mkdir(parents=True, exist_ok=True)
    for name, (f, r, u) in FACES.items():
        face(size, f, r, u).save(out / f"studio-{name}.png", optimize=True)
    print(f"wrote 6 faces of {size}px to {out}")
