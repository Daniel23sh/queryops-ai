from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import mapped models so Alembic can discover them through Base.metadata.
from app import models  # noqa: E402,F401
from app.domains import it_operations  # noqa: E402,F401
