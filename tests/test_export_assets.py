from __future__ import annotations

import json
from pathlib import Path

import pytest

from rdc_auto.errors import McpCapabilityMissing
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


def test_export_meshes_retries_position_only_when_mcp_optional_slots_fail(tmp_path):
    class OptionalSlotFailureMcp(FakeMcp):
        def __init__(self):
            super().__init__()
            self.export_calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            self.calls.append((method, params, timeout))
            if method == "open_capture":
                return {"success": True}
            if method == "get_draw_calls":
                return {"draws": [{"event_id": 184, "name": "vkCmdDrawIndexed()"}]}
            if method == "export_mesh_to_file":
                self.export_calls.append(params)
                if len(self.export_calls) == 1:
                    raise RuntimeError("IndexError: list index out of range")
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            return {}

    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    mcp = OptionalSlotFailureMcp()
    service = ExportService(mcp)

    manifest = service.export(rdc, tmp_path / "out", assets="meshes")

    raw_json = tmp_path / "out" / "raw_mesh_json" / "184_vkCmdDrawIndexed.json"
    assert manifest["assets"]["meshes"] == {"success": 1, "failed": 0}
    assert mcp.export_calls == [
        {"event_id": 184, "output_path": str(raw_json)},
        {
            "event_id": 184,
            "output_path": str(raw_json),
            "normal_slot": 999,
            "tangent_slot": 999,
            "uv0_slot": 999,
            "uv1_slot": 999,
            "extra_slot": 999,
        },
    ]


def test_export_sanitizes_texture_resource_id_only_for_filename(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(UnsafeTextureIdMcp())

    service.export(rdc, tmp_path / "out", assets="textures")

    texture_call = [call for call in service.mcp.calls if call[0] == "export_texture_to_file"][0]
    assert texture_call[1]["resource_id"] == "folder/101"
    assert texture_call[1]["output_path"] == str(tmp_path / "out" / "textures" / "Albedo_folder_101.png")
    assert not (tmp_path / "out" / "textures" / "Albedo_folder").exists()


def test_list_draw_calls_returns_event_rows(tmp_path):
    class FakeMcp:
        def __init__(self):
            self.calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            self.calls.append((method, params, timeout))
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"draws": [{"event_id": 1203, "name": "Character.Draw"}]}
            raise AssertionError(method)

    mcp = FakeMcp()
    rows = ExportService(mcp).list_draw_calls(tmp_path / "capture.rdc")

    assert rows == [{"event_id": 1203, "name": "Character.Draw"}]
    assert mcp.calls == [
        ("open_capture", {"capture_path": str(tmp_path / "capture.rdc")}, 120.0),
        ("get_draw_calls", {"include_children": True, "only_actions": True}, 60.0),
    ]


def test_list_draw_calls_accepts_renderdoc_mcp_actions_response(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {
                    "actions": [
                        {
                            "event_id": 1203,
                            "name": "Character.Draw",
                            "flags": ["Drawcall", "Indexed"],
                            "num_indices": 36,
                        }
                    ]
                }
            raise AssertionError(method)

    rows = ExportService(FakeMcp()).list_draw_calls(tmp_path / "capture.rdc")

    assert rows == [
        {
            "event_id": 1203,
            "name": "Character.Draw",
            "flags": ["Drawcall", "Indexed"],
            "num_indices": 36,
            "has_mesh": True,
        }
    ]


def test_list_draw_calls_preserves_asset_metadata_when_available(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {
                    "draws": [
                        {
                            "event_id": 1203,
                            "name": "Character.Draw",
                            "has_mesh": True,
                            "texture_count": 4,
                        }
                    ]
                }
            raise AssertionError(method)

    rows = ExportService(FakeMcp()).list_draw_calls(tmp_path / "capture.rdc")

    assert rows == [{"event_id": 1203, "name": "Character.Draw", "has_mesh": True, "texture_count": 4}]


def test_export_mesh_for_event_writes_obj(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"actions": [{"event_id": 1203, "name": "Character.Draw", "flags": ["Drawcall"], "num_indices": 3}]}
            if method == "export_mesh_to_file":
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    result = ExportService(FakeMcp()).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)

    assert result["event_id"] == 1203
    assert Path(result["obj_path"]).is_file()


def test_export_mesh_for_event_rejects_event_id_not_in_current_capture(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"actions": [{"event_id": 99, "name": "Other.Draw", "flags": ["Drawcall"], "num_indices": 3}]}
            if method == "export_mesh_to_file":
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    with pytest.raises(ValueError, match="EID 1203 was not found"):
        ExportService(FakeMcp()).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)


def test_export_mesh_for_event_retries_position_only_when_mcp_optional_slots_fail(tmp_path):
    class FakeMcp:
        def __init__(self):
            self.export_calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"actions": [{"event_id": 184, "name": "vkCmdDrawIndexed()", "flags": ["Drawcall"], "num_indices": 243}]}
            if method == "export_mesh_to_file":
                self.export_calls.append(params)
                if len(self.export_calls) == 1:
                    raise RuntimeError("list index out of range")
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    mcp = FakeMcp()
    result = ExportService(mcp).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 184)

    assert Path(result["obj_path"]).is_file()
    assert mcp.export_calls == [
        {"event_id": 184, "output_path": str(tmp_path / "out" / "raw_mesh_json" / "184_eid.json")},
        {
            "event_id": 184,
            "output_path": str(tmp_path / "out" / "raw_mesh_json" / "184_eid.json"),
            "normal_slot": 999,
            "tangent_slot": 999,
            "uv0_slot": 999,
            "uv1_slot": 999,
            "extra_slot": 999,
        },
    ]


