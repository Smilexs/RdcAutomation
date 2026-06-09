from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def _fmt(values: Iterable[float]) -> str:
    return " ".join(f"{float(value):g}" for value in values)


def _validate_mesh(
    positions: list,
    normals: list,
    uvs: list,
    indices: list,
) -> None:
    if len(indices) % 3 != 0:
        raise ValueError("indices length must be a multiple of 3")

    for raw_index in indices:
        index = int(raw_index)
        if index < 0 or index >= len(positions):
            raise ValueError(f"position index {index} is out of range")
        if uvs and index >= len(uvs):
            raise ValueError(f"UV index {index} is out of range")
        if normals and index >= len(normals):
            raise ValueError(f"normal index {index} is out of range")


def convert_mesh_json_to_obj(
    source_json: str | Path,
    obj_path: str | Path,
    mtl_path: str | Path,
    material_name: str,
) -> None:
    source_json = Path(source_json)
    obj_path = Path(obj_path)
    mtl_path = Path(mtl_path)
    data = json.loads(source_json.read_text(encoding="utf-8"))

    positions = data.get("position") or data.get("positions") or []
    normals = data.get("normal") or data.get("normals") or []
    uvs = data.get("uv0") or data.get("uv") or []
    indices = data.get("indices") or []

    _validate_mesh(positions, normals, uvs, indices)

    obj_path.parent.mkdir(parents=True, exist_ok=True)
    mtl_path.parent.mkdir(parents=True, exist_ok=True)

    with mtl_path.open("w", encoding="utf-8", newline="\n") as mtl:
        mtl.write(f"newmtl {material_name}\n")
        mtl.write("Kd 0.8 0.8 0.8\n")
        mtl.write("Ka 0.0 0.0 0.0\n")
        mtl.write("Ks 0.0 0.0 0.0\n")

    with obj_path.open("w", encoding="utf-8", newline="\n") as obj:
        obj.write(f"mtllib {mtl_path.name}\n")
        obj.write(f"usemtl {material_name}\n")
        for pos in positions:
            obj.write(f"v {_fmt(pos[:3])}\n")
        for uv in uvs:
            obj.write(f"vt {_fmt(uv[:2])}\n")
        for normal in normals:
            obj.write(f"vn {_fmt(normal[:3])}\n")

        for offset in range(0, len(indices), 3):
            tri = indices[offset : offset + 3]
            if len(tri) != 3:
                continue
            face = []
            for raw_index in tri:
                idx = int(raw_index) + 1
                vt = idx if uvs else ""
                vn = idx if normals else ""
                if uvs and normals:
                    face.append(f"{idx}/{vt}/{vn}")
                elif uvs:
                    face.append(f"{idx}/{vt}")
                elif normals:
                    face.append(f"{idx}//{vn}")
                else:
                    face.append(str(idx))
            obj.write("f " + " ".join(face) + "\n")
