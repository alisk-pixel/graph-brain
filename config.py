"""Shared config: FalkorDB connection + tiny helpers used everywhere."""
import os
import re
import time

from falkordb import FalkorDB

HOST = os.environ.get("FALKOR_HOST", "localhost")
PORT = int(os.environ.get("FALKOR_PORT", "6379"))
USERNAME = os.environ.get("FALKOR_USER") or None        # FalkorDB Cloud: usually "falkordb"
PASSWORD = os.environ.get("FALKOR_PASSWORD") or None    # FalkorDB Cloud: from the dashboard
SSL = os.environ.get("FALKOR_SSL", "").lower() in ("1", "true", "yes")

_db = None


def db() -> FalkorDB:
    """Local Docker needs only host/port. FalkorDB Cloud also needs user + password (and maybe SSL)."""
    global _db
    url = os.environ.get("FALKOR_URL")
    if _db is None and url:
        # accept the dashboard's falkor:// / falkors:// style by converting to redis:// / rediss://
        url = url.replace("falkors://", "rediss://").replace("falkor://", "redis://")
        _db = FalkorDB.from_url(url)
    if _db is None:
        kwargs = {"host": HOST, "port": PORT}
        if USERNAME:
            kwargs["username"] = USERNAME
        if PASSWORD:
            kwargs["password"] = PASSWORD
        if SSL:
            kwargs["ssl"] = True
        _db = FalkorDB(**kwargs)
    return _db


def safe(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", (name or "").lower()) or "anon"


def study_graph(user_id: str):
    """One isolated graph per student (multi-tenant memory)."""
    return db().select_graph(f"user_{safe(user_id)}")


def company_graph(tenant: str = "nimbus"):
    """One isolated graph per company tenant."""
    return db().select_graph(f"company_{safe(tenant)}")


def now() -> float:
    return time.time()


def q(g, cypher: str, **params):
    """Run a Cypher query with parameters and return the rows."""
    return g.query(cypher, params=params).result_set
