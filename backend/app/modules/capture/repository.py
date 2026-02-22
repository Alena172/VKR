from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.capture.models import CaptureItemModel
from app.modules.capture.schemas import CaptureCreate


class CaptureRepository:
    def list_items(self, db: Session, user_id: int | None) -> list[CaptureItemModel]:
        stmt = select(CaptureItemModel)
        if user_id is not None:
            stmt = stmt.where(CaptureItemModel.user_id == user_id)
        stmt = stmt.order_by(CaptureItemModel.id.desc())
        return list(db.scalars(stmt))

    def create(self, db: Session, payload: CaptureCreate) -> CaptureItemModel:
        row = CaptureItemModel(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


capture_repository = CaptureRepository()
