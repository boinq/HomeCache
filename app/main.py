import os
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional
from uuid import UUID, uuid4

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine, get_session
from app.models import (
    Category,
    InventoryEvent,
    InventoryEventType,
    Item,
    ItemBatch,
    ItemStatus,
    Location,
    StorageType,
)


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DEFAULT_CATEGORIES = [
    "food",
    "cleaning",
    "medicine",
    "tools",
    "electronics",
    "clothing",
    "documents",
    "other",
]


app = FastAPI(title="HomeCache")

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/assets", StaticFiles(directory="app/assets"), name="assets")


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()
    ensure_item_batch_public_ids()
    seed_locations_from_items()
    seed_categories_from_items()
    seed_item_batches_from_items()


def get_item_or_404(session: Session, item_id: UUID) -> Item:
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def get_item_by_token_or_404(session: Session, qr_token: str) -> Item:
    statement = select(Item).where(Item.qr_token == qr_token)
    item = session.exec(statement).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def normalize_location_name(name: str) -> str:
    return " ".join(name.strip().split())


def normalize_category_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def list_locations(session: Session) -> list[Location]:
    statement = select(Location).order_by(Location.name)
    return session.exec(statement).all()


def list_categories(session: Session) -> list[Category]:
    statement = select(Category).order_by(Category.name)
    return session.exec(statement).all()


def get_location_or_404(session: Session, location_id: int) -> Location:
    location = session.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def get_category_or_404(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def ensure_location(session: Session, name: str) -> str:
    name = normalize_location_name(name) or "unknown"
    existing = session.exec(select(Location).where(Location.name == name)).first()

    if not existing:
        session.add(Location(name=name))

    return name


def ensure_category(session: Session, name: str) -> str:
    name = normalize_category_name(name) or "other"
    existing = session.exec(select(Category).where(Category.name == name)).first()

    if not existing:
        session.add(Category(name=name))

    return name


def item_form_context(
    session: Session,
    item: Optional[Item],
    form_action: str,
) -> dict:
    return {
        "item": item,
        "form_action": form_action,
        "categories": list_categories(session),
        "locations": list_locations(session),
    }


def list_item_batches(session: Session, item_id: UUID) -> list[ItemBatch]:
    statement = (
        select(ItemBatch)
        .where(ItemBatch.item_id == item_id)
        .order_by(ItemBatch.expiry_date, ItemBatch.purchase_date, ItemBatch.public_id)
    )
    return session.exec(statement).all()


def get_batch_or_404(session: Session, batch_public_id: UUID) -> ItemBatch:
    batch = session.exec(
        select(ItemBatch).where(ItemBatch.public_id == batch_public_id)
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


def get_primary_item_batch(session: Session, item: Item) -> Optional[ItemBatch]:
    return session.exec(
        select(ItemBatch)
        .where(ItemBatch.item_id == item.id)
        .order_by(ItemBatch.expiry_date, ItemBatch.purchase_date, ItemBatch.public_id)
    ).first()


def list_print_label_batches(session: Session) -> list[dict]:
    statement = (
        select(ItemBatch, Item)
        .join(Item, ItemBatch.item_id == Item.id)
        .where(Item.status == ItemStatus.ACTIVE)
        .order_by(
            Item.storage_location,
            Item.name,
            ItemBatch.expiry_date,
            ItemBatch.public_id,
        )
    )
    return [
        {"batch": batch, "item": item}
        for batch, item in session.exec(statement).all()
    ]


def list_print_label_item_groups(session: Session) -> list[dict]:
    items = session.exec(
        select(Item)
        .where(Item.status == ItemStatus.ACTIVE)
        .order_by(Item.storage_location, Item.name)
    ).all()

    return [
        {
            "item": item,
            "batches": list_item_batches(session, item.id),
        }
        for item in items
    ]


def sync_item_batch_summary(
    session: Session,
    item: Item,
    batches: Optional[list[ItemBatch]] = None,
) -> None:
    batches = batches if batches is not None else list_item_batches(session, item.id)
    item.quantity = sum(int(batch.quantity) for batch in batches)

    purchase_dates = [
        batch.purchase_date for batch in batches if batch.purchase_date is not None
    ]
    expiry_dates = [
        batch.expiry_date for batch in batches if batch.expiry_date is not None
    ]

    item.purchase_date = max(purchase_dates) if purchase_dates else None
    item.expiry_date = min(expiry_dates) if expiry_dates else None
    item.updated_at = datetime.utcnow()
    session.add(item)


def count_items_by_location(session: Session) -> dict[str, int]:
    item_counts: dict[str, int] = {}
    items = session.exec(select(Item)).all()

    for item in items:
        item_counts[item.storage_location] = item_counts.get(item.storage_location, 0) + 1

    return item_counts


def count_items_by_category(session: Session) -> dict[str, int]:
    item_counts: dict[str, int] = {}
    items = session.exec(select(Item)).all()

    for item in items:
        item_counts[item.category] = item_counts.get(item.category, 0) + 1

    return item_counts


def ensure_item_batch_public_ids() -> None:
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(itembatch)")).fetchall()
        column_names = {column[1] for column in columns}

        if "public_id" not in column_names:
            connection.execute(text("ALTER TABLE itembatch ADD COLUMN public_id VARCHAR"))

        for date_column in ["opened_date", "frozen_date"]:
            if date_column not in column_names:
                connection.execute(
                    text(f"ALTER TABLE itembatch ADD COLUMN {date_column} DATE")
                )

        rows = connection.execute(
            text("SELECT id FROM itembatch WHERE public_id IS NULL OR public_id = ''")
        ).fetchall()

        for row in rows:
            connection.execute(
                text("UPDATE itembatch SET public_id = :public_id WHERE id = :id"),
                {"public_id": uuid4().hex, "id": row[0]},
            )

        connection.execute(
            text(
                "UPDATE itembatch "
                "SET public_id = lower(replace(public_id, '-', '')) "
                "WHERE public_id LIKE '%-%'"
            )
        )

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_itembatch_public_id ON itembatch (public_id)"
            )
        )


