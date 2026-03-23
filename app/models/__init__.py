from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic can discover them
from app.models.config import (  # noqa: F401, E402
    ProductFamily,
    ProductService,
    ServiceConfig,
    ServiceConfigHistory,
)
