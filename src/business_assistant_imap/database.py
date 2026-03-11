"""SQLAlchemy-based database for folder mappings and future features."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


class FolderMapping(Base):  # type: ignore[misc]
    """Maps a sender (email or @domain) to a target IMAP folder."""

    __tablename__ = "folder_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String, unique=True, nullable=False)
    folder = Column(String, nullable=False)
    mapping_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class Database:
    """Thin wrapper around SQLAlchemy for folder-mapping operations."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{path}", echo=False)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

    def _open(self) -> Session:
        return self._session_factory()

    def get_folder_mapping(self, email: str) -> FolderMapping | None:
        """Look up a folder mapping: exact email first, then @domain."""
        with self._open() as session:
            # 1. Exact email match
            mapping = (
                session.query(FolderMapping)
                .filter(FolderMapping.identifier == email.lower())
                .first()
            )
            if mapping:
                # Expunge so it can be used outside the session
                session.expunge(mapping)
                return mapping

            # 2. Domain match
            domain = email.lower().split("@")[-1] if "@" in email else ""
            if domain:
                mapping = (
                    session.query(FolderMapping)
                    .filter(FolderMapping.identifier == f"@{domain}")
                    .first()
                )
                if mapping:
                    session.expunge(mapping)
                    return mapping

        return None

    def set_folder_mapping(
        self, identifier: str, folder: str, mapping_type: str
    ) -> None:
        """Insert or update a folder mapping."""
        identifier = identifier.lower()
        with self._open() as session:
            existing = (
                session.query(FolderMapping)
                .filter(FolderMapping.identifier == identifier)
                .first()
            )
            if existing:
                existing.folder = folder
                existing.mapping_type = mapping_type
            else:
                session.add(
                    FolderMapping(
                        identifier=identifier,
                        folder=folder,
                        mapping_type=mapping_type,
                    )
                )
            session.commit()
