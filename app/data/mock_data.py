from app.customers.schemas import Customer
from app.properties.schemas import Property
from app.tickets.schemas import Ticket, TicketPriority, TicketStatus

PROPERTIES: list[Property] = [
    Property(
        id="property-neubaugasse-17",
        address="Neubaugasse 17, 1070 Wien",
        property_manager_id="manager-1",
        emergency_contact_id="emergency-1",
    ),
    Property(
        id="property-landstrasser-42",
        address="Landstraßer Hauptstraße 42, 1030 Wien",
        property_manager_id="manager-2",
        emergency_contact_id="emergency-2",
    ),
]

CUSTOMERS: list[Customer] = [
    Customer(
        id="customer-anna-mueller",
        first_name="Anna",
        last_name="Müller",
        phone="+436601234567",
        property_id="property-neubaugasse-17",
        unit="4B",
        property_manager_id="manager-1",
    ),
    Customer(
        id="customer-lukas-huber",
        first_name="Lukas",
        last_name="Huber",
        phone="+436609876543",
        property_id="property-landstrasser-42",
        unit="12A",
        property_manager_id="manager-2",
    ),
    Customer(
        id="customer-maria-schmidt",
        first_name="Maria",
        last_name="Schmidt",
        phone="+436601111111",
        property_id="property-neubaugasse-17",
        unit="2A",
        property_manager_id="manager-1",
    ),
    Customer(
        id="customer-paul-schmidt",
        first_name="Paul",
        last_name="Schmidt",
        phone="+436601111111",
        property_id="property-neubaugasse-17",
        unit="2A",
        property_manager_id="manager-1",
    ),
]

TICKETS: list[Ticket] = [
    Ticket(
        id="ticket-1",
        customer_id="customer-lukas-huber",
        property_id="property-landstrasser-42",
        category="plumbing",
        description="Kitchen sink is leaking.",
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.OPEN,
    ),
    Ticket(
        id="ticket-2",
        customer_id="customer-lukas-huber",
        property_id="property-landstrasser-42",
        category="heating",
        description="Radiator valve was replaced.",
        priority=TicketPriority.LOW,
        status=TicketStatus.CLOSED,
    ),
]
