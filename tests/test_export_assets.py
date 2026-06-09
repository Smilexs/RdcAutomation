from __future__ import annotations

import json

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
