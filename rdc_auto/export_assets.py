from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Protocol

from .errors import McpCapabilityMissing
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


def _draw_items(response: dict) -> list[dict]:
    raw_items = response.get("draws")
    if raw_items is None:
        raw_items = response.get("actions", [])
    return list(_flatten_draw_items(raw_items if isinstance(raw_items, list) else []))


def _flatten_draw_items(items: list) -> list[dict]:
    flattened = []
    for item in items:
        if not isinstance(item, dict):
            continue
        flattened.append(item)
        children = item.get("children", [])
        if isinstance(children, list):
            flattened.extend(_flatten_draw_items(children))
    return flattened


def _optional_positive_int(value: object) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _flag_names(draw: dict) -> set[str]:
    flags = draw.get("flags", [])
    if isinstance(flags, str):
        flags = [flags]
    if not isinstance(flags, list):
        return set()
    return {str(flag).strip().lower() for flag in flags if str(flag).strip()}


def _draw_has_mesh(draw: dict) -> bool | None:
    explicit = draw.get("has_mesh", draw.get("hasMesh"))
    if isinstance(explicit, bool):
        return explicit

    raw_num_indices = draw.get("num_indices", draw.get("numIndices"))
    num_indices = _optional_positive_int(raw_num_indices)
    flags = _flag_names(draw)
    if flags and "drawcall" not in flags:
        return False
    if num_indices is not None:
        return num_indices > 0
    if flags:
        return "drawcall" in flags
    return None


def _looks_like_optional_mesh_attribute_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return "list index out of range" in message or "indexerror" in message


def _position_only_mesh_params(event_id: int, output_path: Path) -> dict:
    return {
        "event_id": event_id,
        "output_path": str(output_path),
        "normal_slot": 999,
        "tangent_slot": 999,
        "uv0_slot": 999,
        "uv1_slot": 999,
        "extra_slot": 999,
    }


def _mesh_attribute_slot(attribute: dict) -> int | None:
    value = attribute.get("vertex_buffer_slot", attribute.get("vertexBufferSlot"))
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _mesh_attribute_components(attribute: dict) -> int:
    value = attribute.get("components", attribute.get("comp_count", attribute.get("compCount")))
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _mesh_attribute_label(attribute: dict) -> str:
    return " ".join(
        str(attribute.get(key) or "").strip().lower()
        for key in ("name", "semantic_name", "semanticName")
        if str(attribute.get(key) or "").strip()
    )


def _infer_mesh_slot_params(attributes: list) -> dict:
    params = {
        "pos_slot": 999,
        "normal_slot": 999,
        "tangent_slot": 999,
        "uv0_slot": 999,
        "uv1_slot": 999,
        "extra_slot": 999,
    }
    parsed = []
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        slot = _mesh_attribute_slot(attribute)
        components = _mesh_attribute_components(attribute)
        if slot is None or components <= 0:
            continue
        parsed.append((slot, components, _mesh_attribute_label(attribute)))

    for slot, components, label in parsed:
        if params["pos_slot"] == 999 and components >= 3 and any(token in label for token in ("position", "pos")):
            params["pos_slot"] = slot
        elif params["normal_slot"] == 999 and components >= 3 and "normal" in label:
            params["normal_slot"] = slot
        elif params["tangent_slot"] == 999 and components >= 3 and "tangent" in label:
            params["tangent_slot"] = slot
        elif params["uv0_slot"] == 999 and components >= 2 and any(token in label for token in ("texcoord0", "texcoord", "uv0", "uv")):
            params["uv0_slot"] = slot

    if params["pos_slot"] == 999:
        for slot, components, _label in parsed:
            if components >= 3:
                params["pos_slot"] = slot
                break

    for slot, components, _label in parsed:
        if slot in params.values():
            continue
        if components >= 4 and params["tangent_slot"] == 999:
            params["tangent_slot"] = slot
        elif components == 3 and params["normal_slot"] == 999:
            params["normal_slot"] = slot
        elif components == 3 and params["tangent_slot"] == 999:
            params["tangent_slot"] = slot

    for slot, components, _label in parsed:
        if components < 2 or slot in params.values():
            continue
        if components == 2:
            if params["uv0_slot"] == 999:
                params["uv0_slot"] = slot
            elif params["uv1_slot"] == 999:
                params["uv1_slot"] = slot
            elif params["extra_slot"] == 999:
                params["extra_slot"] = slot
        elif params["extra_slot"] == 999:
            params["extra_slot"] = slot

    return params


