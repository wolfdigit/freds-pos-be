import uuid
from contextlib import contextmanager

import pytest

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from src.db.session import SessionFactory, engine
from src.models.location import StockLocation
from src.models.product import ProductStock
from src.models.system import StoreBranch
from src.services.checkout_service import STORE_LOCATION
from src.services.inventory_service import DEFAULT_STORE_LOCATION_ID
from src.services.location_integrity import (
    is_named_store_location_fk,
    is_store_location_fk_violation,
    is_unnamed_sqlite_fk,
    location_delete_blocked_by_store_fk,
)
from tests.test_auth import (
    ADMIN_EMAIL,
    STAFF_EMAIL,
    _add_account,
    _add_store,
    _auth,
    _login,
    _select,
)


def _qty(product_id: str, location_id: str) -> int:
    db = SessionFactory()
    try:
        row = db.scalar(
            select(ProductStock).where(
                ProductStock.product_id == product_id,
                ProductStock.location == location_id,
            )
        )
        return 0 if row is None else row.quantity
    finally:
        db.close()


def _set_qty(product_id: str, location_id: str, quantity: int) -> None:
    db = SessionFactory()
    try:
        row = db.scalar(
            select(ProductStock).where(
                ProductStock.product_id == product_id,
                ProductStock.location == location_id,
            )
        )
        if row is None:
            db.add(
                ProductStock(
                    product_id=product_id,
                    location=location_id,
                    location_name=location_id,
                    quantity=quantity,
                )
            )
        else:
            row.quantity = quantity
        db.commit()
    finally:
        db.close()


def _add_location(name: str) -> str:
    location_id = f"loc-{uuid.uuid4().hex}"
    db = SessionFactory()
    try:
        db.add(
            StockLocation(
                id=location_id,
                name=name,
                icon="📍",
                is_default=False,
                display_order=9,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    return location_id


def _sale(client, token: str, product_id: str, amount: int = 100, key: str | None = None):
    headers = _auth(token)
    if key:
        headers["X-Idempotency-Key"] = key
    return client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{"productId": product_id, "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": amount}],
        },
        headers=headers,
    )


