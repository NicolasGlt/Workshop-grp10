import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool

pool = ConnectionPool(
    conninfo="",
    kwargs={
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    },
    min_size=1,
    max_size=10,
    open=False,
)

def open_pool():
    pool.open(wait=True)

def close_pool():
    pool.close()

@contextmanager
def get_connection():
    with pool.connection() as connection:
        yield connection
