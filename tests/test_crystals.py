import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

import bot
from crystal_commands import CrystalFeature, balance_embed, ranking_embed, DATABASE_UNAVAILABLE
from crystal_rules import (
    CRYSTAL_EMOJI, DOUBLE_ROLE_ID, LEVEL_ROLES, can_claim,
    daily_reward, is_crystal_message, level_for_roles,
)
from database import Account, ClaimResult, DatabaseError, connection_parameters, parse_import


def member(*roles):
    return SimpleNamespace(id=123, display_name="測試使用者", bot=False, roles=list(roles))


def interaction(user=None):
    return SimpleNamespace(
        guild=object(), user=user or member(),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )


def message(content=CRYSTAL_EMOJI, user=None):
    return SimpleNamespace(
        guild=object(), author=user or member(), webhook_id=None,
        content=content, channel=SimpleNamespace(send=AsyncMock()),
    )


class RewardTests(unittest.TestCase):
    def test_all_original_levels(self):
        self.assertEqual(len(LEVEL_ROLES), 20)
        self.assertEqual(set(LEVEL_ROLES.values()), {
            1, 5, 10, 15, 20, 25, 30, 35, 40, 44,
            48, 52, 56, 60, 64, 68, 72, 76, 80, 150,
        })
        for name, level in LEVEL_ROLES.items():
            with self.subTest(name=name):
                self.assertEqual(level_for_roles([name]), level)
                low = math.ceil(level / 1.5)
                high = math.floor(math.nextafter(1, 0) * level * 2.5 + low)
                self.assertEqual(daily_reward(level, False, sample=0), low)
                self.assertEqual(daily_reward(level, False, sample=math.nextafter(1, 0)), high)
                self.assertEqual(daily_reward(level, True, sample=0), low * 2)

    def test_highest_level_and_exact_names(self):
        self.assertEqual(level_for_roles(LEVEL_ROLES), 150)
        self.assertEqual(level_for_roles([]), 1)
        self.assertEqual(level_for_roles(["LV.150 wrong", "LV.80 血色玫瑰 "]), 1)

    def test_original_fractional_distribution(self):
        # Level 1 has a half-width upper interval; randint(1, 3) is not equivalent.
        self.assertEqual([daily_reward(1, False, sample=x) for x in (0, .399, .4, .799, .8)], [1, 1, 2, 2, 3])

    def test_invalid_random_samples(self):
        for sample in (-.1, 1, float("nan")):
            with self.assertRaises(ValueError):
                daily_reward(1, False, sample=sample)

    def test_full_dates_and_clock_rollback(self):
        for previous, today, expected in [
            (None, date(2026, 9, 6), True),
            (date(2026, 9, 6), date(2026, 9, 6), False),
            (date(2026, 9, 6), date(2026, 9, 7), True),
            (date(2026, 9, 30), date(2026, 10, 1), True),
            (date(2026, 12, 31), date(2027, 1, 1), True),
            (date(2026, 8, 6), date(2026, 9, 6), True),
            (date(2026, 9, 7), date(2026, 9, 6), False),
        ]:
            with self.subTest(previous=previous, today=today):
                self.assertEqual(can_claim(previous, today), expected)

    def test_exact_emoji_only(self):
        self.assertTrue(is_crystal_message("  " + CRYSTAL_EMOJI + "\n"))
        for content in ("hello " + CRYSTAL_EMOJI, CRYSTAL_EMOJI + " rank", ":crystal:", "💎", ""):
            self.assertFalse(is_crystal_message(content))


class ImportTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return parse_import(path)

    def test_valid_import_preserves_large_integer_and_ids(self):
        self.assertEqual(
            self.parse([{"user_id": str(2**64 - 1), "balance": 10**100 + 1}]),
            [Account(2**64 - 1, 10**100 + 1)],
        )

    def test_invalid_rows(self):
        rows = [
            {"user_id": 123, "balance": 1},
            {"user_id": "0", "balance": 1},
            {"user_id": str(2**64), "balance": 1},
            {"user_id": "123", "balance": True},
            {"user_id": "123", "balance": 1.5},
            {"user_id": "123", "balance": -1},
            {"user_id": "123", "balance": 1, "display_name": "x" * 129},
            {"user_id": "123", "balance": 1, "unknown": 1},
            {"user_id": "１２３", "balance": 1},
        ]
        for row in rows:
            with self.subTest(row=row), self.assertRaises(DatabaseError):
                self.parse([row])

    def test_duplicate_normalized_ids_and_empty_file(self):
        for value in ([], {}, [{"user_id": "123", "balance": 1}, {"user_id": "0123", "balance": 2}]):
            with self.assertRaises(DatabaseError):
                self.parse(value)

    def test_connection_errors_do_not_echo_secrets(self):
        for dsn in ("a_secret_not_a_dsn", "postgresql://u:SECRET@host/db?sslmode=disable"):
            with self.assertRaises(DatabaseError) as result:
                connection_parameters(dsn)
            self.assertNotIn("SECRET", str(result.exception))
            self.assertNotIn("a_secret", str(result.exception))


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = SimpleNamespace(
            claim=AsyncMock(return_value=ClaimResult(17, 7)),
            leaderboard=AsyncMock(return_value=[]),
        )
        self.feature = CrystalFeature(self.store)

    async def test_single_slash_with_optional_choice(self):
        client = bot.create_bot(store=self.store)
        async with client:
            commands = client.tree.get_commands()
            self.assertEqual({c.name for c in commands}, {"ping", "水晶"})
            command = client.tree.get_command("水晶")
            option = command.parameters[0]
            self.assertEqual(option.display_name, "操作")
            self.assertFalse(option.required)
            self.assertEqual(option.default, "daily")
            self.assertEqual([(c.name, c.value) for c in option.choices], [
                ("簽到／查詢", "daily"), ("排行榜", "rank"),
            ])
            self.assertTrue(command.guild_only)
            self.assertTrue(client.intents.message_content)

    async def test_default_slash_defers_before_claim(self):
        events = []
        request = interaction()
        request.response.defer.side_effect = lambda **kw: events.append("defer")
        async def claim(*args):
            events.append("claim")
            return ClaimResult(17, 7)
        self.store.claim.side_effect = claim
        await self.feature.slash(request)
        self.assertEqual(events, ["defer", "claim"])
        self.store.leaderboard.assert_not_awaited()
        request.edit_original_response.assert_awaited_once()
        self.assertFalse(request.edit_original_response.call_args.kwargs["allowed_mentions"].everyone)

    async def test_rank_never_claims_or_creates_account(self):
        request = interaction()
        await self.feature.slash(request, "rank")
        self.store.claim.assert_not_awaited()
        self.store.leaderboard.assert_awaited_once()
        self.assertIn("尚無", request.edit_original_response.call_args.kwargs["embed"].description)

    async def test_both_entrypoints_use_same_reward_rules(self):
        user = member(
            SimpleNamespace(id=1, name="LV.1 領域裝．白練"),
            SimpleNamespace(id=DOUBLE_ROLE_ID, name="special"),
            SimpleNamespace(id=2, name="LV.80 血色玫瑰"),
        )
        async def claim(uid, name, calculate):
            self.assertEqual((uid, name), (123, "測試使用者"))
            self.assertEqual(calculate(), 108)
            return ClaimResult(118, 108)
        self.store.claim.side_effect = claim
        with patch("crystal_rules.random.random", return_value=0):
            await self.feature.slash(interaction(user))
            await self.feature.on_message(message(user=user))
        self.assertEqual(self.store.claim.await_count, 2)

    async def test_message_filters(self):
        cases = [message("chat " + CRYSTAL_EMOJI), message(), message(), message()]
        cases[1].guild = None
        cases[2].author.bot = True
        cases[3].webhook_id = 999
        for request in cases:
            await self.feature.on_message(request)
            request.channel.send.assert_not_awaited()
        self.store.claim.assert_not_awaited()

    async def test_private_slash_is_rejected(self):
        request = interaction()
        request.guild = None
        await self.feature.slash(request)
        self.store.claim.assert_not_awaited()
        request.response.send_message.assert_awaited_once()

    async def test_database_failure_is_safe(self):
        self.store.claim.side_effect = DatabaseError("private internal information")
        request = interaction()
        await self.feature.slash(request)
        self.assertEqual(request.edit_original_response.call_args.kwargs["content"], DATABASE_UNAVAILABLE)

    async def test_failed_delivery_does_not_retry_reward(self):
        request = message()
        response = SimpleNamespace(status=403, reason="Forbidden")
        request.channel.send.side_effect = discord.Forbidden(response, "missing access")
        await self.feature.on_message(request)
        self.store.claim.assert_awaited_once()

    async def test_embeds_for_daily_repeat_and_short_rank(self):
        daily = balance_embed(ClaimResult(17, 7), "x", 1)
        self.assertEqual(daily.color.value, 0xDC9FB4)
        self.assertEqual(len(daily.fields), 2)
        repeat = balance_embed(ClaimResult(17, None), "x", 1)
        self.assertEqual(len(repeat.fields), 1)
        ranking = ranking_embed([Account(123, 10), Account(456, 9, "@everyone")])
        self.assertEqual(len(ranking.fields), 2)
        self.assertIn("123", ranking.fields[0].value)
        self.assertNotIn("@everyone", ranking.fields[1].value)
