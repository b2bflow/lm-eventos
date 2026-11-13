"""Tags (etiquetas) dos clientes: catálogo criado pela equipe, várias tags por cliente, editadas pelo
contato ou pelo perfil da conversa, e a tag automática da IA (customer_custom_tag) convivendo com elas."""
import pytest

from chat.models.conversation_model import ConversationModel
from crm.models.custumer_model import Customer
from crm.models.customer_tag_model import CustomerTag, tag_key
from crm.models.log_service_model import ServiceLog
from crm.repositories.customer_repository import CustomerRepository
from database.client.mongodb_client import MongoDBClient
from sales.models import Proposal  # noqa: F401  (carrega as regras de exclusão em cadeia)

TAGS = "/api/v1/crm/tags/"
CONTACTS = "/api/v1/crm/contacts/"
CONVERSATIONS = "/api/v1/chat/conversations/"


def contact_tags_url(customer):
    return f"{CONTACTS}{customer.id}/tags/"


@pytest.fixture
def customer():
    customer = Customer(name="Marina Souza", phone="5562991234567", product="corporativo").save()
    ConversationModel(customer=customer, tag="OPERADOR", ai_active=False).save()
    return customer


def create(client, name, **extra):
    resp = client.post(TAGS, {"name": name, **extra}, format="json")
    assert resp.status_code in (200, 201), resp.data
    return resp.data


def test_tag_key_ignores_accents_case_and_punctuation():
    assert tag_key("Orçamento") == "orcamento"
    assert tag_key("  Visita   Técnica ") == "visita tecnica"
    assert tag_key("Pós-venda!") == "pos venda"
    assert tag_key("😀") == ""


@pytest.mark.django_db
def test_catalog_has_builtin_tags_and_creating_same_name_returns_existing(sdr_api):
    keys = {t["key"]: t for t in sdr_api.get(TAGS).data}
    assert {"visita tecnica", "operador humano", "orcamento"} <= set(keys)
    assert keys["orcamento"]["name"] == "Orçamento" and keys["orcamento"]["builtin"] is True

    resp = sdr_api.post(TAGS, {"name": "VIP", "color": "pink"}, format="json")
    assert resp.status_code == 201
    assert resp.data["key"] == "vip" and resp.data["color"] == "pink" and resp.data["builtin"] is False
    again = sdr_api.post(TAGS, {"name": "vip"}, format="json")
    assert again.status_code == 200 and again.data["id"] == resp.data["id"]
    assert sdr_api.post(TAGS, {"name": "   "}, format="json").status_code == 400
    assert sdr_api.post(TAGS, {"name": "x" * 41}, format="json").status_code == 400
    assert sdr_api.post(TAGS, {"name": "Nova", "color": "dourado"}, format="json").status_code == 400


