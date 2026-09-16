"""Versioned streaming AES-256-GCM export, Scrypt KDF, authenticated header."""
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.base import AEADEncryptionContext, AEADDecryptionContext
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .backups import inspect_snapshot, private_directory

MAGIC = b"ICEZPK01"
HEADER_SIZE = 36  # magic + 16-byte salt + 12-byte nonce
CHUNK = 1024 * 1024


def key(password, salt):
    if len(password) < 12:
        raise ValueError("export_password_minimum_12_characters")
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode("utf-8"))


def transform(source, destination, password, decrypt=False):
    """Never publish unauthenticated plaintext or replace an existing destination."""
    private_directory(destination.parent)
    if destination.exists():
        raise ValueError("export_destination_exists")
    if not decrypt:
        inspect_snapshot(source)
    ctx: AEADEncryptionContext | AEADDecryptionContext
    encryptor = None
    temporary = destination.with_name("." + uuid.uuid4().hex + ".partial")
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            if decrypt:
                header = src.read(HEADER_SIZE)
                if len(header) != HEADER_SIZE or header[:8] != MAGIC:
                    raise ValueError("encrypted_export_format_invalid")
                src.seek(0, 2)
                remaining = src.tell() - HEADER_SIZE - 16
                if remaining < 0:
                    raise ValueError("encrypted_export_truncated")
                src.seek(-16, 2)
                tag = src.read(16)
                src.seek(HEADER_SIZE)
                ctx = Cipher(algorithms.AES(key(password, header[8:24])), modes.GCM(header[24:], tag)).decryptor()
            else:
                header = MAGIC + os.urandom(16) + os.urandom(12)
                remaining = source.stat().st_size
                encryptor = Cipher(algorithms.AES(key(password, header[8:24])), modes.GCM(header[24:])).encryptor()
                ctx = encryptor
                dst.write(header)
            ctx.authenticate_additional_data(header)
            while remaining:
                chunk = src.read(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("export_source_truncated")
                remaining -= len(chunk)
                dst.write(ctx.update(chunk))
            dst.write(ctx.finalize())
            if not decrypt:
                assert encryptor is not None
                dst.write(encryptor.tag)
            dst.flush()
            os.fsync(dst.fileno())
        if decrypt:
            inspect_snapshot(temporary)
        # Hard-link gives atomic no-overwrite publication on NTFS and Termux ext4.
        os.link(temporary, destination)
    except InvalidTag:
        raise ValueError("export_password_or_authentication_failed") from None
    finally:
        temporary.unlink(missing_ok=True)
