from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base


class PropertyRecord(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    property_manager_id: Mapped[str] = mapped_column(String(100), nullable=False)
    emergency_contact_id: Mapped[str] = mapped_column(String(100), nullable=False)


class PropertyManagerRecord(Base):
    __tablename__ = "property_managers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EmergencyContactRecord(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)


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


class CallOutcomeRecord(Base):
    __tablename__ = "call_outcomes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    intent: Mapped[str] = mapped_column(String(100), nullable=False)
    ticket_id: Mapped[str | None] = mapped_column(
        ForeignKey("tickets.id"), nullable=True
    )
    transfer_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    transfer_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
