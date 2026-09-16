"""Public voice identity; listener volume/mute preferences remain private."""

VOICE_PACKS = ("oneesan", "shoujo", "nekomimi")


def voice_for(db, member):
    if member["id"].startswith("npc:"):
        # Legacy NPC identifiers are already random; keep their fallback stable.
        return member.get("voice_pack") or VOICE_PACKS[
            sum(member["id"].encode()) % len(VOICE_PACKS)
        ]
    row = db.execute(
        "SELECT voice_pack FROM account_voices WHERE user_id=?", (member["id"],)
    ).fetchone()
    return row[0] if row else VOICE_PACKS[0]