def seed_locations_from_items() -> None:
    with Session(engine) as session:
        existing_locations = {
            location.name.lower()
            for location in session.exec(select(Location)).all()
        }
        item_locations = session.exec(select(Item.storage_location).distinct()).all()

        changed = False
        for item_location in item_locations:
            name = normalize_location_name(item_location or "")
            if not name or name.lower() in existing_locations:
                continue

            session.add(Location(name=name))
            existing_locations.add(name.lower())
            changed = True

        if "unknown" not in existing_locations:
            session.add(Location(name="unknown"))
            changed = True

        if changed:
            session.commit()


def seed_categories_from_items() -> None:
    with Session(engine) as session:
        existing_categories = {
            category.name.lower()
            for category in session.exec(select(Category)).all()
        }
        item_categories = session.exec(select(Item.category).distinct()).all()

        changed = False
        for category_name in [*DEFAULT_CATEGORIES, *item_categories]:
            name = normalize_category_name(category_name or "")
            if not name or name.lower() in existing_categories:
                continue

            session.add(Category(name=name))
            existing_categories.add(name.lower())
            changed = True

        if changed:
            session.commit()


def seed_item_batches_from_items() -> None:
    with Session(engine) as session:
        items = session.exec(select(Item)).all()
        changed = False

        for item in items:
            existing_batch = session.exec(
                select(ItemBatch).where(ItemBatch.item_id == item.id)
            ).first()

            if existing_batch:
                continue

            session.add(
                ItemBatch(
                    item_id=item.id,
                    quantity=int(item.quantity),
                    purchase_date=item.purchase_date,
                    expiry_date=item.expiry_date,
                    opened_date=item.opened_date,
                    frozen_date=item.frozen_date,
                )
            )
            changed = True

        if changed:
            session.commit()


