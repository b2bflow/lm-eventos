"""Estoque maleável: cadastro e remoção pela tela, ajuste de quantidade, ficha com observações,
reserva manual e opcional (liga/desliga nas configurações) e busca por nome."""
from datetime import datetime
from io import StringIO

import pytest
from django.core.management import call_command

from crm.models.lm_settings_model import LmSettings
from inventory.models import InventoryItem, InventoryReservation
from inventory.services.inventory_service import InventoryService

URL = "/api/v1/inventory"


@pytest.fixture
def stock():
    call_command("seed_inventory", stdout=StringIO())


def _item(code="q30_torre_5m"):
    return InventoryItem.objects.get(code=code)


def _reservations(enabled: bool):
    cfg = LmSettings.get()
    cfg.inventory_reservations_enabled = enabled
    cfg.save()


# --- Cadastro e remoção ----------------------------------------------------------------------

@pytest.mark.django_db
def test_create_item_without_code_generates_one(porta_api):
    resp = porta_api.post(f"{URL}/items/", {"name": "Moving head", "line": "Iluminação", "qty_total": 6,
                                            "description": "Beam 230W"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["code"] == "iluminacao_moving_head" and resp.data["description"] == "Beam 230W"
    again = porta_api.post(f"{URL}/items/", {"name": "Moving head", "line": "Iluminação"}, format="json")
    assert again.data["code"] == "iluminacao_moving_head_2"


@pytest.mark.django_db
def test_sdr_cannot_create_or_remove_items(sdr_api, stock):
    assert sdr_api.post(f"{URL}/items/", {"name": "X", "line": "Som"}, format="json").status_code == 403
    assert sdr_api.delete(f"{URL}/items/{_item().id}/").status_code == 403


@pytest.mark.django_db
def test_remove_deactivates_and_restore_brings_back(porta_api, stock):
    item = _item()
    assert porta_api.delete(f"{URL}/items/{item.id}/").status_code == 204
    codes = [r["code"] for r in porta_api.get(f"{URL}/items/").data]
    assert item.code not in codes
    removed = porta_api.get(f"{URL}/items/", {"include_inactive": "1"}).data
    assert any(r["code"] == item.code and not r["active"] for r in removed)
    assert porta_api.patch(f"{URL}/items/{item.id}/", {"active": True}, format="json").status_code == 200
    assert item.code in [r["code"] for r in porta_api.get(f"{URL}/items/").data]


@pytest.mark.django_db
def test_permanent_delete_only_without_history(porta_api, stock):
    item = _item()
    assert porta_api.delete(f"{URL}/items/{item.id}/?permanent=1").status_code == 204
    assert not InventoryItem.objects(code="q30_torre_5m").first()

    other = _item("q30_cubo_5_faces")
    porta_api.post(f"{URL}/reservations/", {"item_id": str(other.id), "qty": 2, "start": "2026-11-10",
                                            "end": "2026-11-11", "client_name": "Feira X"}, format="json")
    resp = porta_api.delete(f"{URL}/items/{other.id}/?permanent=1")
    assert resp.status_code == 400 and InventoryItem.objects(code="q30_cubo_5_faces").first()


# --- Ajuste de quantidade e observações --------------------------------------------------------

@pytest.mark.django_db
def test_adjust_quantity_logs_reason(porta_api, stock):
    item = _item()
    resp = porta_api.post(f"{URL}/items/{item.id}/adjust/", {"delta": -3, "reason": "torres amassadas"}, format="json")
    assert resp.status_code == 200 and resp.data["qty_total"] == 110
    detail = porta_api.get(f"{URL}/items/{item.id}/").data
    assert detail["observations"][0]["kind"] == "ajuste"
    assert "Baixa de 3" in detail["observations"][0]["text"] and "amassadas" in detail["observations"][0]["text"]
    assert porta_api.post(f"{URL}/items/{item.id}/adjust/", {"delta": -500, "reason": "x"},
                          format="json").status_code == 400
    assert porta_api.post(f"{URL}/items/{item.id}/adjust/", {"delta": 2}, format="json").status_code == 400


@pytest.mark.django_db
def test_observations_any_user_writes_author_or_editor_deletes(sdr_api, porta_api, stock):
    item = _item()
    resp = sdr_api.post(f"{URL}/items/{item.id}/observations/", {"text": "2 torres com solda trincada"}, format="json")
    assert resp.status_code == 201 and resp.data["author_name"]
    obs_id = resp.data["id"]
    assert sdr_api.post(f"{URL}/items/{item.id}/observations/", {"text": "  "}, format="json").status_code == 400

    own = sdr_api.post(f"{URL}/items/{item.id}/observations/", {"text": "guardadas no galpão 2"}, format="json").data
    assert sdr_api.delete(f"{URL}/items/{item.id}/observations/{own['id']}/").status_code == 204
    assert porta_api.delete(f"{URL}/items/{item.id}/observations/{obs_id}/").status_code == 204
    assert _item().observations == []


@pytest.mark.django_db
def test_sdr_cannot_delete_someone_elses_observation(sdr_api, porta_api, stock):
    item = _item()
    obs = porta_api.post(f"{URL}/items/{item.id}/observations/", {"text": "manutenção dia 20"}, format="json").data
    assert sdr_api.delete(f"{URL}/items/{item.id}/observations/{obs['id']}/").status_code == 403


# --- Reserva manual e opcional -------------------------------------------------------------

@pytest.mark.django_db
def test_manual_reservation_reduces_availability_and_can_be_cancelled(sdr_api, porta_api, stock):
    item = _item()
    resp = sdr_api.post(f"{URL}/reservations/", {"item_id": str(item.id), "qty": 13, "start": "2026-11-10",
                                                 "end": "2026-11-12", "client_name": "Show da praça"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["manual"] and resp.data["customer_name"] == "Show da praça"
    row = next(r for r in sdr_api.get(f"{URL}/items/", {"start": "2026-11-11", "end": "2026-11-11"}).data
               if r["code"] == item.code)
    assert row["reserved"] == 13 and row["available"] == 100

    too_much = sdr_api.post(f"{URL}/reservations/", {"item_id": str(item.id), "qty": 101, "start": "2026-11-11",
                                                     "end": "2026-11-11", "client_name": "Outro"}, format="json")
    assert too_much.status_code == 400 and "100" in too_much.data["detail"]

    detail = sdr_api.get(f"{URL}/items/{item.id}/").data
    assert [r["id"] for r in detail["reservations"]] == [resp.data["id"]]
    assert sdr_api.delete(f"{URL}/reservations/{resp.data['id']}/").status_code == 200
    assert InventoryReservation.objects.get(id=resp.data["id"]).status == "cancelado"


@pytest.mark.django_db
def test_manual_reservation_of_pieces_needs_whole_quantity(sdr_api, stock):
    resp = sdr_api.post(f"{URL}/reservations/", {"item_id": str(_item().id), "qty": 1.5, "start": "2026-11-10",
                                                 "end": "2026-11-12", "client_name": "Show"}, format="json")
    assert resp.status_code == 400 and "inteiro" in resp.data["detail"]


@pytest.mark.django_db
def test_manual_reservation_needs_a_client(sdr_api, stock):
    resp = sdr_api.post(f"{URL}/reservations/", {"item_id": str(_item().id), "qty": 1, "start": "2026-11-10"},
                        format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_proposal_reservation_is_not_cancelled_from_inventory_screen(porta_api, stock):
    reservation = InventoryReservation(item=_item(), proposal_id="abc", qty=1,
                                       start=datetime(2026, 11, 10),
                                       end=datetime(2026, 11, 11)).save()
    assert porta_api.delete(f"{URL}/reservations/{reservation.id}/").status_code == 400


@pytest.mark.django_db
def test_reservations_disabled_nothing_reserves_and_available_is_total(sdr_api, stock):
    item = _item()
    InventoryReservation(item=item, proposal_id="abc", qty=50, start=datetime(2026, 11, 10),
                         end=datetime(2026, 11, 12)).save()
    _reservations(False)
    row = next(r for r in sdr_api.get(f"{URL}/items/", {"start": "2026-11-10", "end": "2026-11-11"}).data
               if r["code"] == item.code)
    assert row["reserved"] is None and row["available"] == 113
    assert InventoryService().availability([item.code], datetime(2026, 11, 10), datetime(2026, 11, 12)) == {
        item.code: 113}
    assert InventoryService().reserve("p2", None, [{"code": item.code, "qty": 5}], datetime(2026, 11, 10),
                                      datetime(2026, 11, 12)) == []
    resp = sdr_api.post(f"{URL}/reservations/", {"item_id": str(item.id), "qty": 1, "start": "2026-11-10",
                                                 "client_name": "X"}, format="json")
    assert resp.status_code == 400 and "desligada" in resp.data["detail"]

    _reservations(True)
    row = next(r for r in sdr_api.get(f"{URL}/items/", {"start": "2026-11-10", "end": "2026-11-11"}).data
               if r["code"] == item.code)
    assert row["reserved"] == 50 and row["available"] == 63


@pytest.mark.django_db
def test_only_admin_toggles_reservations(sdr_api, api_client):
    assert sdr_api.patch("/api/v1/crm/settings/", {"inventory_reservations_enabled": False},
                         format="json").status_code == 403
    resp = api_client.patch("/api/v1/crm/settings/", {"inventory_reservations_enabled": False}, format="json")
    assert resp.status_code == 200 and resp.data["inventory_reservations_enabled"] is False


# --- Busca ----------------------------------------------------------------------------------

@pytest.mark.django_db
def test_search_by_name_ignores_accents_and_case(sdr_api, stock):
    rows = sdr_api.get(f"{URL}/items/", {"q": "TORRE 5"}).data
    assert rows and all("torre" in r["name"].lower() for r in rows)
    assert "q30_torre_5m" in [r["code"] for r in rows]
    InventoryItem(code="ilum_par", line="Iluminação", name="Refletor PAR LED", qty_total=4).save()
    assert [r["code"] for r in sdr_api.get(f"{URL}/items/", {"q": "refletor"}).data] == ["ilum_par"]
    assert sdr_api.get(f"{URL}/items/", {"q": "nada-parecido"}).data == []


@pytest.mark.django_db
def test_count_correction_is_logged(porta_api, stock):
    item = _item()
    assert porta_api.patch(f"{URL}/items/{item.id}/", {"qty_total": 100}, format="json").status_code == 200
    obs = _item().observations
    assert len(obs) == 1 and obs[0].kind == "ajuste" and "113 → 100" in obs[0].text
    porta_api.patch(f"{URL}/items/{item.id}/", {"description": "Torre treliçada"}, format="json")
    assert len(_item().observations) == 1  # editar outros campos não registra ajuste
