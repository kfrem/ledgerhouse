import pytest


@pytest.fixture(autouse=True, scope="session")
def enforce_postgresql_backend():
    """PostgreSQL is mandatory: the balance, period-lock, VAT-lock and audit
    triggers plus tenant RLS are database-layer features. Running the suite on
    any other backend would silently skip the safeguards under test."""
    from django.conf import settings

    engine = settings.DATABASES["default"]["ENGINE"]
    if "postgresql" not in engine:
        pytest.exit(
            f"LedgerHouse tests require PostgreSQL, but the configured backend is "
            f"'{engine}'. Start the stack with 'docker compose up -d' and run "
            f"'docker compose run --rm web pytest'.",
            returncode=1,
        )
    yield
