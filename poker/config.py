"""Validated configuration, with no secret-bearing repr."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    data_dir: Path
    environment: str = "production"
    origin: str = "https://localhost"
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    bot_token: str = field(default="", repr=False)
    guild_id: str = ""
    reader_token: str = field(default="", repr=False)
    funds_token: str = field(default="", repr=False)
    funds_admins: tuple[str, ...] = ()
    table_admins: tuple[str, ...] = ()
    public_port: int = 8765
    internal_port: int = 8766
    backup_dir: Path | None = None
    export_dir: Path | None = None
    static_dir: Path = Path(__file__).resolve().parent.parent / "poker_web" / "dist"

    @property
    def callback(self):
        return self.origin + "/auth/callback"

    @property
    def secure(self):
        return self.origin.startswith("https://")

    def validate(self):
        errors = []
        parsed = urlsplit(self.origin)
        if self.environment not in ("production", "development", "test"):
            errors.append("POKER_ENV must be production, development or test")
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            errors.append("POKER_ORIGIN must be an origin without path or credentials")
        if not self.secure and (
            self.environment == "production"
            or parsed.hostname not in ("localhost", "127.0.0.1", "testserver")
        ):
            errors.append("HTTPS required outside explicit local development/test")
        for name in ("client_id", "guild_id"):
            if not re.fullmatch(r"[0-9]{1,20}", getattr(self, name)):
                errors.append(name + " must be a Discord ID")
        for name in ("client_secret", "bot_token", "reader_token", "funds_token"):
            if len(getattr(self, name)) < 16:
                errors.append(name + " must be configured (minimum 16 characters)")
        if self.reader_token == self.funds_token:
            errors.append("internal read and funds credentials must differ")
        if any(not re.fullmatch(r"[0-9]{1,20}", actor) for actor in (*self.funds_admins, *self.table_admins)):
            errors.append("funds_admins must contain Discord IDs")
        if not self.data_dir.is_absolute():
            errors.append("POKER_DATA_DIR must be absolute")
        if (
            self.environment == "production"
            and not self.data_dir.resolve().is_relative_to(Path.home().resolve())
        ):
            errors.append(
                "production database must be under the private user home (Termux HOME)"
            )
        if self.public_port == self.internal_port or any(
            not 1024 <= port <= 65535 for port in (self.public_port, self.internal_port)
        ):
            errors.append("ports must be distinct and between 1024 and 65535")
        for name in ("backup_dir", "export_dir"):
            path = getattr(self, name)
            if path is not None and (not path.is_absolute() or path.resolve().is_relative_to(self.static_dir.resolve())):
                errors.append(name + " must be absolute and outside the public static directory")
        if errors:
            raise ValueError("; ".join(errors))

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(
                os.environ.get(
                    "POKER_DATA_DIR", str(Path.home() / ".local/share/icez-poker")
                )
            ),
            environment=os.environ.get("POKER_ENV", "production"),
            origin=os.environ.get("POKER_ORIGIN", "https://localhost"),
            client_id=os.environ.get("POKER_CLIENT_ID", os.environ.get("APPLICATION_ID", "")),
            client_secret=os.environ.get("POKER_CLIENT_SECRET", os.environ.get("CLIENT_SECRET", "")),
            bot_token=os.environ.get("POKER_BOT_TOKEN", os.environ.get("DISCORD_TOKEN", "")),
            guild_id=os.environ.get("POKER_GUILD_ID", os.environ.get("DISCORD_GUILD_ID", "")),
            reader_token=os.environ.get("POKER_READER_TOKEN", ""),
            funds_token=os.environ.get("POKER_FUNDS_TOKEN", ""),
            funds_admins=tuple(
                filter(None, os.environ.get("POKER_FUNDS_ADMINS", "").split(","))
            ),
            table_admins=tuple(filter(None, os.environ.get("POKER_TABLE_ADMINS", "").split(","))),
            public_port=int(os.environ.get("POKER_PUBLIC_PORT", "8765")),
            internal_port=int(os.environ.get("POKER_INTERNAL_PORT", "8766")),
            backup_dir=Path(os.environ.get("POKER_BACKUP_DIR", str(Path(__file__).resolve().parent.parent / "backups/poker/snapshots"))),
            export_dir=Path(os.environ.get("POKER_EXPORT_DIR", str(Path(__file__).resolve().parent.parent / "backups/poker/exports"))),
        )


def load_environment(path=None):
    """CLI only: fixed repository .env, no cwd search or shell evaluation."""
    from dotenv import load_dotenv

    load_dotenv(
        path or Path(__file__).resolve().parent.parent / ".env",
        override=False, encoding="utf-8-sig", interpolate=False,
    )
