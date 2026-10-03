import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 3}
        )
        self._sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessionmaker() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    def ping(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("select 1"))
            return True
        except SQLAlchemyError as e:
            log.debug("database ping failed: %s", e)
            return False

    def dispose(self) -> None:
        self.engine.dispose()
