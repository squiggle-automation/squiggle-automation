from pathlib import Path


def get_version():
    """Read the application version from the VERSION file."""
    version_file = Path(__file__).resolve().parent / "VERSION"
    try:
        return version_file.read_text().strip()
    except FileNotFoundError:
        return "unknown"