def add_event(
    session: Session,
    item: Item,
    event_type: InventoryEventType,
    note: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> None:
    session.add(
        InventoryEvent(
            item_id=item.id,
            event_type=event_type,
            note=note,
            old_value=old_value,
            new_value=new_value,
        )
    )


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/items", status_code=303)


@app.get("/items", response_class=HTMLResponse)
def list_items(
    request: Request,
    session: Session = Depends(get_session),
    q: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: str = "asc",
):
    statement = select(Item).where(Item.status == ItemStatus.ACTIVE)

    if q:
        statement = statement.where(Item.name.contains(q))

    if location:
        statement = statement.where(Item.storage_location == location)

    if category:
        statement = statement.where(Item.category == category)

    sortable_fields = {
        "purchase_date": Item.purchase_date,
        "expiry_date": Item.expiry_date,
    }
    sort_column = sortable_fields.get(sort_by or "")
    sort_dir = "desc" if sort_dir == "desc" else "asc"

    if sort_column is not None:
        sort_expression = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
        statement = statement.order_by(sort_expression, Item.name)
    else:
        statement = statement.order_by(Item.expiry_date, Item.name)

    items = session.exec(statement).all()
    item_groups = [
        {
            "category": category_name,
            "category_items": [
                item
                for item in items
                if (item.category or "other").lower() == category_name.lower()
            ],
        }
        for category_name in sorted({item.category or "other" for item in items})
    ]

    return templates.TemplateResponse(
        request=request,
        name="item_list.html",
        context={
            "items": items,
            "item_groups": item_groups,
            "q": q or "",
            "location": location or "",
            "category": category or "",
            "sort_by": sort_by or "",
            "sort_dir": sort_dir,
        },
    )


@app.get("/items/new", response_class=HTMLResponse)
def new_item_form(
    request: Request,
    session: Session = Depends(get_session),
):
    return templates.TemplateResponse(
        request=request,
        name="item_form.html",
        context=item_form_context(session, item=None, form_action="/items"),
    )


@app.post("/items")
def create_item(
    session: Session = Depends(get_session),
    name: str = Form(...),
    save_action: str = Form("detail"),
    category: str = Form("food"),
    storage_type: StorageType = Form(StorageType.OTHER),
    quantity: int = Form(0),
    unit: str = Form("pcs"),
    storage_location: str = Form("unknown"),
    storage_area: Optional[str] = Form(None),
    container: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    barcode: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    warranty_expiry: Optional[date] = Form(None),
    notes: Optional[str] = Form(None),
):
    category = ensure_category(session, category)
    storage_location = ensure_location(session, storage_location)

    item = Item(
        name=name,
        category=category,
        storage_type=storage_type,
        quantity=quantity,
        unit=unit,
        storage_location=storage_location,
        storage_area=storage_area,
        container=container,
        brand=brand,
        barcode=barcode,
        serial_number=serial_number,
        warranty_expiry=warranty_expiry,
        notes=notes,
    )

    session.add(item)
    session.commit()
    session.refresh(item)

    add_event(session, item, InventoryEventType.CREATED)
    session.commit()

    if save_action == "new":
        return RedirectResponse(url="/items/new", status_code=303)

    return RedirectResponse(url=f"/items/{item.id}", status_code=303)


@app.get("/categories", response_class=HTMLResponse)
def categories_page(
    request: Request,
    session: Session = Depends(get_session),
):
    categories = list_categories(session)

    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={
            "categories": categories,
            "item_counts": count_items_by_category(session),
        },
    )


@app.post("/categories")
def create_category(
    session: Session = Depends(get_session),
    name: str = Form(...),
):
    name = normalize_category_name(name)
    if not name:
        return RedirectResponse(url="/categories", status_code=303)

    existing = session.exec(select(Category).where(Category.name == name)).first()
    if not existing:
        session.add(Category(name=name))
        session.commit()

    return RedirectResponse(url="/categories", status_code=303)


@app.post("/categories/{category_id}/edit")
def update_category(
    category_id: int,
    session: Session = Depends(get_session),
    name: str = Form(...),
):
    category = get_category_or_404(session, category_id)
    new_name = normalize_category_name(name)

    if not new_name:
        return RedirectResponse(url="/categories", status_code=303)

    duplicate = session.exec(select(Category).where(Category.name == new_name)).first()
    if duplicate and duplicate.id != category.id:
        return RedirectResponse(url="/categories", status_code=303)

    old_name = category.name
    category.name = new_name
    category.updated_at = datetime.utcnow()

    items = session.exec(select(Item).where(Item.category == old_name)).all()
    for item in items:
        item.category = new_name
        item.updated_at = datetime.utcnow()
        session.add(item)

    session.add(category)
    session.commit()

    return RedirectResponse(url="/categories", status_code=303)


@app.post("/categories/{category_id}/delete")
def delete_category(
    category_id: int,
    session: Session = Depends(get_session),
):
    category = get_category_or_404(session, category_id)
    in_use = session.exec(select(Item).where(Item.category == category.name)).first()

    if not in_use:
        session.delete(category)
        session.commit()

    return RedirectResponse(url="/categories", status_code=303)


