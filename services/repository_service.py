from __future__ import annotations

from pathlib import Path


EXCLUDED_PARTS = {"__pycache__", ".git", ".venv"}
PREVIEW_EXTENSIONS = {".py", ".md", ".txt", ".csv", ".json", ".bat"}


class RepositoryService:
    """Read-only repository helper used by the repository viewer page."""

    def __init__(self, root_path: str | Path) -> None:
        self.root_path = Path(root_path)

    def get_structure(self) -> list[dict[str, str]]:
        """Return a flattened tree structure for display."""
        items: list[dict[str, str]] = []
        for path in sorted(self.root_path.rglob("*")):
            relative_parts = set(path.relative_to(self.root_path).parts)
            if relative_parts & EXCLUDED_PARTS:
                continue
            item_type = "Directory" if path.is_dir() else "File"
            items.append(
                {
                    "path": str(path.relative_to(self.root_path)),
                    "type": item_type,
                }
            )
        return items

    def list_previewable_files(self) -> list[str]:
        """List files that can be safely previewed in the UI."""
        files = []
        for path in sorted(self.root_path.rglob("*")):
            relative_parts = set(path.relative_to(self.root_path).parts)
            if relative_parts & EXCLUDED_PARTS or not path.is_file():
                continue
            if path.suffix.lower() in PREVIEW_EXTENSIONS:
                files.append(str(path.relative_to(self.root_path)))
        return files

    def read_file_preview(self, relative_path: str, max_chars: int = 12000) -> str:
        """Read a safe text preview of a repository file."""
        target = (self.root_path / relative_path).resolve()
        if self.root_path.resolve() not in target.parents and target != self.root_path.resolve():
            raise ValueError("Invalid repository path.")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target.read_text(encoding="utf-8", errors="replace")[:max_chars]

    def get_summary(self) -> dict[str, int]:
        """Return lightweight repository metrics."""
        structure = self.get_structure()
        return {
            "files": sum(1 for item in structure if item["type"] == "File"),
            "directories": sum(1 for item in structure if item["type"] == "Directory"),
        }