@pytest.mark.django_db
def test_set_customer_tags_from_contact_and_timeline(sdr_api, customer):
    vip = create(sdr_api, "VIP")
    create(sdr_api, "Casamento 2027")

    resp = sdr_api.put(contact_tags_url(customer), {"tags": ["vip", "casamento 2027", "vip"]}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["tags"] == ["vip", "casamento 2027"]
    assert CONTACTS and sdr_api.get(f"{CONTACTS}{customer.id}/").data["tags"] == ["vip", "casamento 2027"]

    log = ServiceLog.objects(customer=customer, action_type="TAGS_CHANGED").first()
    assert "+ VIP" in log.description and "+ Casamento 2027" in log.description

    resp = sdr_api.put(contact_tags_url(customer), {"tags": ["casamento 2027"]}, format="json")
    assert resp.data["tags"] == ["casamento 2027"]
    assert "− VIP" in ServiceLog.objects(customer=customer, action_type="TAGS_CHANGED").order_by("-created_at").first().description
    # Sem mudança: não registra de novo.
    sdr_api.put(contact_tags_url(customer), {"tags": ["casamento 2027"]}, format="json")
    assert ServiceLog.objects(customer=customer, action_type="TAGS_CHANGED").count() == 2
    assert vip["key"] == "vip"


@pytest.mark.django_db
def test_set_customer_tags_rejects_unknown_and_bad_payload(sdr_api, customer):
    assert sdr_api.put(contact_tags_url(customer), {"tags": ["nao existe"]}, format="json").status_code == 400
    assert sdr_api.put(contact_tags_url(customer), {"tags": "vip"}, format="json").status_code == 400
    assert sdr_api.put(f"{CONTACTS}xyz/tags/", {"tags": []}, format="json").status_code == 400


@pytest.mark.django_db
def test_automatic_tag_shows_with_team_tags_and_can_be_removed(sdr_api, customer):
    create(sdr_api, "VIP")
    # A IA marca "operador humano" (customer_custom_tag), como em ai_agents/tools/humano_tool.py.
    CustomerRepository(MongoDBClient()).update(id=str(customer.id), attributes={"customer_custom_tag": "operador humano"})
    assert sdr_api.get(f"{CONTACTS}{customer.id}/").data["tags"] == ["operador humano"]

    # Mantendo a automática e somando VIP: a automática continua no campo dela.
    resp = sdr_api.put(contact_tags_url(customer), {"tags": ["operador humano", "vip"]}, format="json")
    assert resp.data["tags"] == ["vip", "operador humano"]
    customer.reload()
    assert customer.customer_custom_tag == "operador humano" and customer.tags == ["vip"]

    # A IA troca a automática; a da equipe fica.
    CustomerRepository(MongoDBClient()).update(id=str(customer.id), attributes={"customer_custom_tag": "orcamento"})
    customer.reload()
    assert customer.tag_keys == ["vip", "orcamento"]

    # Tirar a automática à mão limpa o campo.
    resp = sdr_api.put(contact_tags_url(customer), {"tags": ["vip"]}, format="json")
    assert resp.data["tags"] == ["vip"]
    customer.reload()
    assert customer.customer_custom_tag is None

    # Pôr uma tag automática à mão a deixa entre as da equipe (a IA não tira).
    sdr_api.put(contact_tags_url(customer), {"tags": ["vip", "visita tecnica"]}, format="json")
    customer.reload()
    assert customer.tags == ["vip", "visita tecnica"] and customer.customer_custom_tag is None


@pytest.mark.django_db
def test_conversation_list_shows_and_filters_by_customer_tag(sdr_api, customer):
    create(sdr_api, "VIP")
    other = Customer(name="Paulo", phone="5562990000001", customer_custom_tag="orcamento").save()
    ConversationModel(customer=other, tag="OPERADOR", ai_active=False).save()
    sdr_api.put(contact_tags_url(customer), {"tags": ["vip"]}, format="json")

    def listed(**params):
        data = sdr_api.get(CONVERSATIONS, {"status": "OPEN", **params}).data["results"]
        return {c["customer_name"]: c["customer_tags"] for c in data}

    assert listed() == {"Marina Souza": ["vip"], "Paulo": ["orcamento"]}
    assert listed(customer_tag="vip") == {"Marina Souza": ["vip"]}
    assert listed(customer_tag="orcamento") == {"Paulo": ["orcamento"]}


@pytest.mark.django_db
def test_contacts_list_filters_by_tag(sdr_api, customer):
    create(sdr_api, "VIP")
    Customer(name="Paulo", phone="5562990000001", customer_custom_tag="orcamento").save()
    sdr_api.put(contact_tags_url(customer), {"tags": ["vip"]}, format="json")

    names = lambda **p: [c["name"] for c in sdr_api.get(CONTACTS, p).data["results"]]  # noqa: E731
    assert names(tag="vip") == ["Marina Souza"]
    assert names(tag="orcamento") == ["Paulo"]
    results = {c["name"]: c["tags"] for c in sdr_api.get(CONTACTS).data["results"]}
    assert results == {"Marina Souza": ["vip"], "Paulo": ["orcamento"]}


@pytest.mark.django_db
def test_only_admin_renames_recolors_and_deletes(api_client, sdr_api, customer):
    vip = create(sdr_api, "VIP")
    sdr_api.put(contact_tags_url(customer), {"tags": ["vip"]}, format="json")
    assert sdr_api.patch(f"{TAGS}{vip['id']}/", {"name": "Cliente VIP"}, format="json").status_code == 403
    assert sdr_api.delete(f"{TAGS}{vip['id']}/").status_code == 403

    resp = api_client.patch(f"{TAGS}{vip['id']}/", {"name": "Cliente VIP", "color": "emerald"}, format="json")
    assert resp.status_code == 200 and resp.data["name"] == "Cliente VIP" and resp.data["key"] == "vip"
    create(sdr_api, "Retornar")
    assert api_client.patch(f"{TAGS}{vip['id']}/", {"name": "retornar"}, format="json").status_code == 400
    # Renomear não muda a chave, mas o nome novo também conta como repetido.
    same = sdr_api.post(TAGS, {"name": "cliente vip"}, format="json")
    assert same.status_code == 200 and same.data["id"] == vip["id"]

    counts = {t["key"]: t["count"] for t in api_client.get(TAGS, {"counts": "1"}).data}
    assert counts["vip"] == 1 and counts["retornar"] == 0

    resp = api_client.delete(f"{TAGS}{vip['id']}/")
    assert resp.status_code == 200 and resp.data["removed_from"] == 1
    customer.reload()
    assert customer.tags == []
    assert not CustomerTag.objects(key="vip").first()

    builtin = CustomerTag.objects(key="orcamento").first()
    assert api_client.delete(f"{TAGS}{builtin.id}/").status_code == 400
    assert api_client.delete(f"{TAGS}aaaaaaaaaaaaaaaaaaaaaaaa/").status_code == 404


@pytest.mark.django_db
def test_crm_customer_page_filter_matches_team_tags(api_client, customer):
    from crm.models.quote_model import Quote
    Quote(customer=customer, status="ANALYSIS").save()
    create(api_client, "Visita técnica")  # já existe (automática): só devolve
    api_client.put(contact_tags_url(customer), {"tags": ["visita tecnica"]}, format="json")
    data = api_client.get("/api/v1/crm/quotes/", {"customer_custom_tag": "visita tecnica"}).data
    results = data["results"] if isinstance(data, dict) else data
    assert [q["customer_tags"] for q in results] == [["visita tecnica"]]