class ExportService:
    def __init__(self, mcp: McpCaller):
        self.mcp = mcp

    def list_draw_calls(self, rdc_path: str | Path) -> list[dict]:
        rdc_path = Path(rdc_path)
        self.mcp.call("open_capture", {"capture_path": str(rdc_path)}, timeout=120.0)
        rows = []
        response = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0)
        draws = _draw_items(response)
        for draw in draws:
            try:
                raw_event_id = draw["event_id"] if "event_id" in draw else draw.get("eventId")
                event_id = _parse_event_id(raw_event_id)
            except (AttributeError, ValueError):
                continue
            row = {"event_id": event_id, "name": str(draw.get("name") or f"draw_{event_id}")}
            for key in (
                "flags",
                "num_indices",
                "numIndices",
                "has_mesh",
                "hasMesh",
                "texture_count",
                "textureCount",
                "textures",
                "bound_textures",
            ):
                if key in draw:
                    row[key] = draw[key]
            if "has_mesh" not in row and "hasMesh" not in row:
                has_mesh = _draw_has_mesh(draw)
                if has_mesh is not None:
                    row["has_mesh"] = has_mesh
            rows.append(row)
        return rows

    def export_mesh_for_event(self, rdc_path: str | Path, output_dir: str | Path, event_id: object) -> dict:
        event_id = _parse_event_id(event_id)
        rdc_path = Path(rdc_path)
        output_dir = Path(output_dir)
        meshes_dir = output_dir / "meshes"
        raw_dir = output_dir / "raw_mesh_json"
        meshes_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        raw_json = raw_dir / f"{event_id}_eid.json"
        obj = meshes_dir / f"{event_id}_eid.obj"
        mtl = meshes_dir / f"{event_id}_eid.mtl"
        self.mcp.call("open_capture", {"capture_path": str(rdc_path)}, timeout=120.0)
        draw = self._draw_for_event(event_id)
        if draw is None:
            raise ValueError(f"EID {event_id} was not found in the current capture draw call list.")
        if _draw_has_mesh(draw) is False:
            raise ValueError(f"EID {event_id} is not an exportable mesh draw.")
        try:
            self._export_mesh_json(event_id, raw_json)
        except Exception as exc:
            raise RuntimeError(f"RenderDocMCP failed to export mesh for EID {event_id}: {exc}") from exc
        convert_mesh_json_to_obj(raw_json, obj, mtl, material_name=f"mat_{event_id}")
        return {"event_id": event_id, "raw_json_path": str(raw_json), "obj_path": str(obj), "mtl_path": str(mtl)}

    def _export_mesh_json(self, event_id: int, raw_json: Path) -> None:
        params = self._mesh_export_params(event_id, raw_json)
        try:
            self.mcp.call(
                "export_mesh_to_file",
                params,
                timeout=120.0,
            )
            return
        except Exception as exc:
            if not _looks_like_optional_mesh_attribute_failure(exc):
                raise
            first_error = exc

        try:
            self.mcp.call(
                "export_mesh_to_file",
                _position_only_mesh_params(event_id, raw_json),
                timeout=120.0,
            )
        except Exception as exc:
            raise RuntimeError(f"{first_error}; position-only retry failed: {exc}") from exc

    def _mesh_export_params(self, event_id: int, raw_json: Path) -> dict:
        params = {"event_id": event_id, "output_path": str(raw_json)}
        try:
            mesh_data = self.mcp.call("get_mesh_data", {"event_id": event_id}, timeout=120.0)
        except Exception:
            return params

        attributes = mesh_data.get("attributes", [])
        if not isinstance(attributes, list):
            return params
        slot_params = _infer_mesh_slot_params(attributes)
        if slot_params["pos_slot"] == 999:
            return params
        params.update(slot_params)
        return params

    def _draw_for_event(self, event_id: int) -> dict | None:
        response = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0)
        for draw in _draw_items(response):
            try:
                raw_event_id = draw["event_id"] if "event_id" in draw else draw.get("eventId")
                if _parse_event_id(raw_event_id) == event_id:
                    return draw
            except (AttributeError, ValueError):
                continue
        return None

    def export_bound_textures_for_event(self, rdc_path: str | Path, output_dir: str | Path, event_id: object) -> dict:
        event_id = _parse_event_id(event_id)
        rdc_path = Path(rdc_path)
        output_dir = Path(output_dir)
        textures_dir = output_dir / "textures" / f"eid_{event_id}"
        textures_dir.mkdir(parents=True, exist_ok=True)

        self.mcp.call("open_capture", {"capture_path": str(rdc_path)}, timeout=120.0)
        try:
            response = self.mcp.call("get_bound_textures", {"event_id": event_id}, timeout=60.0)
        except McpCapabilityMissing as exc:
            raise McpCapabilityMissing("Installed RenderDocMCP does not support EID bound texture export.") from exc
        textures = response.get("textures", response.get("bound_textures", []))
        exported = []
        for index, texture in enumerate(textures, start=1):
            resource_id = str(texture.get("resource_id") or texture.get("resourceId") or texture.get("id") or "")
            if not resource_id:
                continue
            name = str(texture.get("name") or f"texture_{index}")
            path = textures_dir / f"{safe_name(name)}_{safe_name(resource_id)}.png"
            try:
                self.mcp.call(
                    "export_texture_to_file",
                    {"resource_id": resource_id, "output_path": str(path), "file_type": "PNG"},
                    timeout=120.0,
                )
            except McpCapabilityMissing as exc:
                raise McpCapabilityMissing("Installed RenderDocMCP does not support EID bound texture export.") from exc
            exported.append({"resource_id": resource_id, "name": name, "path": str(path)})
        return {"event_id": event_id, "textures": exported}

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
        response = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0)
        draws = _draw_items(response)
        for draw in draws:
            try:
                raw_event_id = draw["event_id"] if "event_id" in draw else draw.get("eventId")
                event_id = _parse_event_id(raw_event_id)
                name = safe_name(str(draw.get("name") or f"draw_{event_id}"))
                stem = f"{event_id}_{name}"
                raw_json = raw_dir / f"{stem}.json"
                obj = meshes_dir / f"{stem}.obj"
                mtl = meshes_dir / f"{stem}.mtl"
                self._export_mesh_json(event_id, raw_json)
                convert_mesh_json_to_obj(raw_json, obj, mtl, material_name=f"mat_{event_id}")
                manifest["assets"]["meshes"]["success"] += 1
            except Exception as exc:
                manifest["assets"]["meshes"]["failed"] += 1
                manifest["failures"].append({"type": "mesh", "draw": draw, "error": str(exc)})
