from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class PropertyRecord(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    property_manager_id: Mapped[str] = mapped_column(String(100), nullable=False)
    emergency_contact_id: Mapped[str] = mapped_column(String(100), nullable=False)


class CustomerRecord(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id"), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    property_manager_id: Mapped[str] = mapped_column(String(100), nullable=False)


class TicketRecord(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
