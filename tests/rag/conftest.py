import pytest

from server.cases.loader import load_demo_case
from server.rag.embedding import HashEmbedding
from server.rag.indexer import index_case
from server.rag.retriever import HybridRetriever
from server.rag.store import RagStore
from server.schemas import Warrant

CASE_ID = "demo_db_deleted"
SLOT = "slot_test_1"


@pytest.fixture(scope="session")
def case():
    return load_demo_case()


@pytest.fixture()
def store(case):
    s = RagStore(":memory:", embedder=HashEmbedding(256))
    index_case(s, case, SLOT)
    yield s
    s.close()


@pytest.fixture()
def retriever(store):
    return HybridRetriever(store)


@pytest.fixture()
def all_warrants():
    return [
        Warrant(system="call", target_id="npc_yoon", from_time=0, to_time=2000),
        Warrant(system="bank", target_id="npc_yoon", from_time=0, to_time=2000),
    ]
