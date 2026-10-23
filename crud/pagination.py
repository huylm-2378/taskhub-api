from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginate(
    db: Session,
    statement: Select,
    offset: int,
    limit: int,
    *,
    load_options: tuple = (),
):
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = db.scalar(count_statement) or 0

    page_statement = statement.options(*load_options).offset(offset).limit(limit)
    items = db.scalars(page_statement).unique().all()

    return items, total