@app.get("/locations", response_class=HTMLResponse)
def locations_page(
    request: Request,
    session: Session = Depends(get_session),
):
    locations = list_locations(session)

    return templates.TemplateResponse(
        request=request,
        name="locations.html",
        context={
            "locations": locations,
            "item_counts": count_items_by_location(session),
        },
    )


@app.post("/locations")
def create_location(
    session: Session = Depends(get_session),
    name: str = Form(...),
):
    name = normalize_location_name(name)
    if not name:
        return RedirectResponse(url="/locations", status_code=303)

    existing = session.exec(select(Location).where(Location.name == name)).first()
    if not existing:
        session.add(Location(name=name))
        session.commit()

    return RedirectResponse(url="/locations", status_code=303)


@app.post("/locations/{location_id}/edit")
def update_location(
    location_id: int,
    session: Session = Depends(get_session),
    name: str = Form(...),
):
    location = get_location_or_404(session, location_id)
    new_name = normalize_location_name(name)

    if not new_name:
        return RedirectResponse(url="/locations", status_code=303)

    duplicate = session.exec(select(Location).where(Location.name == new_name)).first()
    if duplicate and duplicate.id != location.id:
        return RedirectResponse(url="/locations", status_code=303)

    old_name = location.name
    location.name = new_name
    location.updated_at = datetime.utcnow()

    items = session.exec(select(Item).where(Item.storage_location == old_name)).all()
    for item in items:
        item.storage_location = new_name
        item.updated_at = datetime.utcnow()
        session.add(item)

    session.add(location)
    session.commit()

    return RedirectResponse(url="/locations", status_code=303)


@app.post("/locations/{location_id}/delete")
def delete_location(
    location_id: int,
    session: Session = Depends(get_session),
):
    location = get_location_or_404(session, location_id)
    in_use = session.exec(
        select(Item).where(Item.storage_location == location.name)
    ).first()

    if not in_use:
        session.delete(location)
        session.commit()

    return RedirectResponse(url="/locations", status_code=303)


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(
    item_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)
    batches = list_item_batches(session, item.id)

    return templates.TemplateResponse(
        request=request,
        name="item_detail.html",
        context={
            "item": item,
            "batches": batches,
        },
    )


@app.post("/items/{item_id}/batches")
def create_item_batch(
    item_id: UUID,
    session: Session = Depends(get_session),
    quantity: int = Form(1),
    purchase_date: Optional[date] = Form(None),
    expiry_date: Optional[date] = Form(None),
    opened_date: Optional[date] = Form(None),
    frozen_date: Optional[date] = Form(None),
):
    item = get_item_or_404(session, item_id)
    batch = ItemBatch(
        item_id=item.id,
        quantity=quantity,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        opened_date=opened_date,
        frozen_date=frozen_date,
    )

    session.add(batch)
    session.commit()

    sync_item_batch_summary(session, item)
    add_event(
        session,
        item,
        InventoryEventType.QUANTITY_CHANGED,
        note="Added item batch",
    )
    session.commit()

    return RedirectResponse(url=f"/items/{item.id}", status_code=303)


@app.post("/items/{item_id}/batches/{batch_public_id}/edit")
def update_item_batch(
    item_id: UUID,
    batch_public_id: UUID,
    session: Session = Depends(get_session),
    quantity: int = Form(1),
    purchase_date: Optional[date] = Form(None),
    expiry_date: Optional[date] = Form(None),
    opened_date: Optional[date] = Form(None),
    frozen_date: Optional[date] = Form(None),
):
    item = get_item_or_404(session, item_id)
    batch = get_batch_or_404(session, batch_public_id)

    if batch.item_id != item.id:
        raise HTTPException(status_code=404, detail="Batch not found")

    old_quantity = int(batch.quantity)
    batch.quantity = quantity
    batch.purchase_date = purchase_date
    batch.expiry_date = expiry_date
    batch.opened_date = opened_date
    batch.frozen_date = frozen_date
    batch.updated_at = datetime.utcnow()

    session.add(batch)
    sync_item_batch_summary(session, item)
    add_event(
        session,
        item,
        InventoryEventType.QUANTITY_CHANGED,
        note="Updated item batch",
        old_value=str(old_quantity),
        new_value=str(quantity),
    )
    session.commit()

    return RedirectResponse(
        url=f"/items/{item.id}#batch-{batch.public_id}",
        status_code=303,
    )


