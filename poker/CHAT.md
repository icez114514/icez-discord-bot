# Table chat

`POST /api/table/chat` accepts `table_id`, `client_message_id` and `text`.
Authentication, same-origin policy and table spectator authorization apply.
The server resolves the author; no client author or game version is accepted.
Text is trimmed, limited to 200 Unicode codepoints and rendered as plain text.

WebSocket clients opt in with `/ws/table?chat=1&table_id=...`. After `ready`,
a separate `chat` message supplies recent history (`initial: true`), then
ordered additions. Each message includes `table_id`, `sequence`, `closed`
and `messages`. Chat never changes game versions, events or animation queues.

The single SQLite writer stores the last 100 messages, sequence and per-user
rate timestamps in table JSON. Existing `game_commands` stores a namespaced
idempotency hash and receipt, never old message bodies. Retries return the same
receipt even after a message leaves the retention window. Closing a table
clears its chat and rate timestamps. Limits are one message per second and
ten per minute per user/table; they survive reconnects and service restarts.

Desktop chat shows a three-message preview without a heading in the bottom-left
corner. Viewports below 900px show a collapsed chat icon and unread badge instead.
Clicking either opens the full history and input in an accessible dialog. Uncertain sends
retain their original ID for explicit retry. Drafts survive closing the dialog
and connection loss, and table changes unmount the previous draft/pending UI.

Validation: `python -m unittest poker_tests.test_chat`, frontend `npm test`,
and `node poker_web/tools/check_table_chat.cjs` with `POKER_WEB_DIST` pointing
to an isolated Vite build. The browser tool uses simulated chat responses and
never sends messages to real players.
