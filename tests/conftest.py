import os
import tempfile

_db_file = tempfile.NamedTemporaryFile(prefix="freds-auth-", suffix=".db", delete=False)
os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _db_file.name
os.environ["DEBUG"] = "false"
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["AUTH_BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["AUTH_BOOTSTRAP_ADMIN_NAME"] = ""
os.environ["ENVIRONMENT"] = "test"
os.environ["VERCEL_ENV"] = ""
os.environ["SKIP_LOGIN"] = "false"
os.environ["SKIP_LOGIN_STORE"] = ""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import text

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
    return _db_file.name


def pragma_columns(table: str) -> set[str]:
    db = SessionFactory()
    try:
        rows = db.execute(text(f"PRAGMA table_info({table})")).all()
    finally:
        db.close()
    return {row[1] for row in rows}
