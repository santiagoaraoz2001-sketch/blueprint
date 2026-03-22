from pydantic import BaseModel


class WorkspaceSettingsResponse(BaseModel):
    root_path: str | None = None
    auto_fill_paths: bool = True
    watcher_enabled: bool = True


class WorkspaceSettingsUpdate(BaseModel):
    root_path: str | None = None
    auto_fill_paths: bool | None = None
    watcher_enabled: bool | None = None


class WorkspaceStatus(BaseModel):
    root_path: str | None = None
    watcher_running: bool = False
    folder_health: dict[str, bool] = {}
    inbox_count: int = 0


class InboxFile(BaseModel):
    name: str
    size_bytes: int
    extension: str
