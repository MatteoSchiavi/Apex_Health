"""Bounded-memory encrypted gzip archives, with legacy Fernet compatibility.

Each v2 frame uses standard Fernet authentication and contains a random
archive identifier, its sequence number and its type. A required terminal
frame prevents truncation, reordering and mixing frames from other archives.
No plaintext dump or compressed health data is written to disk.
"""

import secrets
import struct
import zlib
from collections.abc import Iterable, Iterator
from typing import BinaryIO

from cryptography.fernet import Fernet, InvalidToken

MAGIC = b"APEXBK2\n"
CHUNK = 512 * 1024
MAX_FRAME = 2 * CHUNK


class ArchiveCorruptError(ValueError):
    pass


def write_archive(chunks: Iterable[bytes], output: BinaryIO, fernet: Fernet) -> None:
    identity = secrets.token_bytes(16)
    output.write(MAGIC + identity)
    sequence = 0
    def frame(kind: bytes, payload: bytes) -> None:
        nonlocal sequence
        encrypted = fernet.encrypt(identity + struct.pack(">Q", sequence) + kind + payload)
        output.write(struct.pack(">I", len(encrypted)))
        output.write(encrypted)
        sequence += 1
    compressor = zlib.compressobj(level=6, wbits=31)  # gzip wrapper
    pending = b""
    for chunk in chunks:
        pending += compressor.compress(chunk)
        while len(pending) >= CHUNK:
            frame(b"D", pending[:CHUNK])
            pending = pending[CHUNK:]
    pending += compressor.flush()
    while pending:
        frame(b"D", pending[:CHUNK])
        pending = pending[CHUNK:]
    frame(b"E", b"")


def read_archive(source: BinaryIO, fernet: Fernet) -> Iterator[bytes]:
    prefix = source.read(len(MAGIC))
    try:
        if prefix != MAGIC:
            # Backwards compatible restore of previously generated archives.
            compressed = fernet.decrypt(prefix + source.read())
            decompressor = zlib.decompressobj(wbits=31)
            for start in range(0, len(compressed), CHUNK):
                block = decompressor.decompress(compressed[start:start + CHUNK], CHUNK)
                while block:
                    yield block
                    block = decompressor.decompress(decompressor.unconsumed_tail, CHUNK)
            if not decompressor.eof or decompressor.unused_data:
                raise ArchiveCorruptError("Invalid compressed archive")
            return
        identity = source.read(16)
        if len(identity) != 16:
            raise ArchiveCorruptError("Truncated archive header")
        decompressor = zlib.decompressobj(wbits=31)
        sequence = 0
        while True:
            size = source.read(4)
            if len(size) != 4:
                raise ArchiveCorruptError("Missing terminal frame")
            length = struct.unpack(">I", size)[0]
            if not 0 < length <= MAX_FRAME:
                raise ArchiveCorruptError("Invalid frame length")
            token = source.read(length)
            if len(token) != length:
                raise ArchiveCorruptError("Truncated frame")
            frame = fernet.decrypt(token)
            if len(frame) < 25 or frame[:16] != identity or frame[16:24] != struct.pack(">Q", sequence):
                raise ArchiveCorruptError("Wrong archive or frame sequence")
            sequence += 1
            kind, payload = frame[24:25], frame[25:]
            if kind == b"E":
                if payload or source.read(1) or not decompressor.eof:
                    raise ArchiveCorruptError("Invalid archive ending")
                return
            if kind != b"D":
                raise ArchiveCorruptError("Unknown frame type")
            block = decompressor.decompress(payload, CHUNK)
            while block:
                yield block
                block = decompressor.decompress(decompressor.unconsumed_tail, CHUNK)
            if decompressor.unused_data:
                raise ArchiveCorruptError("Unexpected compressed trailing data")
    except (InvalidToken, zlib.error, struct.error) as exc:
        raise ArchiveCorruptError("Wrong backup key or corrupt archive") from exc
