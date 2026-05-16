from sqlmodel import SQLModel, Field
from typing import Optional


class SystemSetting(SQLModel, table=True):
    __tablename__ = "system_settings"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(default="", max_length=4096)
