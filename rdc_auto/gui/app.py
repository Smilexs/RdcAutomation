from __future__ import annotations

from rdc_auto.config import load_config
from rdc_auto.gui.bridge import GuiBridge
from rdc_auto.gui.paths import gui_index_path


def build_window_options() -> dict:
    cfg = load_config()
    return {
        "title": "RdcAutomation",
        "url": str(gui_index_path()),
        "width": int(cfg.gui.window_width),
        "height": int(cfg.gui.window_height),
        "min_size": (1100, 720),
    }


def main(debug: bool = False) -> int:
    import webview

    bridge = GuiBridge()
    options = build_window_options()
    window = webview.create_window(
        options["title"],
        options["url"],
        js_api=bridge,
        width=options["width"],
        height=options["height"],
        min_size=options["min_size"],
    )
    bridge.bind_window(window)
    webview.start(debug=debug)
    return 0
