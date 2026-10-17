"""Thin native adapters with separate physical and public observations."""

import hashlib
import sqlite3


def sqlite_rows(path, query, parameters=()):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        cursor = db.execute(query, parameters)
        keys = [d[0] for d in cursor.description]
        return [dict(zip(keys, row)) for row in cursor.fetchall()]
    finally:
        db.close()


class Agentmem:
    def __init__(self, root):
        from agentmem import MemoryStore
        self.root = root
        self.store = MemoryStore(str(root / "memory.db"), embedding_dim=8, checkpoint_interval=0)
        if self.store._vec_mode != "sqlite-vec":
            raise ValueError("sqlite_vec_not_active")

    def add(self, text, namespace):
        result = self.store.remember(text, namespace=namespace, tier="core")
        return result["id"], result

    def update(self, identifier, text):
        result = self.store.update_memory(identifier, text)
        return result["id"], result

    def snapshot(self, known):
        current = self.store.recall("memoryprobe", namespace="fixture", limit=100, auto_translate=False)
        other = self.store.recall("memoryprobe", namespace="other", limit=100, auto_translate=False)
        sentinel = self.store.recall("memoryprobe", namespace="sentinel", limit=100, auto_translate=False)
        rows = sqlite_rows(self.root / "memory.db", "SELECT id,content,namespace,archived,supersedes FROM memories ORDER BY id")
        histories = {str(i): self.store.history(i) for i in sorted(set(known.values()))}
        return dict(public_current=current, current_contents=sorted(r["content"] for r in current),
            physical_contents=sorted(r["content"] for r in rows if r["namespace"] == "fixture" and r["archived"] == 0),
            physical_rows=rows, histories=histories, other_namespace_contents=sorted(r["content"] for r in other),
            sentinel_contents=sorted(r["content"] for r in sentinel), writer_in_transaction=self.store.db.in_transaction,
            sqlite_integrity=sqlite_rows(self.root / "memory.db", "PRAGMA integrity_check"))

    def close(self):
        self.store.close()


class StaticEmbedding:
    def embed(self, text, *args, **kwargs):
        data = hashlib.sha256(str(text).encode()).digest()
        return [((v / 255.0) * 2.0 - 1.0) for v in data[:8]]


class Mem0:
    def __init__(self, root):
        from mem0 import Memory
        self.root = root
        config = dict(vector_store=dict(provider="qdrant", config=dict(collection_name="benign_versions",
                    path=str((root / "qdrant").resolve()), embedding_model_dims=8)),
                history_db_path=str((root / "history.db").resolve()),
                llm=dict(provider="openai", config=dict(api_key="offline-placeholder")),
                embedder=dict(provider="openai", config=dict(api_key="offline-placeholder")))
        self.memory = Memory.from_config(config)
        self.memory.embedding_model = StaticEmbedding()

    def add(self, text, namespace):
        result = self.memory.add(text, user_id=namespace, infer=False)
        if result["results"]:
            identifier = result["results"][0]["id"]
        else:
            candidates = self.memory.get_all(filters={"user_id": namespace}, top_k=100)["results"]
            identifier = next(r["id"] for r in candidates if r["memory"] == text)
        return identifier, result

    def update(self, identifier, text):
        return identifier, self.memory.update(identifier, text)

    def snapshot(self, known):
        from qdrant_client import models
        current = self.memory.get_all(filters={"user_id": "fixture"}, top_k=100)["results"]
        other = self.memory.get_all(filters={"user_id": "other"}, top_k=100)["results"]
        sentinel = self.memory.get_all(filters={"user_id": "sentinel"}, top_k=100)["results"]
        records, continuation = self.memory.vector_store.client.scroll(collection_name="benign_versions",
            scroll_filter=models.Filter(must=[models.FieldCondition(key="user_id", match=models.MatchValue(value="fixture"))]),
            limit=100, with_payload=True, with_vectors=False)
        if continuation is not None:
            raise ValueError("physical_observation_truncated")
        physical = [dict(id=str(r.id), payload=r.payload) for r in records]
        return dict(public_current=current, current_contents=sorted(r["memory"] for r in current),
            physical_contents=sorted(r["payload"]["data"] for r in physical), physical_rows=physical,
            histories={str(i): self.memory.history(i) for i in sorted(set(known.values()))},
            other_namespace_contents=sorted(r["memory"] for r in other),
            sentinel_contents=sorted(r["memory"] for r in sentinel),
            physical_event_rows=sqlite_rows(self.root / "history.db", "SELECT * FROM history ORDER BY rowid"),
            sqlite_integrity=sqlite_rows(self.root / "history.db", "PRAGMA integrity_check"))

    def close(self):
        for name in ("vector_store", "_telemetry_vector_store"):
            client = getattr(getattr(self.memory, name, None), "client", None)
            if client is not None:
                client.close()
        self.memory.db.close()
