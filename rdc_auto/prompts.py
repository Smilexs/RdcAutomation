from __future__ import annotations

from pathlib import Path


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def prompt_path(label: str, default: str | Path | None = None) -> Path:
    default_text = str(default) if default else ""
    value = prompt_text(label, default_text)
    return Path(value).expanduser()


def choose_option(label: str, options: list[str], default: str | None = None) -> str:
    if not options:
        raise ValueError("options must not be empty")
    if default is not None and default not in options:
        raise ValueError("default must be one of options")

    print(label)
    for index, option in enumerate(options, start=1):
        marker = " default" if option == default else ""
        print(f"  {index}. {option}{marker}")

    while True:
        raw = input("Select option: ").strip()
        if raw == "" and default is not None:
            return default
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        if raw in options:
            return raw
        print(f"Enter a number from 1 to {len(options)} or one of: {', '.join(options)}")
