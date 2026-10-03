"""Legacy restore, bounded-memory v2 archives and authenticated framing."""

import gzip
import io
import os
import struct

import pytest

from app.core.backup_archive import ArchiveCorruptError, CHUNK, MAGIC, read_archive, write_archive
from app.core.backups import BackupCorruptError, _fernet, read_backup


def archive(data):
    output = io.BytesIO()
    write_archive((data[i:i + CHUNK] for i in range(0, len(data), CHUNK)), output, _fernet("backup-key"))
    return output.getvalue()


def frames(data):
    offset = len(MAGIC) + 16
    header = data[:offset]
    result = []
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        result.append(data[offset:offset + 4 + length])
        offset += 4 + length
    return header, result


def test_streaming_archive_roundtrip_has_bounded_read_chunks():
    data = os.urandom(3 * CHUNK)
    result = list(read_archive(io.BytesIO(archive(data)), _fernet("backup-key")))
    assert b"".join(result) == data
    assert max(map(len, result)) <= CHUNK


@pytest.mark.parametrize("damage", ["truncate", "drop_end", "reorder", "duplicate", "mix", "trailing"])
def test_authenticated_archive_rejects_frame_manipulation(damage):
    encoded = archive(os.urandom(3 * CHUNK))
    header, parts = frames(encoded)
    if damage == "truncate": altered = encoded[:-11]
    elif damage == "drop_end": altered = header + b"".join(parts[:-1])
    elif damage == "reorder": altered = header + parts[1] + parts[0] + b"".join(parts[2:])
    elif damage == "duplicate": altered = header + parts[0] + b"".join(parts)
    elif damage == "trailing": altered = encoded + b"junk"
    else:
        _, other = frames(archive(os.urandom(3 * CHUNK)))
        altered = header + other[0] + b"".join(parts[1:])
    with pytest.raises(ArchiveCorruptError):
        list(read_archive(io.BytesIO(altered), _fernet("backup-key")))


def test_legacy_backup_remains_restorable_and_invalid_gzip_is_rejected(tmp_path):
    path = tmp_path / "legacy.enc"
    sql = b"CREATE TABLE legacy_restore (id integer);\n" * 100
    path.write_bytes(_fernet("backup-key").encrypt(gzip.compress(sql)))
    assert read_backup(str(path), "backup-key") == sql
    path.write_bytes(_fernet("backup-key").encrypt(b"invalid compressed bytes"))
    with pytest.raises(BackupCorruptError):
        read_backup(str(path), "backup-key")