def test_export_mesh_for_event_infers_uv_slot_from_two_component_input(tmp_path):
    class FakeMcp:
        def __init__(self):
            self.export_calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"actions": [{"event_id": 184, "name": "vkCmdDrawIndexed()", "flags": ["Drawcall"], "num_indices": 243}]}
            if method == "get_mesh_data":
                return {
                    "attributes": [
                        {"name": "_input0", "semantic_name": "", "vertex_buffer_slot": 0, "format": "R32G32B32_FLOAT", "components": 3},
                        {"name": "_input2", "semantic_name": "", "vertex_buffer_slot": 2, "format": "R32G32_FLOAT", "components": 2},
                    ]
                }
            if method == "export_mesh_to_file":
                self.export_calls.append(params)
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]],"uv0":[[0,0],[1,0],[0,1]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    mcp = FakeMcp()
    ExportService(mcp).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 184)

    assert mcp.export_calls == [
        {
            "event_id": 184,
            "output_path": str(tmp_path / "out" / "raw_mesh_json" / "184_eid.json"),
            "pos_slot": 0,
            "normal_slot": 999,
            "tangent_slot": 999,
            "uv0_slot": 2,
            "uv1_slot": 999,
            "extra_slot": 999,
        }
    ]


def test_export_mesh_for_event_preserves_common_position_normal_tangent_uv_layout(tmp_path):
    class FakeMcp:
        def __init__(self):
            self.export_calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            if method == "open_capture":
                return {}
            if method == "get_draw_calls":
                return {"actions": [{"event_id": 1203, "name": "Character", "flags": ["Drawcall"], "num_indices": 3}]}
            if method == "get_mesh_data":
                return {
                    "attributes": [
                        {"name": "_input0", "semantic_name": "", "vertex_buffer_slot": 0, "format": "R32G32B32_FLOAT", "components": 3},
                        {"name": "_input1", "semantic_name": "", "vertex_buffer_slot": 1, "format": "R32G32B32_FLOAT", "components": 3},
                        {"name": "_input2", "semantic_name": "", "vertex_buffer_slot": 2, "format": "R32G32B32A32_FLOAT", "components": 4},
                        {"name": "_input3", "semantic_name": "", "vertex_buffer_slot": 3, "format": "R32G32_FLOAT", "components": 2},
                    ]
                }
            if method == "export_mesh_to_file":
                self.export_calls.append(params)
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]],"normal":[[0,0,1],[0,0,1],[0,0,1]],"tangent":[[1,0,0,1],[1,0,0,1],[1,0,0,1]],"uv0":[[0,0],[1,0],[0,1]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    mcp = FakeMcp()
    ExportService(mcp).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)

    assert mcp.export_calls == [
        {
            "event_id": 1203,
            "output_path": str(tmp_path / "out" / "raw_mesh_json" / "1203_eid.json"),
            "pos_slot": 0,
            "normal_slot": 1,
            "tangent_slot": 2,
            "uv0_slot": 3,
            "uv1_slot": 999,
            "extra_slot": 999,
        }
    ]


def test_export_bound_textures_for_event_uses_safe_texture_filenames(tmp_path):
    class FakeMcp:
        def __init__(self):
            self.calls = []

        def call(self, method, params=None, timeout=None):
            params = params or {}
            self.calls.append((method, params, timeout))
            if method == "open_capture":
                return {}
            if method == "get_bound_textures":
                return {"textures": [{"resource_id": "folder/101", "name": "Albedo/Base"}]}
            if method == "export_texture_to_file":
                Path(params["output_path"]).write_text("png", encoding="utf-8")
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    mcp = FakeMcp()
    result = ExportService(mcp).export_bound_textures_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)

    texture_call = [call for call in mcp.calls if call[0] == "export_texture_to_file"][0]
    assert result["event_id"] == 1203
    assert result["textures"] == [
        {
            "resource_id": "folder/101",
            "name": "Albedo/Base",
            "path": str(tmp_path / "out" / "textures" / "eid_1203" / "Albedo_Base_folder_101.png"),
        }
    ]
    assert texture_call[1]["resource_id"] == "folder/101"
    assert texture_call[1]["output_path"] == str(tmp_path / "out" / "textures" / "eid_1203" / "Albedo_Base_folder_101.png")
    assert (tmp_path / "out" / "textures" / "eid_1203" / "Albedo_Base_folder_101.png").is_file()


def test_export_bound_textures_for_event_reports_unsupported_mcp_capability(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "get_bound_textures":
                raise McpCapabilityMissing("Method not found: get_bound_textures")
            raise AssertionError(method)

    with pytest.raises(McpCapabilityMissing, match="Installed RenderDocMCP does not support EID bound texture export."):
        ExportService(FakeMcp()).export_bound_textures_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)
