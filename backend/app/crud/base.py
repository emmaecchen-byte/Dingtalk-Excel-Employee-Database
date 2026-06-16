from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from sqlalchemy.orm import Session

from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, record_id: int) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == record_id).first()

    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, data: Union[Dict[str, Any], Any]) -> ModelType:
        payload = data if isinstance(data, dict) else data.model_dump()
        db_obj = self.model(**payload)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        data: Union[Dict[str, Any], Any],
    ) -> ModelType:
        payload = data if isinstance(data, dict) else data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, record_id: int) -> bool:
        obj = self.get(db, record_id)
        if not obj:
            return False
        db.delete(obj)
        db.commit()
        return True
