import asyncio

import pytest

from app.api.v1.endpoints import admin


class _ChunkedUpload:
    def __init__(self, chunks: list[bytes]):
        self._chunks = iter(chunks)

    async def read(self, _size: int) -> bytes:
        return next(self._chunks, b"")


def test_save_uploaded_file_removes_partial_file_over_limit(tmp_path, monkeypatch):
    destination = tmp_path / "oversized.csv"
    monkeypatch.setattr(admin.settings, "TRADE_REGISTRY_MAX_UPLOAD_BYTES", 5)

    with pytest.raises(admin.HTTPException) as exc_info:
        asyncio.run(
            admin._save_uploaded_file(
                _ChunkedUpload([b"1234", b"56"]),
                destination,
            )
        )

    assert exc_info.value.status_code == 413
    assert not destination.exists()


def test_save_uploaded_file_keeps_valid_file(tmp_path, monkeypatch):
    destination = tmp_path / "valid.csv"
    monkeypatch.setattr(admin.settings, "TRADE_REGISTRY_MAX_UPLOAD_BYTES", 10)

    asyncio.run(
        admin._save_uploaded_file(
            _ChunkedUpload([b"1234", b"56"]),
            destination,
        )
    )

    assert destination.read_bytes() == b"123456"
