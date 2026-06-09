from __future__ import annotations

import json

import pytest

from rdc_auto.mesh_convert import convert_mesh_json_to_obj


def test_convert_mesh_json_to_obj_and_mtl(tmp_path):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, 2],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "normal": [[0, 0, 1], [0, 0, 1], [0, 0, 1]],
                "uv0": [[0, 0], [1, 0], [0, 1]],
            }
        ),
        encoding="utf-8",
    )
    obj = tmp_path / "mesh.obj"
    mtl = tmp_path / "mesh.mtl"

    convert_mesh_json_to_obj(source, obj, mtl, material_name="mat_001")

    obj_text = obj.read_text(encoding="utf-8")
    mtl_text = mtl.read_text(encoding="utf-8")
    assert "mtllib mesh.mtl" in obj_text
    assert "usemtl mat_001" in obj_text
    assert "v 1 0 0" in obj_text
    assert "vn 0 0 1" in obj_text
    assert "vt 1 0" in obj_text
    assert "f 1/1/1 2/2/2 3/3/3" in obj_text
    assert "newmtl mat_001" in mtl_text


def test_convert_mesh_json_to_obj_rejects_missing_uv_for_referenced_index(tmp_path):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, 2],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "normal": [[0, 0, 1], [0, 0, 1], [0, 0, 1]],
                "uv0": [[0, 0]],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="UV index"):
        convert_mesh_json_to_obj(
            source,
            tmp_path / "mesh.obj",
            tmp_path / "mesh.mtl",
            material_name="mat_001",
        )


def test_convert_mesh_json_to_obj_rejects_missing_normal_for_referenced_index(tmp_path):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, 2],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "normal": [[0, 0, 1]],
                "uv0": [[0, 0], [1, 0], [0, 1]],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="normal index"):
        convert_mesh_json_to_obj(
            source,
            tmp_path / "mesh.obj",
            tmp_path / "mesh.mtl",
            material_name="mat_001",
        )


def test_convert_mesh_json_to_obj_rejects_malformed_index_count(tmp_path):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, 2, 0],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="multiple of 3"):
        convert_mesh_json_to_obj(
            source,
            tmp_path / "mesh.obj",
            tmp_path / "mesh.mtl",
            material_name="mat_001",
        )


@pytest.mark.parametrize("bad_index", [-1, 3])
def test_convert_mesh_json_to_obj_rejects_invalid_position_index(tmp_path, bad_index):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, bad_index],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="position index"):
        convert_mesh_json_to_obj(
            source,
            tmp_path / "mesh.obj",
            tmp_path / "mesh.mtl",
            material_name="mat_001",
        )
