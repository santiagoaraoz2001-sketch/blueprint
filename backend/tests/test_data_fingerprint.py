"""Tests for data fingerprinting — content-addressable hashing for datasets."""

import json
import os
import tempfile

import pytest

from backend.utils.data_fingerprint import (
    fingerprint_dataset,
    hash_directory,
    hash_file,
    hash_json,
    hash_string,
)


# ---------- hash_file ----------

class TestHashFile:
    def test_same_file_same_hash(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3\n")
        assert hash_file(str(f)) == hash_file(str(f))

    def test_modified_file_different_hash(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3\n")
        h1 = hash_file(str(f))
        f.write_text("a,b,c\n1,2,4\n")
        h2 = hash_file(str(f))
        assert h1 != h2

    def test_hash_is_64_hex_chars(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello")
        h = hash_file(str(f))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------- hash_directory ----------

class TestHashDirectory:
    def test_same_dir_same_hash(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")
        assert hash_directory(str(tmp_path)) == hash_directory(str(tmp_path))

    def test_added_file_changes_hash(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        h1 = hash_directory(str(tmp_path))
        (tmp_path / "b.txt").write_text("bbb")
        h2 = hash_directory(str(tmp_path))
        assert h1 != h2

    def test_modified_file_changes_hash(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        h1 = hash_directory(str(tmp_path))
        (tmp_path / "a.txt").write_text("modified")
        h2 = hash_directory(str(tmp_path))
        assert h1 != h2

    def test_nested_files(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")
        h1 = hash_directory(str(tmp_path))
        (sub / "nested.txt").write_text("changed")
        h2 = hash_directory(str(tmp_path))
        assert h1 != h2

    def test_empty_directory(self, tmp_path):
        """Empty directory produces a valid hash (SHA256 of nothing)."""
        h = hash_directory(str(tmp_path))
        assert len(h) == 64

    def test_broken_symlink_skipped(self, tmp_path):
        """Broken symlinks are gracefully skipped."""
        (tmp_path / "real.txt").write_text("real")
        (tmp_path / "broken_link").symlink_to(tmp_path / "nonexistent")
        # Should not raise
        h = hash_directory(str(tmp_path))
        assert len(h) == 64


# ---------- hash_string ----------

class TestHashString:
    def test_same_string_same_hash(self):
        assert hash_string("hello") == hash_string("hello")

    def test_different_string_different_hash(self):
        assert hash_string("hello") != hash_string("world")


# ---------- hash_json ----------

class TestHashJson:
    def test_key_order_independent(self):
        assert hash_json({"b": 2, "a": 1}) == hash_json({"a": 1, "b": 2})

    def test_different_data_different_hash(self):
        assert hash_json({"a": 1}) != hash_json({"a": 2})


# ---------- fingerprint_dataset ----------

class TestFingerprintDataset:
    def test_none_input(self):
        fp = fingerprint_dataset(None)
        assert fp["hash"] == "empty"
        assert fp["source_type"] == "none"

    def test_file_input(self, tmp_path):
        f = tmp_path / "train.csv"
        f.write_text("x,y\n1,2\n3,4\n")
        fp = fingerprint_dataset(str(f))
        assert fp["source_type"] == "file"
        assert fp["source_id"] == "train.csv"
        assert fp["size_bytes"] == f.stat().st_size
        assert len(fp["hash"]) == 64

    def test_directory_input(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")
        fp = fingerprint_dataset(str(tmp_path))
        assert fp["source_type"] == "directory"
        assert fp["size_bytes"] > 0

    def test_hf_dataset_id(self):
        fp = fingerprint_dataset("username/dataset")
        assert fp["source_type"] == "hf_dataset"
        assert fp["source_id"] == "username/dataset"

    def test_inline_string(self):
        fp = fingerprint_dataset("some raw text data")
        assert fp["source_type"] == "string"
        assert fp["source_id"] == "<inline>"
        assert fp["size_bytes"] == len("some raw text data".encode("utf-8"))

    def test_dict_input(self):
        data = {"rows": [1, 2, 3], "columns": ["a"]}
        fp = fingerprint_dataset(data)
        assert fp["source_type"] == "json"
        assert fp["source_id"] == "<inline>"
        assert fp["size_bytes"] > 0

    def test_list_input(self):
        data = [{"a": 1}, {"a": 2}]
        fp = fingerprint_dataset(data)
        assert fp["source_type"] == "json"

    def test_unknown_type_fallback(self):
        fp = fingerprint_dataset(42)
        assert fp["source_type"] == "unknown"

    def test_file_hash_stability(self, tmp_path):
        """Same file content always produces the same hash."""
        f = tmp_path / "stable.txt"
        f.write_text("deterministic content")
        h1 = fingerprint_dataset(str(f))["hash"]
        h2 = fingerprint_dataset(str(f))["hash"]
        assert h1 == h2

    def test_file_modification_changes_hash(self, tmp_path):
        """Modifying file content changes the hash."""
        f = tmp_path / "mutable.txt"
        f.write_text("version 1")
        h1 = fingerprint_dataset(str(f))["hash"]
        f.write_text("version 2")
        h2 = fingerprint_dataset(str(f))["hash"]
        assert h1 != h2

    def test_empty_string(self):
        fp = fingerprint_dataset("")
        assert fp["source_type"] == "string"
        assert fp["size_bytes"] == 0
        assert len(fp["hash"]) == 64

    def test_nested_hf_dataset_id(self):
        """HF IDs with org/user/dataset format."""
        fp = fingerprint_dataset("org/dataset-name")
        assert fp["source_type"] == "hf_dataset"
        assert fp["source_id"] == "org/dataset-name"

    def test_empty_dict(self):
        fp = fingerprint_dataset({})
        assert fp["source_type"] == "json"
        assert len(fp["hash"]) == 64

    def test_empty_list(self):
        fp = fingerprint_dataset([])
        assert fp["source_type"] == "json"
        assert len(fp["hash"]) == 64

    def test_json_hash_determinism(self):
        """Same data in different insertion order produces same hash."""
        d1 = {"z": 3, "a": 1, "m": 2}
        d2 = {"a": 1, "m": 2, "z": 3}
        assert fingerprint_dataset(d1)["hash"] == fingerprint_dataset(d2)["hash"]

    def test_nonexistent_path_treated_as_string(self):
        """A string that looks like a path but doesn't exist is treated as string."""
        fp = fingerprint_dataset("/nonexistent/path/to/data.csv")
        assert fp["source_type"] == "string"


# ---------- BlockContext integration ----------

class TestBlockContextFingerprinting:
    def test_load_input_records_fingerprint(self, tmp_path):
        from backend.block_sdk.context import BlockContext

        f = tmp_path / "input.csv"
        f.write_text("col1,col2\n1,2\n")

        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path),
            config={},
            inputs={"dataset": str(f)},
        )
        ctx.load_input("dataset")

        fps = ctx.get_data_fingerprints()
        assert "dataset" in fps
        assert fps["dataset"]["source_type"] == "file"
        assert fps["dataset"]["source_id"] == "input.csv"
        assert len(fps["dataset"]["hash"]) == 64

    def test_multiple_inputs_fingerprinted(self, tmp_path):
        from backend.block_sdk.context import BlockContext

        f1 = tmp_path / "train.csv"
        f1.write_text("a\n1\n")
        f2 = tmp_path / "val.csv"
        f2.write_text("b\n2\n")

        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path),
            config={},
            inputs={"train": str(f1), "val": str(f2)},
        )
        ctx.load_input("train")
        ctx.load_input("val")

        fps = ctx.get_data_fingerprints()
        assert len(fps) == 2
        assert fps["train"]["hash"] != fps["val"]["hash"]

    def test_no_fingerprint_without_load(self, tmp_path):
        from backend.block_sdk.context import BlockContext

        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path),
            config={},
            inputs={"data": "some_value"},
        )
        assert ctx.get_data_fingerprints() == {}

    def test_fingerprint_error_does_not_crash_load_input(self, tmp_path, monkeypatch):
        """If fingerprinting raises, load_input still returns the value."""
        from backend.block_sdk import context as ctx_module
        from backend.block_sdk.context import BlockContext

        def bad_fingerprint(source, source_type="auto"):
            raise RuntimeError("simulated I/O error")

        monkeypatch.setattr(ctx_module, "fingerprint_dataset", bad_fingerprint)

        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path),
            config={},
            inputs={"data": "my_value"},
        )
        result = ctx.load_input("data")
        assert result == "my_value"
        # Fingerprint should be empty since it failed
        assert ctx.get_data_fingerprints() == {}

    def test_none_input_not_fingerprinted(self, tmp_path):
        """None-valued inputs are not fingerprinted."""
        from backend.block_sdk.context import BlockContext

        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path),
            config={},
            inputs={"data": None},
        )
        result = ctx.load_input("data")
        assert result is None
        assert ctx.get_data_fingerprints() == {}


# ---------- API endpoint tests ----------

class TestDataProvenanceEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_data_provenance_missing_run(self, client):
        resp = client.get("/api/runs/nonexistent/data-provenance")
        assert resp.status_code == 404

    def test_compare_data_missing_runs(self, client):
        resp = client.post("/api/runs/compare-data?run_id_a=aaa&run_id_b=bbb")
        assert resp.status_code == 404
