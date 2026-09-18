import unittest
import uuid
from poker_tests.test_table_web import TableWebTests, A, B, C
from poker import chat
from poker.tables import load, save, initial

class ChatTests(TableWebTests):
    def post(self, user=A, text="你好 🃏", table_id="main", key=None, **extra):
        return self.client.post("/api/table/chat", headers=self.headers(user), json={"table_id": table_id, "client_message_id": key or uuid.uuid4().hex, "text": text, **extra})

    def history(self, user=A, table_id="main", after=0):
        return self.client.portal.call(chat.history, self.app.state.store, self.tokens[user], table_id, after)

    def mutate(self, operation):
        return self.client.portal.call(self.app.state.store.run, operation)

    def test_chat_identity_idempotency_and_no_game_changes(self):
        before = self.view()
        result = self.post(key="retry").json()
        self.assertEqual(result["message"]["author"]["id"], A)
        self.assertEqual(self.post(key="retry").json(), result)
        self.assertEqual(self.post(key="retry", text="different").status_code, 409)
        self.assertEqual(self.post(author={"id":B}).status_code, 422)
        after = self.view()
        self.assertEqual(before["version"], after["version"])
        self.assertNotIn("chat", after)
        self.assertEqual(len(self.history()["messages"]), 1)

    def test_unicode_and_literal_text(self):
        self.assertEqual(self.post(text=" 🃏"*200).status_code, 409)
        self.assertEqual(self.post(text="🃏"*200).status_code, 200)
        self.now += 2
        self.assertEqual(self.post(text="🃏"*201).status_code, 409)
        self.assertEqual(self.post(text="  ").status_code, 409)
        literal = '<img src=x onerror=alert(1)> https://example.com'
        self.assertEqual(self.post(text=literal).json()["message"]["text"],literal)

    def test_rate_limit_persists_across_connections_and_restart(self):
        for i in range(10):
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post().status_code, 409)
            self.now += 1.01
        self.assertEqual(self.post().status_code,409)
        self.assertEqual(self.post(B).status_code,200)
        self.restart()
        self.assertEqual(self.post().status_code,409)
        self.now += 61
        self.assertEqual(self.post().status_code,200)

    def test_history_retention_restart_and_old_retry(self):
        for i in range(101):
            self.assertEqual(self.post(text=str(i),key="msg"+str(i)).status_code,200)
            self.now += 7
        self.restart()
        messages = self.history()["messages"]
        self.assertEqual(len(messages),100)
        self.assertEqual(messages[0]["text"],"1")
        result = self.post(text="0",key="msg0").json()
        self.assertIsNone(result["message"])
        self.assertEqual(result["receipt"]["sequence"],1)
        self.assertEqual(self.history()["sequence"],101)

    def test_private_access_watchers_and_closure(self):
        def create(db):
            table=initial("private"); table.update(private=True, invitation="preview", watchers=[A]); save(db,table)
        self.mutate(create)
        self.assertEqual(self.post(A,table_id="private").status_code,200)
        self.assertEqual(self.post(B,table_id="private").status_code,409)
        response=self.client.post("/api/table/chat",headers={**self.headers(B),"x-table-invitation":"preview"},json={"table_id":"private","client_message_id":"preview","text":"no"})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.history(table_id="main")["messages"],[])
        def close(db):
            table=load(db,"private"); table["closed"]=True; save(db,table)
        self.mutate(close)
        self.assertEqual(self.history(table_id="private")["messages"],[])
        self.assertEqual(self.post(A,table_id="private").status_code,409)

    def test_ws_independent_sync_and_spectator(self):
        with self.client.websocket_connect("/ws/table?chat=1&table_id=main",headers=self.headers(B)) as socket:
            self.assertEqual(socket.receive_json()["type"],"ready")
            history=socket.receive_json(); self.assertTrue(history["initial"])
            self.assertEqual(self.post(A).status_code,200)
            for _ in range(6):
                message=socket.receive_json()
                if message["type"]=="chat": break
            self.assertEqual(message["type"],"chat")
            self.assertEqual(message["messages"][0]["author"]["id"],A)
            self.assertFalse(message["initial"])
        with self.client.websocket_connect("/ws/table?chat=1&table_id=main",headers=self.headers(B)) as socket:
            socket.receive_json()
            self.assertEqual(len(socket.receive_json()["messages"]),1)

    def test_origin_and_session(self):
        data={"table_id":"main","client_message_id":"no","text":"no"}
        self.assertEqual(self.client.post("/api/table/chat",json=data).status_code,403)
        self.assertEqual(self.client.post("/api/table/chat",headers={"origin":self.config.origin},json=data).status_code,401)

def load_tests(loader, tests, pattern):
    return unittest.TestSuite(ChatTests(name) for name in ChatTests.__dict__ if name.startswith("test_"))
