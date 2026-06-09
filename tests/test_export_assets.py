from __future__ import annotations

import json

import pytest

from rdc_auto.export_assets import ExportService


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_textures":
            return {"textures": [{"resource_id": "101", "name": "Albedo"}]}
        if method == "export_texture_to_file":
            return {"output_path": params["output_path"]}
        if method == "get_draw_calls":
            return {"draws": [{"event_id": 12, "name": "Character"}]}
        if method == "export_mesh_to_file":
            with open(params["output_path"], "w", encoding="utf-8") as handle:
                json.dump({"indices": [0, 1, 2], "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}, handle)
            return {"output_path": params["output_path"]}
        return {}


class MalformedDrawMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_draw_calls":
            return {"draws": [{"event_id": "bad", "name": "Broken"}, {"event_id": 12, "name": "Character"}]}
        if method == "export_mesh_to_file":
            with open(params["output_path"], "w", encoding="utf-8") as handle:
                json.dump({"indices": [0, 1, 2], "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}, handle)
            return {"output_path": params["output_path"]}
        return {}


class InvalidDrawIdMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_draw_calls":
            return {
                "draws": [
                    {"name": "Missing"},
                    {"event_id": 0, "name": "Zero"},
                    {"event_id": -7, "name": "Negative"},
                    {"event_id": 12, "name": "Character"},
                ]
            }
        if method == "export_mesh_to_file":
            with open(params["output_path"], "w", encoding="utf-8") as handle:
                json.dump({"indices": [0, 1, 2], "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}, handle)
            return {"output_path": params["output_path"]}
        return {}


class StrictDrawIdMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_draw_calls":
            return {
                "draws": [
                    {"event_id": 12.7, "name": "Float"},
                    {"event_id": True, "name": "Bool"},
                    {"event_id": 13, "name": "Integer"},
                    {"event_id": "14", "name": "StringInteger"},
                ]
            }
        if method == "export_mesh_to_file":
            with open(params["output_path"], "w", encoding="utf-8") as handle:
                json.dump({"indices": [0, 1, 2], "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}, handle)
            return {"output_path": params["output_path"]}
        return {}


class UnsafeTextureIdMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_textures":
            return {"textures": [{"resource_id": "folder/101", "name": "Albedo"}]}
        if method == "export_texture_to_file":
            return {"output_path": params["output_path"]}
        return {}


def test_export_textures_and_meshes(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(FakeMcp())

    manifest = service.export(rdc, tmp_path / "out", assets="both")

    assert manifest["assets"]["textures"]["success"] == 1
    assert manifest["assets"]["meshes"]["success"] == 1
    texture_call = [call for call in service.mcp.calls if call[0] == "export_texture_to_file"][0]
    assert texture_call[1]["output_path"] == str(tmp_path / "out" / "textures" / "Albedo_101.png")
    assert (tmp_path / "out" / "meshes" / "12_Character.obj").is_file()
    assert (tmp_path / "out" / "manifest.json").is_file()


def test_export_rejects_invalid_asset_type_before_opening_capture(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    mcp = FakeMcp()
    service = ExportService(mcp)

    with pytest.raises(ValueError):
        service.export(rdc, tmp_path / "out", assets="audio")

    assert [call for call in mcp.calls if call[0] == "open_capture"] == []
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_export_records_malformed_draw_and_continues_mesh_export(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(MalformedDrawMcp())

    manifest = service.export(rdc, tmp_path / "out", assets="meshes")

    assert manifest["assets"]["meshes"]["failed"] >= 1
    assert manifest["assets"]["meshes"]["success"] == 1
    assert manifest["failures"][0]["type"] == "mesh"
    assert manifest["failures"][0]["draw"] == {"event_id": "bad", "name": "Broken"}
    assert (tmp_path / "out" / "meshes" / "12_Character.obj").is_file()


def test_export_records_missing_zero_and_negative_draw_ids_as_failures(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(InvalidDrawIdMcp())

    manifest = service.export(rdc, tmp_path / "out", assets="meshes")

    assert manifest["assets"]["meshes"]["failed"] == 3
    assert manifest["assets"]["meshes"]["success"] == 1
    assert [failure["draw"] for failure in manifest["failures"]] == [
        {"name": "Missing"},
        {"event_id": 0, "name": "Zero"},
        {"event_id": -7, "name": "Negative"},
    ]
    assert all(failure["type"] == "mesh" for failure in manifest["failures"])
    assert (tmp_path / "out" / "meshes" / "12_Character.obj").is_file()


def test_export_records_non_integer_numeric_and_bool_draw_ids_as_failures(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    mcp = StrictDrawIdMcp()
    service = ExportService(mcp)

    manifest = service.export(rdc, tmp_path / "out", assets="meshes")

    mesh_export_event_ids = [
        call[1]["event_id"]
        for call in mcp.calls
        if call[0] == "export_mesh_to_file"
    ]
    assert manifest["assets"]["meshes"]["failed"] == 2
    assert manifest["assets"]["meshes"]["success"] == 2
    assert mesh_export_event_ids == [13, 14]
    assert [failure["draw"] for failure in manifest["failures"]] == [
        {"event_id": 12.7, "name": "Float"},
        {"event_id": True, "name": "Bool"},
    ]
    assert not (tmp_path / "out" / "meshes" / "12_Float.obj").exists()
    assert not (tmp_path / "out" / "meshes" / "1_Bool.obj").exists()
    assert (tmp_path / "out" / "meshes" / "13_Integer.obj").is_file()
    assert (tmp_path / "out" / "meshes" / "14_StringInteger.obj").is_file()


def test_export_sanitizes_texture_resource_id_only_for_filename(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(UnsafeTextureIdMcp())

    service.export(rdc, tmp_path / "out", assets="textures")

    texture_call = [call for call in service.mcp.calls if call[0] == "export_texture_to_file"][0]
    assert texture_call[1]["resource_id"] == "folder/101"
    assert texture_call[1]["output_path"] == str(tmp_path / "out" / "textures" / "Albedo_folder_101.png")
    assert not (tmp_path / "out" / "textures" / "Albedo_folder").exists()
