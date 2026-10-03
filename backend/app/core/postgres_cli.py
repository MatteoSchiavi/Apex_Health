"""libpq connection settings without passwords in process arguments."""

import os

from sqlalchemy.engine import make_url


def postgres_environment(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("A PostgreSQL connection URL is required")
    env = os.environ.copy()
    # Do not inherit a different target or password from the operator's shell.
    for key in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE"):
        env.pop(key, None)
    for key, value in {
        "PGHOST": url.host, "PGPORT": url.port, "PGUSER": url.username,
        "PGPASSWORD": url.password, "PGDATABASE": url.database,
    }.items():
        if value is not None:
            env[key] = str(value)
    for key in ("sslmode", "sslcert", "sslkey", "sslrootcert", "connect_timeout"):
        if key in url.query:
            env[f"PG{key.upper()}"] = str(url.query[key])
    env.setdefault("PGCONNECT_TIMEOUT", "10")
    return env
