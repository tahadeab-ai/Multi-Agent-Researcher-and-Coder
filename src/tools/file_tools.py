"""Sandboxed file operations for autonomous agents."""

import json
from pathlib import Path
from typing import Dict, Any, List
from src.config import settings


def _resolve_safe_path(filepath: str) -> Path:
    """Ensures filepath remains safely confined within the configured workspace directory."""
    workspace = settings.get_resolved_workspace()
    resolved = (workspace / filepath).resolve()

    # Path traversal guard
    if not str(resolved).startswith(str(workspace)):
        raise PermissionError(
            f"Access denied: Path '{filepath}' attempts to escape sandbox '{workspace}'"
        )
    return resolved


def read_file(filepath: str) -> str:
    """Reads the text content of a file located within the workspace sandbox."""
    try:
        path = _resolve_safe_path(filepath)
        if not path.exists():
            return json.dumps({"error": f"File not found: '{filepath}'"})
        if not path.is_file():
            return json.dumps({"error": f"Path is not a file: '{filepath}'"})

        content = path.read_text(encoding="utf-8")
        return json.dumps({"filepath": filepath, "content": content})
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {str(e)}"})


def write_file(filepath: str, content: str) -> str:
    """Writes or overwrites text content to a file in the workspace sandbox."""
    try:
        path = _resolve_safe_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({
            "success": True,
            "filepath": filepath,
            "bytes_written": len(content.encode("utf-8")),
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to write file: {str(e)}"})


def list_directory(dirpath: str = ".") -> str:
    """Lists files and subdirectories within a directory in the workspace sandbox."""
    try:
        path = _resolve_safe_path(dirpath)
        if not path.exists():
            return json.dumps({"error": f"Directory not found: '{dirpath}'"})
        if not path.is_dir():
            return json.dumps({"error": f"Path is not a directory: '{dirpath}'"})

        entries = []
        for item in sorted(path.iterdir()):
            entries.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size_bytes": item.stat().st_size if item.is_file() else None,
            })
        return json.dumps({"dirpath": dirpath, "entries": entries})
    except Exception as e:
        return json.dumps({"error": f"Failed to list directory: {str(e)}"})


# OpenAPI/JSON-Schema tool definitions for LLMs
FILE_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the text content of an existing file in the workspace sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Relative path to the file within the sandbox (e.g. 'src/module.py')",
                    }
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes or overwrites text content to a file in the workspace sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Relative path to the file to create/modify (e.g. 'solution.py')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The exact source code or text content to write.",
                    },
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists all files and subfolders inside a sandbox directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "Relative directory path (default is '.' for root of sandbox).",
                        "default": ".",
                    }
                },
                "required": [],
            },
        },
    },
]
