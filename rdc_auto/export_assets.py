from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Protocol

from .mesh_convert import convert_mesh_json_to_obj


class McpCaller(Protocol):
    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        raise NotImplementedError


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("_") or "unnamed"


def _parse_event_id(value: object) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        event_id = int(value)
        if event_id > 0:
            return event_id
    raise ValueError(f"invalid event_id: {value!r}")


class ExportService:
    def __init__(self, mcp: McpCaller):
        self.mcp = mcp

    def export(self, rdc_path: str | Path, output_dir: str | Path, assets: str) -> dict:
        if assets not in {"textures", "meshes", "both"}:
            raise ValueError(f"unsupported asset type: {assets}")
        rdc_path = Path(rdc_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source_rdc": str(rdc_path),
            "exported_at": dt.datetime.now().astimezone().isoformat(),
            "assets": {
                "textures": {"success": 0, "failed": 0},
                "meshes": {"success": 0, "failed": 0},
            },
            "failures": [],
        }

        self.mcp.call("open_capture", {"capture_path": str(rdc_path)}, timeout=120.0)

        if assets in {"textures", "both"}:
            self._export_textures(output_dir, manifest)
        if assets in {"meshes", "both"}:
            self._export_meshes(output_dir, manifest)

        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def _export_textures(self, output_dir: Path, manifest: dict) -> None:
        textures_dir = output_dir / "textures"
        textures_dir.mkdir(parents=True, exist_ok=True)
        textures = self.mcp.call("get_textures", timeout=60.0).get("textures", [])
        for texture in textures:
            resource_id = str(texture.get("resource_id") or texture.get("id") or "")
            resource_id_name = safe_name(resource_id)
            name = safe_name(str(texture.get("name") or "texture"))
            path = textures_dir / f"{name}_{resource_id_name}.png"
            try:
                self.mcp.call(
                    "export_texture_to_file",
                    {"resource_id": resource_id, "output_path": str(path), "file_type": "PNG"},
                    timeout=120.0,
                )
                manifest["assets"]["textures"]["success"] += 1
            except Exception as exc:
                manifest["assets"]["textures"]["failed"] += 1
                manifest["failures"].append({"type": "texture", "resource_id": resource_id, "error": str(exc)})

    def _export_meshes(self, output_dir: Path, manifest: dict) -> None:
        meshes_dir = output_dir / "meshes"
        raw_dir = output_dir / "raw_mesh_json"
        meshes_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        draws = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0).get("draws", [])
        for draw in draws:
            try:
                raw_event_id = draw["event_id"] if "event_id" in draw else draw.get("eventId")
                event_id = _parse_event_id(raw_event_id)
                name = safe_name(str(draw.get("name") or f"draw_{event_id}"))
                stem = f"{event_id}_{name}"
                raw_json = raw_dir / f"{stem}.json"
                obj = meshes_dir / f"{stem}.obj"
                mtl = meshes_dir / f"{stem}.mtl"
                self.mcp.call(
                    "export_mesh_to_file",
                    {"event_id": event_id, "output_path": str(raw_json)},
                    timeout=120.0,
                )
                convert_mesh_json_to_obj(raw_json, obj, mtl, material_name=f"mat_{event_id}")
                manifest["assets"]["meshes"]["success"] += 1
            except Exception as exc:
                manifest["assets"]["meshes"]["failed"] += 1
                manifest["failures"].append({"type": "mesh", "draw": draw, "error": str(exc)})