@app.post("/items/{item_id}/batches/{batch_public_id}/delete")
def delete_item_batch(
    item_id: UUID,
    batch_public_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)
    batch = get_batch_or_404(session, batch_public_id)

    if batch.item_id != item.id:
        raise HTTPException(status_code=404, detail="Batch not found")

    session.delete(batch)
    session.commit()

    sync_item_batch_summary(session, item)
    add_event(
        session,
        item,
        InventoryEventType.QUANTITY_CHANGED,
        note="Removed item batch",
    )
    session.commit()

    return RedirectResponse(url=f"/items/{item.id}", status_code=303)


@app.get("/i/{qr_token}", response_class=HTMLResponse)
def item_from_qr(
    qr_token: str,
    session: Session = Depends(get_session),
):
    item = get_item_by_token_or_404(session, qr_token)
    return RedirectResponse(url=f"/items/{item.id}", status_code=303)


@app.get("/b/{batch_public_id}", response_class=HTMLResponse)
def batch_from_qr(
    batch_public_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    batch = get_batch_or_404(session, batch_public_id)
    item = get_item_or_404(session, batch.item_id)

    return templates.TemplateResponse(
        request=request,
        name="batch_scan.html",
        context={
            "item": item,
            "batch": batch,
        },
    )


@app.post("/b/{batch_public_id}/consume")
def consume_batch_from_qr(
    batch_public_id: UUID,
    session: Session = Depends(get_session),
):
    batch = get_batch_or_404(session, batch_public_id)
    item = get_item_or_404(session, batch.item_id)
    old_quantity = int(batch.quantity)

    if old_quantity <= 1:
        session.delete(batch)
        redirect_url = f"/items/{item.id}"
        new_quantity = 0
    else:
        batch.quantity = old_quantity - 1
        batch.updated_at = datetime.utcnow()
        session.add(batch)
        redirect_url = f"/b/{batch.public_id}"
        new_quantity = int(batch.quantity)

    sync_item_batch_summary(session, item)
    add_event(
        session,
        item,
        InventoryEventType.QUANTITY_CHANGED,
        note="Consumed 1 from batch",
        old_value=str(old_quantity),
        new_value=str(new_quantity),
    )
    session.commit()

    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_form(
    item_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)

    return templates.TemplateResponse(
        request=request,
        name="item_form.html",
        context=item_form_context(
            session,
            item=item,
            form_action=f"/items/{item.id}/edit",
        ),
    )


@app.post("/items/{item_id}/edit")
def update_item(
    item_id: UUID,
    session: Session = Depends(get_session),
    name: str = Form(...),
    category: str = Form("food"),
    storage_type: StorageType = Form(StorageType.OTHER),
    quantity: int = Form(1),
    unit: str = Form("pcs"),
    storage_location: str = Form("unknown"),
    storage_area: Optional[str] = Form(None),
    container: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    barcode: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    warranty_expiry: Optional[date] = Form(None),
    notes: Optional[str] = Form(None),
):
    item = get_item_or_404(session, item_id)
    category = ensure_category(session, category)
    storage_location = ensure_location(session, storage_location)

    item.name = name
    item.category = category
    item.storage_type = storage_type
    item.quantity = quantity
    item.unit = unit
    item.storage_location = storage_location
    item.storage_area = storage_area
    item.container = container
    item.brand = brand
    item.barcode = barcode
    item.serial_number = serial_number
    item.warranty_expiry = warranty_expiry
    item.notes = notes
    item.updated_at = datetime.utcnow()

    batches = list_item_batches(session, item.id)
    if len(batches) == 1:
        batches[0].quantity = quantity
        batches[0].updated_at = datetime.utcnow()
        session.add(batches[0])
        sync_item_batch_summary(session, item, batches)
    elif len(batches) > 1:
        sync_item_batch_summary(session, item, batches)

    session.add(item)
    add_event(session, item, InventoryEventType.UPDATED)
    session.commit()

    return RedirectResponse(url=f"/items/{item.id}", status_code=303)


@app.post("/items/{item_id}/consume")
def mark_consumed(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)

    old_status = item.status
    item.status = ItemStatus.CONSUMED
    item.updated_at = datetime.utcnow()

    session.add(item)
    add_event(
        session,
        item,
        InventoryEventType.CONSUMED,
        old_value=str(old_status),
        new_value=str(ItemStatus.CONSUMED),
    )
    session.commit()

    return RedirectResponse(url="/items", status_code=303)


@app.post("/items/{item_id}/discard")
def mark_discarded(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)

    old_status = item.status
    item.status = ItemStatus.DISCARDED
    item.updated_at = datetime.utcnow()

    session.add(item)
    add_event(
        session,
        item,
        InventoryEventType.DISCARDED,
        old_value=str(old_status),
        new_value=str(ItemStatus.DISCARDED),
    )
    session.commit()

    return RedirectResponse(url="/items", status_code=303)


@app.post("/items/{item_id}/delete")
def delete_item(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)

    batches = session.exec(
        select(ItemBatch).where(ItemBatch.item_id == item.id)
    ).all()
    events = session.exec(
        select(InventoryEvent).where(InventoryEvent.item_id == item.id)
    ).all()

    for batch in batches:
        session.delete(batch)

    for event in events:
        session.delete(event)

    session.delete(item)
    session.commit()

    return RedirectResponse(url="/items", status_code=303)


@app.get("/items/{item_id}/qr")
def item_qr_code(
    item_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)
    batch = get_primary_item_batch(session, item)
    if not batch:
        raise HTTPException(status_code=404, detail="No batch QR available")

    qr_url = f"{BASE_URL}/b/{batch.public_id}"

    img = qrcode.make(qr_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")


@app.get("/items/{item_id}/batches/{batch_public_id}/qr")
def item_batch_qr_code(
    item_id: UUID,
    batch_public_id: UUID,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)
    batch = get_batch_or_404(session, batch_public_id)

    if batch.item_id != item.id:
        raise HTTPException(status_code=404, detail="Batch not found")

    img = qrcode.make(f"{BASE_URL}/b/{batch.public_id}")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")


@app.get("/items/{item_id}/label", response_class=HTMLResponse)
def item_label(
    item_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
):
    item = get_item_or_404(session, item_id)
    batch = get_primary_item_batch(session, item)

    if not batch:
        raise HTTPException(status_code=404, detail="No batch label available")

    add_event(session, item, InventoryEventType.LABEL_PRINTED)
    session.commit()

    return templates.TemplateResponse(
        request=request,
        name="item_label.html",
        context={
            "item": item,
            "batch": batch,
            "qr_url": f"{BASE_URL}/b/{batch.public_id}",
        },
    )


@app.get("/print-labels", response_class=HTMLResponse)
def print_labels(
    request: Request,
    session: Session = Depends(get_session),
    batch_id: Optional[list[UUID]] = Query(None),
    selected: bool = False,
):
    item_groups = list_print_label_item_groups(session)
    all_batches = [
        {"item": group["item"], "batch": batch}
        for group in item_groups
        for batch in group["batches"]
    ]
    selected_ids = set(batch_id or [])

    if selected:
        batches = [
            entry for entry in all_batches if entry["batch"].public_id in selected_ids
        ]
    else:
        batches = all_batches

    return templates.TemplateResponse(
        request=request,
        name="print_labels.html",
        context={
            "items": batches,
            "all_items": all_batches,
            "item_groups": item_groups,
            "selected": selected,
            "selected_batch_ids": {str(batch_id) for batch_id in selected_ids},
        },
    )


@app.get("/expiring-soon", response_class=HTMLResponse)
def expiring_soon(
    request: Request,
    session: Session = Depends(get_session),
    days: int = 7,
):
    today = date.today()
    cutoff = today + timedelta(days=days)

    statement = (
        select(Item)
        .where(
            Item.expiry_date.is_not(None),
            Item.expiry_date <= cutoff,
            Item.status == ItemStatus.ACTIVE,
        )
        .order_by(Item.expiry_date, Item.name)
    )

    items = session.exec(statement).all()

    return templates.TemplateResponse(
        request=request,
        name="expiring_soon.html",
        context={
            "items": items,
            "days": days,
            "today": today,
            "cutoff": cutoff,
        },
    )


# Simple JSON API endpoints for later mobile/API use.

@app.get("/api/items")
def api_list_items(session: Session = Depends(get_session)):
    statement = select(Item).order_by(Item.name)
    return session.exec(statement).all()


@app.get("/api/items/{item_id}")
def api_get_item(item_id: UUID, session: Session = Depends(get_session)):
    return get_item_or_404(session, item_id)


@app.get("/api/lookup/{qr_token}")
def api_lookup_item(qr_token: str, session: Session = Depends(get_session)):
    return get_item_by_token_or_404(session, qr_token)
