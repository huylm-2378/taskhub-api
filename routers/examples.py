"""Các endpoint mock của bài tập trước, giữ nguyên hành vi."""
from enum import Enum

from fastapi import APIRouter, Path, Query

router = APIRouter(tags=["Examples (mock)"])

# Mock Database lưu trữ danh sách công việc
MOCK_TASKS = [
    {"id": 1, "title": "Thiết kế Database", "status": "DONE"},
    {"id": 2, "title": "Viết API Đăng nhập", "status": "IN_PROGRESS"},
    {"id": 3, "title": "Cấu hình Docker server", "status": "TODO"},
]

@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: int):
    # Ép kiểu tự động string -> int
    for task in MOCK_TASKS:
        if task["id"] == task_id:
            return task

    return {"error": "Task không tồn tại"}


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


@router.get("/tasks/status/{status_name}")
async def get_tasks_by_status(status_name: TaskStatus):
    # Chỉ chấp nhận: TODO, IN_PROGRESS, DONE
    return [
        task for task in MOCK_TASKS
        if task["status"] == status_name
    ]


@router.get("/tasks/")
async def search_tasks(
    keyword: str | None = None,
    limit: int = 10
):
    results = []
    for task in MOCK_TASKS:
        if keyword is None or \
                keyword.lower() in task["title"].lower():
            results.append(task)

    return results[:limit]


@router.get("/tasks/secure/{task_id}")
async def get_secure_task(
    task_id: int = Path(
        ...,  # Bắt buộc
        ge=1, le=10000  # Từ 1 đến 10000, bao gồm hai đầu
    ),
    keyword: str | None = Query(
        default=None,
        min_length=3, max_length=50,
        pattern=r"^[a-zA-Z0-9_ ]*$"
    )
):
    return {"status": "Dữ liệu hợp lệ"}
