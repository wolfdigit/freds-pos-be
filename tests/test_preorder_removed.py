"""預購功能已移除：路由不存在，商品回應不再有 preOrderPendingCount。"""

from tests.test_product_pagination import _create, _get, _setup


def test_preorder_routes_are_gone(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    customer = client.post("/api/v1/customers", json={"name": "QA-預購移除", "phone": "0900000001"}, headers=headers)
    assert customer.status_code == 201, customer.text
    customer_id = customer.json()["id"]

    assert client.get("/api/v1/preorders", params={"query": "車"}, headers=headers).status_code == 404
    assert client.post("/api/v1/preorders", json={}, headers=headers).status_code == 404
    assert client.get(f"/api/v1/customers/{customer_id}/preorders", headers=headers).status_code == 404


def test_product_responses_have_no_preorder_pending_count(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    product_id = _create(client, headers, "SKU-NOPO")

    listed = _get(client, headers)[0]
    paged = _get(client, headers, page=1, pageSize=10)["items"][0]
    single = client.get(f"/api/v1/products/{product_id}", headers=headers).json()
    for body in (listed, paged, single):
        assert "preOrderPendingCount" not in body
        assert body["totalInventory"] == 0


def test_customer_without_open_sales_can_be_deleted(client, google_jwks):
    headers, _shelf = _setup(client, google_jwks)
    customer = client.post("/api/v1/customers", json={"name": "QA-可刪除會員", "phone": "0900000002"}, headers=headers)
    assert customer.status_code == 201, customer.text
    response = client.delete(f"/api/v1/customers/{customer.json()['id']}", headers=headers)
    assert response.status_code == 204, response.text
