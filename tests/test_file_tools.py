"""Unit tests for sandboxed file tools."""

import json
import pytest
from src.tools.file_tools import write_file, read_file, list_directory, _resolve_safe_path


def test_write_and_read_file():
    filename = "test_sample.py"
    code = "print('Hello from AI sandbox!')\n"

    # Write file
    write_res = json.loads(write_file(filename, code))
    assert write_res.get("success") is True

    # Read file
    read_res = json.loads(read_file(filename))
    assert read_res.get("content") == code


def test_list_directory():
    list_res = json.loads(list_directory("."))
    assert "entries" in list_res
    assert isinstance(list_res["entries"], list)


def test_path_traversal_blocked():
    with pytest.raises(PermissionError):
        _resolve_safe_path("../../../windows/system32/cmd.exe")
