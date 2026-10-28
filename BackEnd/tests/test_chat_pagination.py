"""B6: lista de conversas e mensagens paginadas por cursor."""
from datetime import datetime, timedelta

import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer

BASE = datetime(2026, 10, 1, 12, 0, 0)


def make_conversations(n):
    convs = []
    for i in range(n):
        customer = Customer(name=f"Cliente {i:03d}", phone=f"55629{i:08d}").save()
        convs.append(ConversationModel(customer=customer, updated_at=BASE + timedelta(minutes=i)).save())
    return convs


def fetch_all(api_client, url, page_size):
    seen, cursor = [], None
    while True:
        params = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        data = api_client.get(url, params).data
        seen.extend(item["id"] for item in data["results"])
        cursor = data["next_cursor"]
        if not data["has_more"]:
            return seen


@pytest.mark.django_db
def test_scroll_reaches_every_conversation_without_duplicates(api_client):
    convs = make_conversations(55)
    ids = fetch_all(api_client, "/api/v1/chat/conversations/", page_size=20)
    assert len(ids) == 55 and len(set(ids)) == 55
    # mais recente primeiro
    assert ids[0] == str(convs[-1].id)


@pytest.mark.django_db
def test_conversation_moving_to_top_does_not_repeat_or_skip(api_client):
    convs = make_conversations(30)
    first = api_client.get("/api/v1/chat/conversations/", {"page_size": 10}).data
    first_ids = [c["id"] for c in first["results"]]

    # Uma conversa da primeira página recebe mensagem e vai para o topo
    moved = ConversationModel.objects.get(id=first_ids[5])
    moved.last_message_at = BASE + timedelta(days=1)
    moved.save()

    rest, cursor = [], first["next_cursor"]
    while cursor:
        page = api_client.get("/api/v1/chat/conversations/", {"page_size": 10, "cursor": cursor}).data
        rest.extend(c["id"] for c in page["results"])
        cursor = page["next_cursor"]

    assert len(first_ids) + len(rest) == 30
    assert set(first_ids).isdisjoint(rest)
    assert len(set(first_ids + rest)) == len(convs)


@pytest.mark.django_db
def test_page_size_limits(api_client):
    make_conversations(60)
    assert len(api_client.get("/api/v1/chat/conversations/").data["results"]) == 20
    assert len(api_client.get("/api/v1/chat/conversations/", {"page_size": 500}).data["results"]) == 50


@pytest.mark.django_db
def test_search_runs_in_database_by_name_or_phone(api_client):
    make_conversations(60)
    by_name = api_client.get("/api/v1/chat/conversations/", {"search": "cliente 001"}).data["results"]
    assert [c["customer_name"] for c in by_name] == ["Cliente 001"]
    by_phone = api_client.get("/api/v1/chat/conversations/", {"search": "(62) 9000-00002"}).data["results"]
    assert {c["customer_name"] for c in by_phone} >= {"Cliente 002"}


@pytest.mark.django_db
def test_filters_by_tag_and_attention(api_client):
    convs = make_conversations(5)
    convs[0].tag = "AGENTE"
    convs[0].needs_attention = True
    convs[0].save()
    assert len(api_client.get("/api/v1/chat/conversations/", {"tag": "AGENTE"}).data["results"]) == 1
    assert len(api_client.get("/api/v1/chat/conversations/", {"needs_attention": "true"}).data["results"]) == 1
    convs[1].status = "CLOSED"
    convs[1].save()
    open_page = api_client.get("/api/v1/chat/conversations/", {"status": "OPEN", "page_size": 1}).data
    assert open_page["total"] == 4 and len(open_page["results"]) == 1
    assert api_client.get("/api/v1/chat/conversations/", {"status": "CLOSED"}).data["total"] == 1


@pytest.mark.django_db
def test_invalid_cursor_returns_400(api_client):
    assert api_client.get("/api/v1/chat/conversations/", {"cursor": "lixo"}).status_code == 400


@pytest.mark.django_db
def test_long_conversation_opens_on_latest_and_loads_older_pages(api_client):
    conv = make_conversations(1)[0]
    for i in range(300):
        MessageModel(conversation=conv, customer=conv.customer, role="user", direction="INCOMING",
                     content=f"m{i}", created_at=BASE + timedelta(seconds=i)).save()

    url = "/api/v1/chat/messages/"
    first = api_client.get(url, {"conversation": str(conv.id)}).data
    assert [m["content"] for m in first["results"]] == [f"m{i}" for i in range(270, 300)]
    assert first["has_more"] is True

    older = api_client.get(url, {"conversation": str(conv.id), "cursor": first["next_cursor"]}).data
    assert [m["content"] for m in older["results"]] == [f"m{i}" for i in range(240, 270)]

    contents, cursor = [], None
    while True:
        params = {"conversation": str(conv.id), "page_size": 100}
        if cursor:
            params["cursor"] = cursor
        page = api_client.get(url, params).data
        contents = [m["content"] for m in page["results"]] + contents
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert contents == [f"m{i}" for i in range(300)]


@pytest.mark.django_db
def test_retrieve_single_conversation_by_id(api_client):
    from chat.models.conversation_model import ConversationModel
    from crm.models.custumer_model import Customer
    conversation = ConversationModel(customer=Customer(name="Zé", phone="5562911112222").save()).save()
    resp = api_client.get(f"/api/v1/chat/conversations/{conversation.id}/")
    assert resp.status_code == 200, resp.data
    assert resp.data["id"] == str(conversation.id)
