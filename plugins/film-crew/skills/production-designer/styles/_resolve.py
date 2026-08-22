"""Resolve production-designer style assets."""
import os


def styles_root() -> str:
    """Return the absolute path to the styles directory."""
    return os.path.dirname(os.path.abspath(__file__))


def style_dir(style_id: str) -> str:
    """Return the absolute path to a style directory."""
    path = os.path.join(styles_root(), style_id)
    if not os.path.isdir(path):
        raise LookupError(f"style {style_id!r} was not found at {path}")
    return path


def style_scripts(style_id: str) -> str:
    """Return the absolute path to a style's scripts directory."""
    return os.path.join(style_dir(style_id), "scripts")


def style_fonts(style_id: str) -> str:
    """Return the absolute path to a style's fonts directory."""
    path = os.path.join(style_dir(style_id), "fonts")
    if not os.path.isdir(path):
        raise LookupError(f"style {style_id!r} has no fonts directory at {path}")
    return path


def list_styles() -> list[str]:
    """Return style ids that have a style.json manifest."""
    root = styles_root()
    return sorted(
        name for name in os.listdir(root)
        if os.path.isfile(os.path.join(root, name, "style.json")))