def test_shared_default_two_stores_and_idempotent_replay(client, google_jwks):
    assert DEFAULT_STORE_LOCATION_ID == STORE_LOCATION == "e1a10001-0000-4000-8000-000000000001"
    _add_account(ADMIN_EMAIL)
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    created = client.post(
        "/api/v1/system/stores",
        json={"name": "乙店"},
        headers=_auth(login["token"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["stockLocationId"] == DEFAULT_STORE_LOCATION_ID
    assert created.json()["stockLocationName"] == "門市現貨"
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-MAP", "barcode": "444", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)

    first = _sale(client, login["token"], product_id, key="map-replay")
    assert first.status_code == 201, first.text
    assert first.json()["order"]["branchName"] == "甲店"
    assert first.json()["order"]["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    replay = _sale(client, login["token"], product_id, key="map-replay")
    assert replay.status_code == 201, replay.text
    assert replay.json()["order"]["id"] == first.json()["order"]["id"]
    assert replay.json()["order"]["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    _select(client, login["token"], "乙店")
    blocked = _sale(client, login["token"], product_id)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "INSUFFICIENT_STORE_STOCK"
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0


def test_separate_locations_mapping_update_and_return_to_current_store(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_account(STAFF_EMAIL, "staff", "店員")
    warehouse = _add_location("後方倉二")
    _add_store("甲店")
    _add_store("乙店", warehouse)
    admin = _login(client, google_jwks, ADMIN_EMAIL)
    staff = _login(client, google_jwks, STAFF_EMAIL)
    _select(client, admin["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-ISO", "barcode": "555", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(admin["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)
    _set_qty(product_id, warehouse, 3)

    sale = _sale(client, admin["token"], product_id)
    assert sale.status_code == 201, sale.text
    order = sale.json()["order"]
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0
    assert _qty(product_id, warehouse) == 3

    forbidden = client.put(
        "/api/v1/system/stores/乙店/stock-location",
        json={"stockLocationId": DEFAULT_STORE_LOCATION_ID},
        headers=_auth(staff["token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"
    switched = _select(client, staff["token"], "乙店")
    assert switched["storeName"] == "乙店"

    missing = client.put(
        "/api/v1/system/stores/甲店/stock-location",
        json={"stockLocationId": "does-not-exist"},
        headers=_auth(admin["token"]),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "LOCATION_NOT_FOUND"

    remapped = client.put(
        "/api/v1/system/stores/甲店/stock-location",
        json={"stockLocationId": warehouse},
        headers=_auth(admin["token"]),
    )
    assert remapped.status_code == 200, remapped.text
    assert remapped.json()["stockLocationId"] == warehouse
    original = client.get(f"/api/v1/checkout/orders/{order['id']}", headers=_auth(admin["token"]))
    assert original.json()["branchName"] == "甲店"
    assert original.json()["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0
    assert _qty(product_id, warehouse) == 3

    _select(client, admin["token"], "乙店")
    returned = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
                "restock": True,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=_auth(admin["token"]),
    )
    assert returned.status_code == 201, returned.text
    assert returned.json()["order"]["branchName"] == "乙店"
    assert returned.json()["order"]["totalAmount"] == -100
    assert _qty(product_id, warehouse) == 4
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    blocked_delete = client.request(
        "DELETE",
        f"/api/v1/inventory/locations/{warehouse}",
        json={"transferToLocation": DEFAULT_STORE_LOCATION_ID, "reason": "停用"},
        headers=_auth(admin["token"]),
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["code"] == "STOCK_LOCATION_IN_USE"
    assert _qty(product_id, warehouse) == 4


def test_restock_false_does_not_change_current_location(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    other = _add_location("退貨倉")
    _add_store("甲店")
    _add_store("乙店", other)
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-NO", "barcode": "666", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)
    sale = _sale(client, login["token"], product_id)
    order = sale.json()["order"]
    _select(client, login["token"], "乙店")
    returned = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
                "restock": False,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=_auth(login["token"]),
    )
    assert returned.status_code == 201, returned.text
    assert _qty(product_id, other) == 0
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0


def test_store_without_location_requires_explicit_id_when_shared_row_is_gone(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    other = _add_location("只剩這倉")
    _add_store("甲店", other)
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    db = SessionFactory()
    try:
        shared = db.get(StockLocation, DEFAULT_STORE_LOCATION_ID)
        if shared is not None:
            db.delete(shared)
            db.commit()
    finally:
        db.close()
    created = client.post("/api/v1/system/stores", json={"name": "丙店"}, headers=_auth(login["token"]))
    assert created.status_code == 409
    assert created.json()["code"] == "STOCK_LOCATION_REQUIRED"
    explicit = client.post(
        "/api/v1/system/stores",
        json={"name": "丙店", "stockLocationId": other},
        headers=_auth(login["token"]),
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["stockLocationId"] == other


class _PgError(Exception):
    def __init__(self, sqlstate: str, constraint_name: str) -> None:
        super().__init__(f"{sqlstate} {constraint_name}")
        self.pgcode = sqlstate
        self.diag = type("Diag", (), {"constraint_name": constraint_name})()


def test_only_the_store_location_foreign_key_is_recognized():
    unique = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: store_branch.name"))
    product_fk = IntegrityError("DELETE", {}, _PgError("23503", "product_stock_product_id_fkey"))
    store_fk = IntegrityError("DELETE", {}, _PgError("23503", "fk_store_branch_stock_location"))
    sqlite_fk = IntegrityError("DELETE", {}, Exception("FOREIGN KEY constraint failed"))

    assert is_store_location_fk_violation(unique) is False
    assert is_named_store_location_fk(product_fk) is False
    assert is_named_store_location_fk(store_fk) is True
    assert is_unnamed_sqlite_fk(sqlite_fk) is True
    assert is_named_store_location_fk(sqlite_fk) is False


def test_unnamed_sqlite_fk_blocks_delete_only_when_a_store_is_mapped(client):
    """SQLite does not name the constraint. A product foreign key must stay a product foreign key."""
    _add_store("甲店")
    spare = _add_location("未對應倉")
    sqlite_fk = IntegrityError("DELETE", {}, Exception("FOREIGN KEY constraint failed"))
    db = SessionFactory()
    try:
        assert location_delete_blocked_by_store_fk(db, sqlite_fk, spare) is False
        assert location_delete_blocked_by_store_fk(db, sqlite_fk, DEFAULT_STORE_LOCATION_ID) is True
        unique = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: store_branch.name"))
        assert location_delete_blocked_by_store_fk(db, unique, DEFAULT_STORE_LOCATION_ID) is False
    finally:
        db.close()


def test_unmapped_location_delete_still_moves_stock(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    spare = _add_location("可刪倉")
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-MOVE", "barcode": "777", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, spare, 4)
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)
    deleted = client.request(
        "DELETE",
        f"/api/v1/inventory/locations/{spare}",
        json={"transferToLocation": DEFAULT_STORE_LOCATION_ID, "reason": "整併"},
        headers=_auth(login["token"]),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["totalQuantityTransferred"] == 4
    assert _qty(product_id, spare) == 0
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 5
    db = SessionFactory()
    try:
        assert db.get(StockLocation, spare) is None
    finally:
        db.close()


@contextmanager
def _sqlite_foreign_keys():
    """The suite leaves SQLite foreign keys off. Postgres enforces them without this pragma."""

    def _on_connect(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=2000")
        cursor.close()

    event.listen(engine, "connect", _on_connect)
    engine.dispose()
    try:
        yield
    finally:
        event.remove(engine, "connect", _on_connect)
        engine.dispose()


def test_remap_during_location_delete_returns_409_and_keeps_stock(client, google_jwks):
    """A mapping committed after the in-use check still aborts the delete.

    SQLite drops FOR UPDATE, so this window exists here. The test turns foreign
    keys on and commits the remap from the delete transaction's before_commit
    hook. Postgres row locks make that window unreachable for a remap that locks
    the location first; this suite does not run Postgres. The injected commit is
    what a second connection can do on SQLite, and the foreign-key error is the
    same one Postgres raises if a mapping lands without that lock.
    """
    _add_account(ADMIN_EMAIL)
    spare = _add_location("競態倉")
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-RACE", "barcode": "888", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, spare, 0)
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 6)
    planted = {"done": False}

    def _plant(session) -> None:
        if planted["done"]:
            return
        doomed = [obj.id for obj in session.deleted if isinstance(obj, StockLocation) and obj.id == spare]
        if not doomed:
            return
        planted["done"] = True
        other = SessionFactory()
        try:
            store = other.get(StoreBranch, "甲店")
            assert store is not None
            store.stock_location_id = spare
            other.commit()
        finally:
            other.close()

    event.listen(OrmSession, "before_commit", _plant)
    try:
        with _sqlite_foreign_keys():
            blocked = client.request(
                "DELETE",
                f"/api/v1/inventory/locations/{spare}",
                json={"transferToLocation": DEFAULT_STORE_LOCATION_ID, "reason": "競態"},
                headers=_auth(login["token"]),
            )
    finally:
        event.remove(OrmSession, "before_commit", _plant)

    assert planted["done"] is True
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "STOCK_LOCATION_IN_USE"
    assert _qty(product_id, spare) == 0
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 6
    db = SessionFactory()
    try:
        assert db.get(StockLocation, spare) is not None
        store = db.get(StoreBranch, "甲店")
        assert store is not None
        assert store.stock_location_id == spare
    finally:
        db.close()


def test_location_removed_during_store_create_is_not_found(client, google_jwks):
    """SQLite allows the location delete to commit before the store insert flushes."""
    _add_account(ADMIN_EMAIL)
    spare = _add_location("臨時倉")
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    removed = {"done": False}

    def _remove(session) -> None:
        if removed["done"]:
            return
        creating = [obj for obj in session.new if isinstance(obj, StoreBranch) and obj.name == "丙店"]
        if not creating:
            return
        removed["done"] = True
        other = SessionFactory()
        try:
            location = other.get(StockLocation, spare)
            assert location is not None
            other.delete(location)
            other.commit()
        finally:
            other.close()

    event.listen(OrmSession, "before_commit", _remove)
    try:
        with _sqlite_foreign_keys():
            created = client.post(
                "/api/v1/system/stores",
                json={"name": "丙店", "stockLocationId": spare},
                headers=_auth(login["token"]),
            )
    finally:
        event.remove(OrmSession, "before_commit", _remove)

    assert removed["done"] is True
    assert created.status_code == 404, created.text
    assert created.json()["code"] == "LOCATION_NOT_FOUND"
    db = SessionFactory()
    try:
        assert db.get(StoreBranch, "丙店") is None
        assert db.get(StockLocation, spare) is None
        store = db.get(StoreBranch, "甲店")
        assert store is not None
        assert store.stock_location_id == DEFAULT_STORE_LOCATION_ID
    finally:
        db.close()


def test_unrelated_integrity_error_on_delete_is_not_in_use(client, google_jwks, monkeypatch):
    _add_account(ADMIN_EMAIL)
    spare = _add_location("別的錯誤倉")
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-UNIQ", "barcode": "999", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, spare, 3)
    real_commit = OrmSession.commit

    def _commit(self) -> None:
        if any(isinstance(obj, StockLocation) for obj in self.deleted):
            raise IntegrityError("DELETE", {}, Exception("UNIQUE constraint failed: product_stock.product_id"))
        real_commit(self)

    monkeypatch.setattr(OrmSession, "commit", _commit)
    with pytest.raises(IntegrityError):
        client.request(
            "DELETE",
            f"/api/v1/inventory/locations/{spare}",
            json={"transferToLocation": DEFAULT_STORE_LOCATION_ID, "reason": "不該吞掉"},
            headers=_auth(login["token"]),
        )
    assert _qty(product_id, spare) == 3
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0
    db = SessionFactory()
    try:
        assert db.get(StockLocation, spare) is not None
    finally:
        db.close()
