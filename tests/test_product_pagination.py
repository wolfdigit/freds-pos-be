"""GET /products 分頁：不帶分頁參數時維持原本陣列格式；帶 page/pageSize 時回 {items, page, pageSize, total}。"""

from src.services.inventory_service import RETURNED_LOCATION_ID
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _set_location_qty


def _setup(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    return _auth(login["token"]), shelf


def _create(client, headers, sku: str, *, barcode: str | None = None, brand: str = "Brand", name: str = "車") -> str:
    response = client.post(
        "/api/v1/products",
        json={"sku": sku, "barcode": barcode or sku, "brand": brand, "name": name, "listPrice": 100},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _get(client, headers, **params):
    response = client.get("/api/v1/products", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_without_paging_params_the_full_array_is_unchanged(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    for sku in ["SKU-C", "SKU-A", "SKU-B"]:
        _create(client, headers, sku)
    body = _get(client, headers)
    assert isinstance(body, list)
    assert [row["sku"] for row in body] == ["SKU-A", "SKU-B", "SKU-C"]
    assert {"totalInventory", "loginStoreQuantity", "inventories"} <= set(body[0])


def test_pages_cover_every_match_once_in_sku_order(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    for sku in ["SKU-E", "SKU-C", "SKU-A", "SKU-D", "SKU-B"]:
        _create(client, headers, sku)

    first = _get(client, headers, page=1, pageSize=2)
    assert first["page"] == 1
    assert first["pageSize"] == 2
    assert first["total"] == 5
    assert [row["sku"] for row in first["items"]] == ["SKU-A", "SKU-B"]

    third = _get(client, headers, page=3, pageSize=2)
    assert [row["sku"] for row in third["items"]] == ["SKU-E"]
    assert third["total"] == 5

    past_end = _get(client, headers, page=4, pageSize=2)
    assert past_end["items"] == []
    assert past_end["total"] == 5

    only_size = _get(client, headers, pageSize=3)
    assert only_size["page"] == 1
    assert [row["sku"] for row in only_size["items"]] == ["SKU-A", "SKU-B", "SKU-C"]

    only_page = _get(client, headers, page=1)
    assert only_page["pageSize"] == 50
    assert len(only_page["items"]) == 5


def test_filters_apply_before_paging_and_total_counts_matches(client, google_jwks):
    headers, shelf = _setup(client, google_jwks)
    locations = client.get("/api/v1/inventory/locations", headers=headers).json()
    warehouse = next(row["id"] for row in locations if row["name"] == "後方倉庫")
    on_shelf = _create(client, headers, "TOY-1", brand="AutoArt", name="Ferrari")
    in_warehouse = _create(client, headers, "TOY-2", brand="AutoArt", name="Ferrari F40")
    negative = _create(client, headers, "TOY-3", brand="AutoArt", name="Ferrari 250")
    _create(client, headers, "TOY-4", brand="Kyosho", name="Ferrari")
    deleted = _create(client, headers, "TOY-5", brand="AutoArt", name="Ferrari Enzo")
    _set_location_qty(on_shelf, shelf, 2)
    _set_location_qty(in_warehouse, warehouse, 1)
    _set_location_qty(in_warehouse, shelf, -1)
    _set_location_qty(in_warehouse, RETURNED_LOCATION_ID, 3)
    _set_location_qty(negative, shelf, -4)
    _set_location_qty(deleted, shelf, 9)
    assert client.put(f"/api/v1/products/{deleted}", json={"deleted": True}, headers=headers).status_code == 200

    by_brand = _get(client, headers, keyword="ferrari", brand="AutoArt", page=1, pageSize=2)
    assert by_brand["total"] == 3
    assert [row["sku"] for row in by_brand["items"]] == ["TOY-1", "TOY-2"]

    stocked = _get(client, headers, inInventoryOnly=True, page=1, pageSize=10)
    assert [row["id"] for row in stocked["items"]] == [on_shelf, in_warehouse]
    assert stocked["total"] == 2
    # totalInventory 是所有庫存點的有號合計；loginStoreQuantity 只看目前門市的正常庫存點。
    row = stocked["items"][1]
    assert row["totalInventory"] == 3
    assert row["loginStoreQuantity"] == -1
    assert row["loginStoreReturnedQuantity"] == 3

    # 同樣的篩選，分頁和不分頁拿到同一組商品。
    unpaged = _get(client, headers, inInventoryOnly=True)
    assert [r["id"] for r in unpaged] == [r["id"] for r in stocked["items"]]


def test_barcode_filter_is_an_exact_match(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    first = _create(client, headers, "BAR-1", barcode="4710001")
    second = _create(client, headers, "BAR-2", barcode="4710001")
    _create(client, headers, "BAR-3", barcode="47100012")
    assert [row["id"] for row in _get(client, headers, barcode="4710001")] == [first, second]
    paged = _get(client, headers, barcode="4710001", page=1, pageSize=1)
    assert paged["total"] == 2
    assert [row["id"] for row in paged["items"]] == [first]


def test_paging_params_are_validated(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    for params in ({"page": 0}, {"pageSize": 0}, {"pageSize": 201}, {"page": "x"}):
        response = client.get("/api/v1/products", params=params, headers=headers)
        assert response.status_code == 422, (params, response.text)
