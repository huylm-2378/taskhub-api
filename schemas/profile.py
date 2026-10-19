from schemas.project import ProjectRead
from schemas.task import TaskWithRelations
from schemas.user import UserRead


class ProjectWithTasks(ProjectRead):
    tasks: list[TaskWithRelations]


class UserProfile(UserRead):
    projects: list[ProjectWithTasks]
    assigned_tasks: list[TaskWithRelations]
