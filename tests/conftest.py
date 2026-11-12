import os
import tempfile

# Default is a temporary SQLite file so CI can run without a database server.
# Inventory foreign keys are enforced by PostgreSQL; set TEST_DATABASE_URI to a
# throwaway Postgres database to run this same suite there. See README.
_db_file = None
_test_database_uri = os.environ.get("TEST_DATABASE_URI", "").strip()
if _test_database_uri:
    os.environ["SQLALCHEMY_DATABASE_URI"] = _test_database_uri
else:
    _db_file = tempfile.NamedTemporaryFile(prefix="freds-auth-", suffix=".db", delete=False)
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _db_file.name
os.environ["DEBUG"] = "false"
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["AUTH_BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["AUTH_BOOTSTRAP_ADMIN_NAME"] = ""
os.environ["ENVIRONMENT"] = "test"

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import inspect

from src.db.base import Base
from src.db.session import SessionFactory, engine
from src.main import app

Base.metadata.create_all(bind=engine)


def _reset_database() -> None:
    db = SessionFactory()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    _reset_database()
    with TestClient(app) as test_client:
        yield test_client
    _reset_database()


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def google_jwks(monkeypatch, signing_key):
    public_jwk = RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    public_jwk["kid"] = "test-key"
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"
    monkeypatch.setattr(
        "src.services.google_identity.load_jwks",
        lambda force=False: {"test-key": public_jwk},
    )
    return signing_key


@pytest.fixture
def private_pem(signing_key):
    return signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def sqlite_path() -> str:
    if _db_file is None:
        raise RuntimeError("tests are using TEST_DATABASE_URI, not the default SQLite file")
    return _db_file.name


def pragma_columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}
