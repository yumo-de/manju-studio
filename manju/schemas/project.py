from pydantic import BaseModel
from datetime import datetime
from .story import Story, Storyboard


class Project(BaseModel):
    id: str
    created_at: datetime
    theme: str                 # 用户输入的主题
    status: str = "created"
    story: Story | None = None
    storyboard: Storyboard | None = None
    work_dir: str = ""         # data/projects/{id}/
