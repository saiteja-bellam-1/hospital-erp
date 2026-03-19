from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

Base = declarative_base()

# Lazy engine — initialized on first use or after setup changes the DB path
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        from app.utils.paths import get_db_path
        db_path = get_db_path()
        url = f"sqlite:///{db_path}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def _get_session_local():
    _get_engine()
    return _SessionLocal


def reinitialize_engine():
    """Call after setup wizard changes the DB path to point engine at the new location."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None


# Public API — backward compatible
@property
def engine_prop():
    return _get_engine()


# Module-level 'engine' for backward compat (used by imports like `from config.database import engine`)
class _EngineProxy:
    """Proxy that lazily resolves to the real engine."""
    def __getattr__(self, name):
        return getattr(_get_engine(), name)
    def __repr__(self):
        return repr(_get_engine())


engine = _EngineProxy()


class _SessionLocalProxy:
    """Proxy that lazily resolves to the real SessionLocal."""
    def __call__(self, *args, **kwargs):
        return _get_session_local()(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(_get_session_local(), name)


SessionLocal = _SessionLocalProxy()


def get_db():
    Session = _get_session_local()
    db = Session()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    real_engine = _get_engine()
    Base.metadata.create_all(bind=real_engine)
