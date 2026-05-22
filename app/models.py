from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ItemStatus(str, Enum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    DISCARDED = "discarded"
    LOST = "lost"


class StorageType(str, Enum):
    PANTRY = "pantry"
    FRIDGE = "fridge"
    FREEZER = "freezer"
    CABINET = "cabinet"
    DRAWER = "drawer"
    SHELF = "shelf"
    BOX = "box"
    GARAGE = "garage"
    BASEMENT = "basement"
    OTHER = "other"


class Location(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class InventoryEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    MOVED = "moved"
    QUANTITY_CHANGED = "quantity_changed"
    OPENED = "opened"
    FROZEN = "frozen"
    CONSUMED = "consumed"
    DISCARDED = "discarded"
    LABEL_PRINTED = "label_printed"


class Item(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    # Used for QR-code lookup.
    qr_token: str = Field(
        default_factory=lambda: uuid4().hex,
        index=True,
        unique=True,
        nullable=False,
    )

    name: str = Field(index=True)

    category: str = Field(default="food", index=True)
    status: ItemStatus = Field(default=ItemStatus.ACTIVE, index=True)

    quantity: int = Field(default=0)
    unit: str = Field(default="pcs")

    purchase_date: Optional[date] = Field(default=None, index=True)
    expiry_date: Optional[date] = Field(default=None, index=True)

    opened_date: Optional[date] = None
    frozen_date: Optional[date] = None

    storage_type: StorageType = Field(default=StorageType.OTHER, index=True)

    storage_location: str = Field(default="unknown", index=True)
    storage_area: Optional[str] = Field(default=None, index=True)
    container: Optional[str] = Field(default=None, index=True)

    notes: Optional[str] = None

    brand: Optional[str] = None
    serial_number: Optional[str] = Field(default=None, index=True)
    warranty_expiry: Optional[date] = None

    barcode: Optional[str] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ItemBatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: UUID = Field(
        default_factory=uuid4,
        index=True,
        unique=True,
        nullable=False,
    )

    item_id: UUID = Field(index=True, foreign_key="item.id")

    quantity: int = Field(default=1)
    purchase_date: Optional[date] = Field(default=None, index=True)
    expiry_date: Optional[date] = Field(default=None, index=True)
    opened_date: Optional[date] = Field(default=None, index=True)
    frozen_date: Optional[date] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class InventoryEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    item_id: UUID = Field(index=True, foreign_key="item.id")

    event_type: InventoryEventType = Field(index=True)

    old_value: Optional[str] = None
    new_value: Optional[str] = None

    note: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
