from __future__ import annotations

from pathlib import Path

from rdc_auto.prompts import choose_option, prompt_path


def test_package_exposes_version():
    import rdc_auto

    assert isinstance(rdc_auto.__version__, str)
    assert rdc_auto.__version__


def test_choose_option_accepts_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "both"


def test_choose_option_accepts_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "2")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "meshes"


def test_prompt_path_returns_default(monkeypatch, tmp_path):
    default = tmp_path / "captures"
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert prompt_path("Output directory", default=default) == default
