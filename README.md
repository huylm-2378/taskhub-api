# TaskHub API — SQLAlchemy, Pydantic & APIRouter

FastAPI + SQLAlchemy 2 + PostgreSQL, quản lý schema bằng Alembic. Project dùng
Python **3.15.0** (ghi trong `.python-version`) và Docker Compose để chạy PostgreSQL.

## Khởi chạy

Tại thư mục gốc project, chỉ cần chạy:

```bash
make dev
```

Lệnh này đảm bảo PostgreSQL đang chạy và sẵn sàng, áp dụng migration còn thiếu,
rồi bật API với tự động tải lại khi sửa code. Nếu DB đã chạy và schema đã cập
nhật, hai bước đầu không tạo lại dữ liệu. Khi một bước lỗi, lệnh dừng tại bước đó.
Makefile dùng thẳng `venv/bin/python3`, nên không cần `source venv/bin/activate`.

Nhấn **Ctrl+C** để dừng API. Database tiếp tục chạy; dùng `make db-stop` nếu muốn
dừng cả database. Có thể đổi cổng API bằng `make dev PORT=8001`.

Môi trường hiện tại đã được cài đặt. Chỉ cần cài lại thư viện khi setup máy mới
hoặc khi các file requirements thay đổi:

```bash
source venv/bin/activate
python3 --version  # Python 3.15.0
python3 -m pip install -r requirements-dev.txt
```

Nếu cài project trên máy mới, dùng [uv](https://docs.astral.sh/uv/getting-started/installation/)
phiên bản 0.13.1 trở lên để tạo môi trường trước khi kích hoạt:

```bash
UV_PYTHON_INSTALL_DIR="$PWD/.python" uv venv --python 3.15.0 --seed venv
```

Python được tải riêng vào `.python/`; thư viện của project nằm trong `venv/`.
Cả hai thư mục đều được bỏ qua bởi Git. Trong môi trường đã kích hoạt, `python`
và `python3` đều chạy Python 3.15.0; Python hệ thống vẫn hoạt động độc lập.
VS Code có cấu hình mặc định trỏ tới `venv/bin/python3`. Nếu editor đã lưu lựa
chọn khác, dùng **Python: Select Interpreter** và chọn đường dẫn này.

Nếu chưa có `.env`, sao chép `.env.example` thành `.env`. Đổi mật khẩu trong cả
`POSTGRES_PASSWORD` và `DATABASE_URL` cho khớp nhau. File `.env` đã được bỏ qua
trong `.gitignore`; không đưa thông tin đăng nhập thật vào `.env.example`.
Biến môi trường của tiến trình được ưu tiên hơn giá trị trong `.env`.

JWT yêu cầu `JWT_SECRET_KEY` ngẫu nhiên tối thiểu 32 byte trong `.env`. Workspace
hiện tại đã có khóa riêng. Khi setup máy mới, tạo khóa bằng lệnh sau rồi chép
kết quả vào `JWT_SECRET_KEY` trong `.env` (không commit khóa):

```bash
venv/bin/python3 -c 'import secrets; print(secrets.token_hex(32))'
```

`ACCESS_TOKEN_EXPIRE_MINUTES` mặc định là `30`. API từ chối khởi động nếu thiếu
khóa hoặc khóa quá ngắn. Dùng cùng một khóa cho các worker để token hợp lệ xuyên
suốt ứng dụng; thay khóa sẽ làm token đã cấp không còn hợp lệ.

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- Liveness: <http://127.0.0.1:8000/health> (chỉ kiểm tra API, không kiểm tra DB).

PostgreSQL chỉ mở cổng trên localhost; dữ liệu nằm trong Docker volume
`taskhub_postgres_data`. Dừng DB bằng `docker compose stop db`. Nếu cổng 5432 đang
bận, sửa `POSTGRES_PORT` và cổng trong `DATABASE_URL` sang cùng một giá trị khác.
Với PostgreSQL có sẵn ngoài Docker Compose, cấu hình `DATABASE_URL` rồi chạy
`venv/bin/python3 -m alembic upgrade head` và
`venv/bin/python3 -m uvicorn main:app --reload` trực tiếp.

## Cấu trúc

```text
main.py                 # Khởi tạo app, đăng ký router
config.py               # Đọc .env và cấu hình pool
error_messages.py       # Thông báo lỗi dùng chung
database.py             # Engine, Base, SessionLocal, get_db
routers/                # HTTP, validation tham số, mã lỗi
schemas/                # Pydantic: dữ liệu đầu vào và response
crud/                   # Truy vấn ORM và commit/rollback
services/               # Nghiệp vụ, transaction, email nền và cache tag
models/                 # User, Project, Task, Comment, Tag, Bookmark
alembic/versions/       # Lịch sử migration
tests/                  # API, quan hệ và ràng buộc database
Dockerfile              # Image API Python 3.15, chạy với user không phải root
docker-compose.yml      # App + migration + PostgreSQL; Redis tùy chọn
celery_app.py            # Broker/backend Redis, routing và lịch Celery Beat
workers/tasks.py         # Export Excel, email nhắc việc, quét job chờ
middleware.py           # Request ID và access/error log
logging_setup.py        # Log JSON ra stdout
Makefile                # make dev: bật DB, migrate, chạy API
```

## Thông báo lỗi dùng chung

Các thông báo lỗi do ứng dụng định nghĩa nằm trong `error_messages.py`, dùng
chung cho router, schema, service, cấu hình và worker. Khi cần thêm lỗi mới,
khai báo hằng số ở file này rồi sử dụng tại nơi phát sinh lỗi:

```python
import error_messages as errors

raise HTTPException(status_code=404, detail=errors.USER_NOT_FOUND)
```

Mã HTTP và loại exception vẫn được quyết định tại chỗ gọi. Với thông báo có
tham số, dùng placeholder có tên, ví dụ
`errors.INVALID_BOOLEAN_ENV.format(name=name)`. Module này không import các
module ứng dụng khác để tránh phụ thuộc vòng khi khởi động.

Việc gom thông báo không thay đổi nội dung lỗi hay định dạng response. Lỗi
validation tự sinh bởi FastAPI/Pydantic vẫn do framework xử lý.

## Model và quan hệ

- User sở hữu nhiều Project và được giao nhiều Task.
- Project chứa nhiều Task.
- Task chứa nhiều Comment; mỗi Comment có một User là tác giả.
- Task và Tag có quan hệ nhiều–nhiều qua bảng `task_tags`.
- Bookmark dùng khóa chính ghép `(user_id, task_id)` để mỗi user chỉ lưu một
  bookmark cho mỗi task; tự xóa khi user hoặc task bị xóa.

Mỗi entity có UUIDv4 và `created_at` được tạo theo UTC. PostgreSQL lưu thời gian
bằng cột có thông tin múi giờ. Email, username và tên Tag là duy nhất. Xóa Project sẽ xóa
Task, Comment và các liên kết Tag liên quan; bản thân Tag được giữ lại.

Pool có `pool_pre_ping=True`; kích thước được cấu hình qua `.env`. Giới hạn kết
nối tính riêng cho mỗi worker: `DB_POOL_SIZE + DB_MAX_OVERFLOW`. Dependency
`get_db()` đóng session trong `finally`, trả kết nối về pool.

## Thử API

| Phương thức | Đường dẫn | Chức năng |
| --- | --- | --- |
| POST | `/api/users/register` | Đăng ký tài khoản có mật khẩu |
| POST | `/api/users/login` | Đăng nhập bằng form OAuth2, trả JWT |
| GET / PUT | `/api/users/me` | Xem / cập nhật tài khoản đang đăng nhập |
| POST / GET | `/api/users` | Tạo / liệt kê user (admin) |
| GET | `/api/users/{user_id}` | Thông tin user cơ bản, không trả email |
| GET | `/api/users/{username}/profile` | Thông tin user cơ bản theo username, không lồng project/task |
| POST / GET | `/api/projects` | Tạo / liệt kê project; GET hỗ trợ lọc `owner_id` |
| GET | `/api/projects/{project_id}` | Xem project |
| PATCH | `/api/projects/{project_id}` | Cập nhật một phần project |
| GET / POST | `/api/projects/{project_id}/tasks` | Liệt kê / tạo task trong project, kèm assignee và tags |
| POST / GET | `/api/tags` | Admin tạo / user đang hoạt động liệt kê tag |
| PATCH | `/api/tags/{tag_id}` | Admin cập nhật tên tag |
| POST / GET | `/api/tasks` | Tạo / liệt kê task; GET hỗ trợ lọc `assignee_id` |
| GET / PATCH / DELETE | `/api/tasks/{task_id}` | Xem, cập nhật hoặc xóa task theo quyền |
| POST | `/api/tasks/{task_id}/bookmark` | Bookmark task cho user đang đăng nhập |
| DELETE | `/api/tasks/{task_id}/bookmark` | Bỏ bookmark của chính user đang đăng nhập; trả 204, chưa bookmark trả 404 |
| POST | `/api/tasks/{task_id}/assign` | Giao lại task cho user (PM/Admin) |
| POST | `/api/tasks/{task_id}/comments` | Thêm comment với tác giả từ JWT |
| PATCH / DELETE | `/api/tasks/{task_id}/comments/{comment_id}` | Sửa / xóa comment (tác giả hoặc PM/Admin) |

`GET /api/tasks` và `GET /api/projects/{project_id}/tasks` nhận `skip` (mặc định 0),
`limit` (mặc định 20, tối đa 100), và vẫn hỗ trợ `offset` cũ. Danh sách User/Project/Tag
dùng `offset` và `limit`; `GET /api/projects` nhận thêm bộ lọc `owner_id`.
`GET /api/tasks` có bộ lọc `project_id`, `assignee_id`, `status` (`TODO`, `IN_PROGRESS`, `DONE`) và
`priority` (`LOW`, `MEDIUM`, `HIGH`); xem Bài 5 bên dưới.

Các API danh sách User/Tag/Project/Task cùng trả object phân trang `Page`:

| Endpoint | Kiểu phần tử trong `items` |
| --- | --- |
| `GET /api/users` | `UserRead` (chỉ admin) |
| `GET /api/tags` | `TagRead` |
| `GET /api/projects` | `ProjectRead` |
| `GET /api/tasks` | `TaskRead` |
| `GET /api/projects/{project_id}/tasks` | `TaskWithRelations` |

Response gồm `items`, `total`, `offset`, `limit`. `total` là tổng số bản ghi
khớp tất cả bộ lọc **trước phân trang**, không phải độ dài của `items`.
Ví dụ có 23 kết quả, bỏ qua 40 bản ghi:

```json
{"items": [], "total": 23, "offset": 40, "limit": 20}
```

Trang đầu mặc định lấy tối đa 20 bản ghi. Trang cuối có thể ít hơn `limit`;
trang vượt dữ liệu có `items: []` nhưng giữ nguyên `total`. Nếu không có kết quả
khớp, `items: []` và `total: 0`. Metadata luôn dùng tên `offset`, kể cả khi
request task dùng `skip`. Frontend đọc `page.items` và tính còn trang tiếp theo
bằng `page.offset + page.items.length < page.total`. Dữ liệu có thể thay đổi
giữa các lần tải trang.

`GET /api/users` và `GET /api/tags` đã chuyển từ mảng trực tiếp sang `Page`;
frontend cần đọc danh sách qua `response.items`. Cache Tag lưu cả trang gồm
`items`, `total`, `offset`, `limit`. Các API tạo, chi tiết và cập nhật vẫn trả
object tài nguyên như trước; mảng `tags` lồng trong task cũng không đổi.

Các API dữ liệu yêu cầu Bearer token. Trong Swagger UI, gọi
`POST /api/users/register` trước:

```json
{"name": "Huy", "email": "huy@example.com", "username": "huy", "password": "MyTestPassword123!"}
```

Bấm **Authorize**, nhập username/password vừa đăng ký, để trống client_id và
client_secret rồi bấm **Authorize**. Swagger gọi endpoint login và gắn Bearer
token vào các request cần xác thực. Username/email phải chưa được dùng; nếu
trùng hồ sơ cũ, hãy dùng tài khoản mới để thực hành.

Lấy `id` trả về, dùng làm `owner_id` khi tạo Project:

```json
{"name": "TaskHub", "owner_id": "<UUID của User>"}
```

Lấy `id` của Project, dùng khi tạo Task:

```json
{
  "title": "Thiết kế database",
  "project_id": "<UUID của Project>",
  "assignee_id": "<UUID của User>",
  "priority": 3,
  "due_date": "2026-10-21T17:00:00+07:00"
}
```

`assignee_id` và `due_date` có thể bỏ qua. Nếu gửi `due_date`, phải kèm múi giờ
và không được nằm trong quá khứ; hãy thay ngày trong ví dụ bằng deadline tương lai.
Khi tạo task qua một trong hai endpoint, người được giao phải đang hoạt động;
user không tồn tại trả 404, user bị khóa trả 409 và không lưu task.
Priority nằm trong khoảng 1–5. API trả 201 khi tạo thành công, 404 khi không tìm
thấy tài nguyên, 409 khi xung đột và 422 khi dữ liệu không hợp lệ.

Phạm vi hiện tại: xác thực JWT, phân quyền admin/chủ project, tạo/xem User,
Project, Task, Tag, thêm/bỏ bookmark, giao lại task, thêm/sửa/xóa comment, cập nhật
Project/Tag và tài khoản hiện tại, cập nhật thông tin/trạng thái và xóa Task.
Các API đọc project/task vẫn dùng chung cho tài khoản đang hoạt động;
chưa có mô hình project riêng tư hoặc thành viên project. Chưa triển khai API
xóa User/Project/Tag. Task hỗ trợ TODO → IN_PROGRESS → DONE qua PATCH;
quyền và quy tắc chuyển trạng thái được mô tả trong Bài 6.
Các đường dẫn mock `/tasks/...` cũ đã được gỡ và trả 404.
Dùng API thật `/api/tasks` với Bearer token.

## Thực hành schema và Swagger UI

Project và Tag có ba schema riêng trong `schemas/project.py` và `schemas/tag.py`:

- `Create`: kiểm tra dữ liệu tạo mới; không nhận `id` hay `created_at` từ client.
- `Update`: cho phép chỉ gửi trường muốn sửa. CRUD dùng
  `model_dump(exclude_unset=True)` để giữ nguyên các trường không được gửi.
  `description: null` xóa mô tả project; `name` và `owner_id` không nhận `null`.
  Body `{}` giữ nguyên dữ liệu.
- `Read`: response gồm các trường của tài nguyên, UUID và `created_at`.
  `from_attributes=True` cho phép đọc thuộc tính từ đối tượng SQLAlchemy.

Luồng một request: APIRouter nhận request → Pydantic kiểm tra đầu vào → hàm
trong `crud/` truy vấn/cập nhật SQLAlchemy Model → database → schema Read → JSON.
Ví dụ `GET /api/tags`: `routers/tags.py` → `services/tag_cache.py` → cache hoặc
`crud/tags.py` → `models/tag.py` → `Page[TagRead]`. Lỗi validation trả 422
trước khi chạy thân hàm endpoint.

Chạy `make dev`, mở <http://127.0.0.1:8000/docs>, chọn endpoint rồi bấm
**Try it out** → nhập tham số/body → **Execute**:

1. Tạo User và Project theo ví dụ phía trên. Gọi `GET /api/projects`, sau đó
   sao chép `id` vào `GET /api/projects/{project_id}` để xem chi tiết.
2. Gọi `PATCH /api/projects/{project_id}` với `{"description": "Bài thực hành CRUD"}`.
   Gọi GET chi tiết để xác nhận tên và owner vẫn giữ nguyên. Thử tiếp
   `{"description": null}` để xóa mô tả.
3. Đăng nhập bằng tài khoản admin, gọi `POST /api/tags` với `{"name": "backend"}`. Sao chép `id` trả về và
   gọi `PATCH /api/tags/{tag_id}` với `{"name": "frontend"}`.
4. Gọi `GET /api/tags` với `offset=0`, `limit=20` để xem kết quả. Khi chưa tạo
   tag nào, API trả `{"items": [], "total": 0, "offset": 0, "limit": 20}`.
5. Thử tên rỗng hoặc UUID sai định dạng (422), UUID hợp lệ nhưng không tồn tại
   khi xem/sửa project hoặc sửa tag (404), và tạo/sửa tag trùng tên (409).

Các schema gắn vào endpoint hiển thị trong mục **Schemas** của Swagger UI.
Tag dùng chung toàn hệ thống; chỉ admin được tạo và đổi tên tag. User đang hoạt
động được xem danh sách và sử dụng tag có sẵn khi tạo task trong project mình quản lý.
User thường gọi POST/PATCH tag nhận 403, kể cả khi là chủ project.
`GET /api/projects`, `GET /api/projects/{project_id}` và `GET /api/tags`
không nhận request body; dữ liệu đầu vào nằm ở path/query parameters.

## Bài 3: Relationship, eager loading và dữ liệu lồng nhau

Quan hệ được khai báo bằng `ForeignKey` và `relationship(back_populates=...)`:
User → Project và Project → Task là một–nhiều; Task → assignee là nhiều–một;
Task ↔ Tag là nhiều–nhiều qua `task_tags`. Khóa chính ghép `(task_id, tag_id)`
ngăn gắn trùng cùng một tag vào một task.

Trước khi thử API mới, chạy `make dev` để áp dụng migration `0002`.
Nếu API đang chạy, dừng rồi chạy lại lệnh này; tự reload code không chạy migration.
Migration thêm `username` và giữ các dữ liệu/quan hệ cũ:

- User cũ nhận username `user_<UUID của user, bỏ dấu gạch ngang>`.
- Khi tạo user, có thể truyền `username` hoặc bỏ qua để tự sinh `user_<UUID ngẫu nhiên>`.
- Username được bỏ khoảng trắng hai đầu và chuyển chữ thường; dài 3–64 ký tự,
  chỉ gồm `a-z`, `0-9`, `_`. Username trùng trả 409.
- Xem username đã cấp qua `GET /api/users`; `name` vẫn là tên hiển thị, có thể trùng.

Trong Swagger, chuẩn bị user và project; dùng tài khoản admin tạo tag, rồi gọi
`POST /api/projects/{project_id}/tasks` với body:

```json
{
  "title": "Thực hành eager loading",
  "assignee_id": "<UUID của User>",
  "tag_ids": ["<UUID của Tag backend>", "<UUID của Tag urgent>"],
  "priority": 3
}
```

`project_id` lấy từ URL, không gửi trong body. Có thể bỏ `assignee_id` và `tag_ids`;
response khi đó có `assignee: null`, `tags: []`. `tag_ids` nhận tối đa 100 phần tử,
tự bỏ UUID trùng. Project, assignee hoặc tag không tồn tại trả 404 và không tạo task.
Task cùng các liên kết tag được lưu trong một transaction.

Gọi `GET /api/projects/{project_id}/tasks?offset=0&limit=20` để xem task kèm
object `assignee` và mảng `tags`. Có thể lọc `status=TODO|IN_PROGRESS|DONE`.
Danh sách vẫn phân trang theo task dù mỗi task có nhiều tag; project không tồn
tại trả 404, project chưa có task trả page với `items: []`, `total: 0`.

Gọi `GET /api/users/huy/profile` hoặc `GET /api/users/{user_id}` để xem
`UserSummary`, chỉ gồm `id`, `created_at`, `name`, `username`. Hai endpoint này
không trả `email`, `role`, `is_active` hoặc các collection project/task.
Username được chuẩn hóa chữ thường. `/api/users/me` vẫn trả thông tin đầy đủ của
chính người đăng nhập; danh sách `/api/users` chỉ cho admin và vẫn có email.

Lấy `id` từ profile để lọc trên các API danh sách hiện có:

```http
GET /api/projects?owner_id=<UUID>&offset=0&limit=20
GET /api/projects?owner_id=<UUID>&offset=20&limit=20
GET /api/tasks?assignee_id=<UUID>&skip=0&limit=20
GET /api/tasks?assignee_id=<UUID>&status=TODO&priority=HIGH
GET /api/projects/{project_id}/tasks?skip=0&limit=20
```

- `/api/projects?owner_id=...` trả `Page[ProjectRead]` của các project user sở hữu,
  không lồng `tasks`. Bỏ `owner_id` để lấy danh sách project không lọc theo owner.
- `/api/tasks?assignee_id=...` trả `Page[TaskRead]` được giao cho user, kể cả task
  thuộc project người khác. Mỗi phần tử trong `items` có `assignee_id`, không lồng `assignee` hoặc
  `tags`. Bỏ `assignee_id` để lấy danh sách không lọc theo người được giao, gồm cả
  task chưa giao. Có thể kết hợp `project_id`, `status`, `priority` bằng AND.
- Project dùng `offset`, task dùng `skip` (đều mặc định 0, tối thiểu 0).
  `limit` mặc định 20, từ 1 đến 100. Task vẫn nhận `offset` cũ; gửi cả `skip`
  khác 0 và `offset` khác nhau trả 422. Tham số sai định dạng/giới hạn trả 422.
- Dữ liệu được lọc theo user, sắp xếp theo `created_at`, `id`, rồi phân trang
  ngay trong SQL. Response có `items`, `total`, `offset`, `limit`.
- UUID hợp lệ nhưng user không tồn tại, không có dữ liệu khớp hoặc trang vượt
  số bản ghi đều trả 200 với `items: []`. `total` là 0 khi không có dữ liệu khớp,
  nhưng vẫn giữ số kết quả khớp nếu chỉ vượt trang. UUID sai định dạng trả 422. Các bộ lọc này
  vẫn đọc được dữ liệu gắn với user bị khóa; không kiểm tra trạng thái user đích.

Các endpoint đọc này cho phép mọi user đang hoạt động, giống quyền đọc project/task
hiện có. Thiếu JWT hoặc JWT không hợp lệ trả 401; tài khoản bị khóa trả 403.
Hai route `/api/users/{user_id}/projects` và `/api/users/{user_id}/assigned-tasks`
đã được gỡ. Frontend dùng hai route này hoặc đọc `profile.projects`/
`profile.assigned_tasks` cần chuyển sang API danh sách với bộ lọc tương ứng.
Nếu cần task kèm `assignee` và `tags`, dùng `GET /api/projects/{project_id}/tasks`
trả `Page[TaskWithRelations]` khi mở project.

Trong `crud/tasks.py`, danh sách task theo project dùng eager loading:

```python
select(Task).options(
    joinedload(Task.assignee),
    joinedload(Task.tags),
    raiseload("*"),
)
```

`joinedload` tải task cùng assignee/tags bằng JOIN. Khi JOIN một collection,
một task có thể xuất hiện ở nhiều hàng SQL; `.unique()` gộp chúng thành một
object Task. `raiseload("*")` báo lỗi nếu response vô tình truy cập relationship
chưa tải, giúp phát hiện lazy loading ngoài dự kiến.

Endpoint profile dùng `get_by_username()` để chỉ tải user; hàm `get_profile()`
và `schemas/profile.py` cũ đã được xóa. Các import model chỉ dùng cho type hint
trong `models/tag.py`, `models/user.py`, `models/task.py` nằm trong `TYPE_CHECKING`;
`models/__init__.py` vẫn đăng ký đầy đủ model tại runtime để ORM resolve quan hệ.
Danh sách project
lọc theo `Project.owner_id`; danh sách task lọc theo `Task.assignee_id` trước
phân trang. Hai danh sách này không tải relationship. Danh sách task theo project
vẫn dùng `joinedload` assignee/tags và phân trang theo task.
Tham khảo [SQLAlchemy Relationship Loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html).

Test truy vấn thay dependency xác thực bằng user giả để đo riêng nghiệp vụ,
kể cả serialize response: với bộ dữ liệu
1 và 12 phần tử, danh sách task theo project dùng **3 SELECT** (kiểm tra project
+ đếm task + tải tasks/assignee/tags), profile dùng **1 SELECT**. Danh sách project/task
có bộ lọc user dùng **2 SELECT** (đếm kết quả + tải trang dữ liệu), không truy vấn kiểm tra
user đích hoặc tải quan hệ từng task. Khi dùng JWT thật, truy vấn xác thực
current user cũng được tính thêm;
SQLAlchemy có thể tái sử dụng user trong session khi đọc chính user đó.

`tests/test_user_collections.py` kiểm tra 23 bản ghi với thời gian tạo trùng nhau,
thứ tự ổn định, trang mặc định 20 bản ghi, lọc đúng user, trang cuối/rỗng và task
có nhiều tag không bị lặp. `tests/test_filtering.py` kiểm tra `assignee_id`
kết hợp với project/status/priority trước phân trang và `total` theo cùng bộ lọc.
`tests/test_pagination.py` kiểm tra dependency chung, giới hạn tham số, tương thích
`skip`/`offset`, response `Page` cho User/Tag, thứ tự ổn định khi trùng thời gian
tạo, tổng bản ghi ở trang cuối/vượt dữ liệu và tổng task sau tạo/xóa.
`tests/test_permissions.py` kiểm tra bằng JWT thật:
không lộ email người khác, giữ quyền xem `/me` và danh sách admin, từ chối token
sai và tài khoản bị khóa.

```bash
venv/bin/python -m pytest -q tests/test_pagination.py tests/test_user_collections.py tests/test_filtering.py tests/test_relationship_api.py tests/test_permissions.py tests/test_auth.py tests/test_api.py
```

## Bài 4: JWT, OAuth2 và Dependency Injection

Cài dependencies mới bằng `venv/bin/python3 -m pip install -r requirements-dev.txt`,
sau đó dừng server và chạy lại `make dev` để áp dụng migration `0003`.
Migration thêm `hashed_password` nullable: user cũ giữ nguyên ID, project và task,
nhưng chưa có mật khẩu nên không thể đăng nhập. `POST /api/users` cũ vẫn tạo hồ sơ
không có mật khẩu và từ Bài 5 yêu cầu admin. Dùng `/register` để tạo tài khoản đăng nhập;
không tự cấp mật khẩu mặc định hoặc cho phép chiếm hồ sơ cũ qua email/username.

Luồng xác thực:

1. `POST /api/users/register` nhận JSON, kiểm tra dữ liệu và băm mật khẩu bằng
   bcrypt (cost 12). Mật khẩu tối thiểu 8 ký tự, tối đa 72 byte UTF-8; giữ nguyên
   khoảng trắng và chữ hoa/thường. Database chỉ lưu hash; response dùng `UserRead`
   nên không trả password/hash. Username hoặc email trùng trả 409.
2. `POST /api/users/login` nhận **form** `application/x-www-form-urlencoded`,
   không nhận JSON. Gửi `username`, `password`; `grant_type=password` có thể gửi
   thêm. Mật khẩu sai, user không tồn tại hoặc hồ sơ chưa có mật khẩu đều trả 401
   với cùng thông báo. Thành công trả `{"access_token": "...", "token_type": "bearer"}`.
3. Client gửi `Authorization: Bearer <access_token>`. `OAuth2PasswordBearer` đọc
   header; `get_current_user` trong `routers/dependencies.py` kiểm tra chữ ký HS256,
   thời hạn và các claim bắt buộc `sub`, `iat`, `exp`, rồi lấy user theo UUID trong
   `sub`. Token sai/hết hạn, user đã xóa hoặc không có mật khẩu trả 401 với header
   `WWW-Authenticate: Bearer`.
4. `GET /api/users/me` trả user lấy từ dependency. `PUT /api/users/me` sửa
   `name`, `email`, `username` của chính user đó. Chỉ trường gửi lên được đổi;
   trường bỏ qua giữ nguyên, `null` không hợp lệ, `{}` giữ nguyên dữ liệu.
   Không nhận `id`, password, hash hoặc role. Token vẫn dùng được sau khi đổi
   username vì `sub` là UUID; lần đăng nhập sau dùng username mới.

Ví dụ body cập nhật:

```json
{"name": "Huy Updated", "email": "huy.updated@example.com"}
```

Toàn bộ `/api/users`, `/api/projects`, `/api/tasks`, `/api/tags` được bảo vệ;
chỉ `/api/users/register` và `/api/users/login` công khai trong nhóm `/api/`.
`/docs`, `/openapi.json`, `/health` vẫn công khai. Router auth
được đăng ký trước router user để `/me` không bị hiểu là `/{user_id}`.

Thử bằng Swagger: đăng ký → **Authorize** → gọi `/me` → PUT đổi tên → GET kiểm tra.
Bấm **Logout** trong Authorize rồi gọi API dữ liệu để thấy 401. Token hết hạn thì
đăng nhập lại; bài này chưa có refresh token, thu hồi token hoặc đổi/reset mật khẩu.
Logout ở Swagger chỉ xóa token khỏi giao diện, không thu hồi token đã phát hành.

`JWT_IAT_LEEWAY_SECONDS` mặc định `5`, nhận giá trị 0–30: cho phép `iat` (thời điểm
phát hành) đi trước đồng hồ kiểm tra tối đa từng đó giây để chịu được lệch đồng
hồ nhỏ hoặc đồng hồ vừa lùi. Đặt 0 để kiểm tra tuyệt đối. Chữ ký, thuật toán,
claim bắt buộc và `exp`/`nbf` vẫn được kiểm tra nghiêm ngặt; token hết hạn không
được thêm thời gian sống. `iat` phải là số nguyên. Khi vượt ngưỡng, API trả 401
và log `clock_skew_seconds`, không ghi token hoặc secret. Các server vẫn cần
đồng bộ giờ bằng NTP. Test đồng hồ cố định trong `tests/test_jwt_clock.py` tái
hiện lỗi `ImmatureSignatureError` khi lùi 2 giây trước bản sửa, kiểm tra biên
5/6 giây và xác nhận token hết hạn/tương lai xa vẫn bị từ chối.
Tham khảo [PyJWT claims validation](https://pyjwt.readthedocs.io/en/stable/api.html).

Các test auth dùng JWT và dependency thật, kiểm tra toàn bộ route được bảo vệ,
token sai chữ ký/thuật toán/hết hạn/thiếu claim, không lộ hash, cập nhật đúng user,
rollback khi trùng username/email và luồng user thường tạo project/task với tag có sẵn.
Test phân quyền kiểm tra admin tạo/đổi tên tag, user thường chỉ đọc và sử dụng tag;
admin bị khóa hoặc hạ role mất quyền ghi ngay cả khi JWT cũ còn hạn.
Tham khảo [FastAPI OAuth2 JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
và [bcrypt](https://github.com/pyca/bcrypt).

## Bài 5: Phân quyền, Filtering và Pagination

Chạy `make dev` để áp dụng migration `0004` và khởi động API. Migration thêm
`users.is_active` (mặc định `true`), `users.role` (mặc định `USER`) và bảng
`bookmarks`. Tài khoản cũ giữ nguyên dữ liệu và có role `USER`; không tự cấp admin.

Các dependency trong `routers/dependencies.py`:

- `get_current_active_user`: lấy user từ JWT rồi kiểm tra `is_active`. Áp dụng
  cho toàn bộ API dữ liệu và `/me`. Tài khoản bị khóa nhận 403 ngay cả với token
  chưa hết hạn; đăng nhập bằng mật khẩu đúng cũng nhận 403.
- `verify_admin_role`: chỉ cho role `ADMIN` tạo hồ sơ bằng `POST /api/users`
  hoặc xem danh sách bằng `GET /api/users`, tạo tag bằng `POST /api/tags` và
  đổi tên tag bằng `PATCH /api/tags/{tag_id}`. `/register` vẫn công khai;
  `GET /api/tags` cho phép mọi user đang hoạt động.
- `verify_project_manager`: chủ sở hữu (`project.owner_id`) hoặc admin được
  sửa project và tạo task qua cả hai đường dẫn `/api/tasks` và
  `/api/projects/{project_id}/tasks`. User thường chỉ tạo project cho chính mình.
  Chủ project được chuyển quyền sở hữu; quyền quản lý chuyển sang chủ mới ngay.

Khi tạo project (`POST /api/projects`) hoặc gửi `owner_id` để chuyển chủ sở hữu
(`PATCH /api/projects/{project_id}`), owner phải tồn tại và đang hoạt động.
Owner không tồn tại trả 404 (`Owner not found`); owner bị khóa trả 409
(`Owner is inactive`), kể cả khi admin gửi request. Request bị từ chối không
tạo project hoặc lưu bất kỳ trường cập nhật nào. PATCH không gửi `owner_id`
vẫn cho phép admin sửa tên/mô tả của project có owner đã bị khóa.

Chạy unit test kiểm tra owner và test tích hợp API/quyền với JWT thật:

```bash
venv/bin/python -m pytest tests/test_project_owners.py tests/test_permissions.py tests/test_api.py -q
```

Role và trạng thái hoạt động được đọc từ DB ở mỗi request. Các body đăng ký,
tạo hồ sơ và sửa `/me` không cho phép truyền `role` hay `is_active`. Để thực hành
admin, người vận hành có thể cập nhật tài khoản đã đăng ký trong PostgreSQL:

```sql
UPDATE users SET role = 'ADMIN' WHERE username = 'huy';
```

Thiếu JWT hoặc JWT không hợp lệ trả 401; thiếu quyền hoặc tài khoản bị khóa trả
403; tài nguyên không tồn tại trả 404; query/body không hợp lệ trả 422.

### Lọc và phân trang trực tiếp bằng Query Parameters

`routers/pagination.py` gom `DEFAULT_OFFSET = 0`, `DEFAULT_LIMIT = 20`,
`MAX_LIMIT = 100` và validation query. `PaginationDep` dùng `Annotated`/`Depends`
cho User/Project/Tag; `TaskPaginationDep` nhận `skip` và `offset` cũ cho hai
danh sách task. Cả hai trả `Pagination(offset, limit)` để router dùng chung.
`schemas/pagination.py` định nghĩa `Page[T]`; `crud/pagination.py` thực hiện
COUNT trên truy vấn đã lọc rồi SELECT trang dữ liệu. Truy vấn COUNT không tải
relationship nên task nhiều tag không làm tăng `total`.

Các bộ lọc kết hợp bằng AND, chạy trước phân trang. Dữ liệu được sắp xếp theo
`created_at`, rồi `id` để phân trang có thứ tự ổn định. Các phần tử nằm trong `items`.

| Tham số | Giá trị |
| --- | --- |
| `skip` | Số task bỏ qua, mặc định 0, không âm |
| `limit` | Số task tối đa, mặc định 20, từ 1 đến 100 |
| `status` | `TODO`, `IN_PROGRESS`, `DONE`; bỏ qua để lấy mọi trạng thái |
| `priority` | `LOW` = 1–2, `MEDIUM` = 3, `HIGH` = 4–5 |
| `project_id` | UUID lọc project trên `GET /api/tasks` |
| `assignee_id` | UUID lọc người được giao trên `GET /api/tasks`; kết hợp với các bộ lọc khác bằng AND |
| `offset` | Tương thích API cũ; bị đánh dấu deprecated trong Swagger |

`GET /api/projects` dùng `owner_id` tùy chọn để lọc chủ sở hữu, phân trang bằng
`offset` và `limit`. Cả `owner_id` và `assignee_id` không có dữ liệu khớp đều trả
page với `items: []`, `total: 0`.

Body tạo task và response vẫn dùng priority số 1–5. Nếu có `offset`, nó thay
`skip=0` mặc định; nếu `skip` khác 0 và khác `offset`, API trả 422.

Sau khi đăng nhập và lấy token, thử:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/tasks?status=TODO&priority=HIGH'

curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/projects/$PROJECT_ID/tasks?skip=10&limit=5"

curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/bookmark"

curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/bookmark"
```

Bookmark không cần body: user được lấy từ JWT, task lấy từ path. Thành công trả
200 với `user_id`, `task_id`, `created_at`. Gọi lại trả bookmark đã lưu, không
tạo bản sao; hai user bookmark cùng task sẽ có hai bản ghi riêng. Mọi tài khoản
đang hoạt động đều được bookmark task, không yêu cầu quyền quản lý project.

`DELETE /api/tasks/{task_id}/bookmark` cũng không cần body, chỉ bỏ bookmark
của user lấy từ JWT; không xóa task, bookmark của người khác hoặc bookmark
của user đó trên task khác. Thành công trả 204, không có body. Nếu task còn
tồn tại nhưng user chưa bookmark hoặc đã bỏ bookmark, trả 404 với
`"Bookmark not found"`; gọi xóa lần hai cũng trả lỗi này. Có thể gọi POST để
bookmark lại. Admin cũng chỉ bỏ được bookmark của chính mình.
Task không tồn tại trả 404 với `"Task not found"`; UUID không hợp lệ trả 422; thiếu/sai JWT trả 401;
user bị khóa trả 403. Request bị từ chối không xóa bookmark.

Các test mới kiểm tra quyền bằng JWT thật, chặn tự nâng quyền, thu hồi quyền khi
đổi role/khóa tài khoản/chuyển chủ project, thêm/bỏ bookmark riêng từng user, xóa theo
khóa ngoại, bộ lọc kết hợp và phân trang sau khi lọc. Test migration kiểm tra
schema và dữ liệu cũ trên SQLite tạm; không sửa database trong `.env`.

Chạy unit test kết quả xóa/rollback khi bỏ bookmark, test API/quyền và kiểm tra router mock
đã được gỡ khỏi ứng dụng/OpenAPI:

```bash
venv/bin/python -m pytest tests/test_bookmarks.py tests/test_permissions.py tests/test_api.py tests/test_auth.py -q
```

## Bài 6: Nghiệp vụ tương tác task và Transaction

Phần này dùng bảng `comments` và `tasks.assignee_id` đã có, không cần migration
mới. Khởi động bằng `make dev`, đăng nhập và dùng Bearer token cho các API sau.
PM tiếp tục được hiểu là chủ sở hữu của project chứa task.

| API | Body | Quyền | Thành công |
| --- | --- | --- | --- |
| `POST /api/tasks/{task_id}/assign` | `{"assignee_id": "<UUID user>"}` | PM của project hoặc Admin | 200, task sau khi giao |
| `POST /api/tasks/{task_id}/comments` | `{"content": "Đã hoàn tất API"}` | Tài khoản đang hoạt động | 201, comment vừa tạo |
| `PATCH /api/tasks/{task_id}/comments/{comment_id}` | `{"content": "Nội dung cập nhật"}` | Tác giả, PM của project hoặc Admin | 200, comment sau khi sửa |
| `DELETE /api/tasks/{task_id}/comments/{comment_id}` | Không có body | Tác giả, PM của project hoặc Admin | 204, không có body |

Giao task yêu cầu `assignee_id` là UUID của user tồn tại và đang hoạt động;
không nhận `null` hoặc bỏ trống. User không tồn tại trả 404, user bị khóa trả
409. Giao lại cho cùng user là thao tác hợp lệ. Endpoint chỉ đổi `assignee_id`,
giữ nguyên trạng thái và các thông tin task khác. Hồ sơ user cũ chưa có mật khẩu
vẫn có thể nhận task nếu đang hoạt động, giống quy ước tạo task hiện có.

Comment nhận `content` từ 1 đến 10.000 ký tự sau khi bỏ khoảng trắng đầu/cuối;
chuỗi rỗng, chỉ khoảng trắng, `null`, thiếu content hoặc trường thừa trả 422.
`author_id` luôn lấy từ JWT và `task_id` lấy từ URL; client không được gửi hai
trường này trong body. Response gồm `id`, `created_at`, `content`, `task_id`,
`author_id`. Sửa comment giữ nguyên tác giả và task.

Comment phải thuộc đúng `task_id` trên URL; sai task hoặc không tồn tại trả 404,
kể cả với Admin. Người được giao task và PM của project khác không được sửa/xóa
comment của người khác (403). Khi chuyển chủ project, quyền PM chuyển theo chủ
mới; tác giả vẫn giữ quyền với comment của mình. Mọi API tiếp tục chặn tài khoản
bị khóa (403), thiếu token hoặc token sai (401).

Ví dụ sau khi đặt `TOKEN`, `TASK_ID`, `ASSIGNEE_ID`, `COMMENT_ID`:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"assignee_id\": \"$ASSIGNEE_ID\"}" \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/assign"

curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content": "Đã hoàn tất API"}' \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/comments"

curl -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content": "Đã hoàn tất API và kiểm thử"}' \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/comments/$COMMENT_ID"

curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID/comments/$COMMENT_ID"
```

### Cập nhật và xóa task

`PATCH /api/tasks/{task_id}` trả 200 với task sau cập nhật. PM của project hoặc
Admin được sửa `title`, `description`, `priority`, `due_date`, `status`.
Người được giao task chỉ được gửi `status`; user khác nhận 403. Quyền được lấy
lại từ task/project hiện tại, nên người đã bị giao lại task hoặc chuyển chủ
project không giữ quyền cũ. Tài khoản bị khóa vẫn bị từ chối.

- Bỏ qua trường để giữ nguyên. PM/Admin gửi `{}` giữ nguyên task.
- `description: null` hoặc `due_date: null` xóa giá trị tương ứng.
- `title`, `priority`, `status` không nhận `null`; deadline phải kèm timezone.
- Không nhận `project_id`, `assignee_id`, `tag_ids` hoặc trường thừa. Dùng
  endpoint `/assign` riêng để giao task.
- Chuyển trạng thái theo TODO → IN_PROGRESS → DONE. Gửi lại trạng thái hiện tại
  là hợp lệ; bỏ qua một bước hoặc quay lùi trả 409, không lưu một phần body.
  Hai API `POST /api/tasks` và `POST /api/projects/{project_id}/tasks` không nhận
  trường `status` (gửi vào trả 422); task mới luôn có trạng thái `TODO`.
  Nếu cung cấp `due_date`, giá trị phải kèm timezone và không được nằm trong
  quá khứ tại thời điểm tạo. PATCH vẫn cho phép deadline quá khứ.

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"IN_PROGRESS"}' "http://127.0.0.1:8000/api/tasks/$TASK_ID"
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"DONE"}' "http://127.0.0.1:8000/api/tasks/$TASK_ID"
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/tasks/$TASK_ID"
```

`DELETE /api/tasks/{task_id}` chỉ dành cho PM/Admin, trả 204 không có body.
Task không tồn tại hoặc xóa lại trả 404. Xóa task đồng thời xóa comment, bookmark
và liên kết tag; giữ nguyên tag, project, user và task khác. Đây là xóa vĩnh viễn.
Cả hai nghiệp vụ dùng transaction và khóa hàng như `/assign`, không cần migration.

### Ranh giới transaction

Router kiểm tra schema và xác thực, rồi gọi `services/task_interactions.py`.
Mỗi nghiệp vụ dùng `transaction(db)` trong `services/transactions.py` để kiểm
tra tài nguyên, quyền và ghi dữ liệu trên cùng session, chỉ commit một lần:

1. Dependency xác thực đã mở transaction ngầm qua SELECT; service tiếp tục
   transaction đó, không gọi `db.begin()` lần nữa hoặc CRUD có commit trung gian.
2. Trên PostgreSQL, truy vấn khóa task/project bằng `SELECT ... FOR UPDATE`
   đến khi kết thúc transaction. Sửa/xóa comment khóa thêm bản ghi comment;
   giao task giữ khóa đọc trên user đích để trạng thái hoạt động không đổi giữa
   lúc kiểm tra và ghi dữ liệu.
3. Hoàn tất nghiệp vụ: `flush()` để gửi SQL và lấy ID/thời gian tạo, rồi `commit()`.
   Mọi exception trong nghiệp vụ, flush hoặc commit đều gọi `rollback()`.
   Xung đột ràng buộc dữ liệu hoặc bản ghi đã thay đổi trả 409; lỗi bất ngờ được
   chuyển tiếp để xử lý như lỗi server sau khi rollback.

Các test trong `tests/test_task_interactions.py` kiểm tra API bằng JWT thật,
ma trận quyền, comment sai task, dữ liệu đầu vào và trạng thái đã lưu. Test
transaction gây lỗi sau flush hoặc trước commit cho cả sáu nghiệp vụ, xác nhận
DB không lưu thay đổi dở dang và session vẫn dùng lại được sau rollback.
Test chạy trên SQLite tạm; SQLite không thực thi khóa hàng `FOR UPDATE`, nên
bộ test này không xác nhận hành vi tranh chấp khóa đồng thời trên PostgreSQL.

## Bài 7: Testing, Background Tasks và Caching

Phần này không thay đổi schema. Cài các dependency mới rồi khởi động API:

```bash
venv/bin/python3 -m pip install -r requirements-dev.txt
make dev
```

### Integration test: đăng ký → đăng nhập → tạo project → tạo task

`tests/test_registration_task_flow.py` dùng `TestClient` thật từ fixture
`anonymous_client`, không thay dependency xác thực hoặc CRUD. Test đăng ký user,
đăng nhập lấy JWT, tạo project của chính user, rồi tạo task qua cả hai đường dẫn
`/api/tasks` và `/api/projects/{project_id}/tasks`. Test kiểm tra mã phản hồi,
request thiếu token, task đọc lại qua API/bộ lọc và dữ liệu đã lưu trong DB.
Các test dùng SQLite tạm với migration thật, không dùng DB trong `.env`.

```bash
venv/bin/python3 -m pytest -q tests/test_registration_task_flow.py
venv/bin/python3 -m pytest -q
```

Cách sử dụng `TestClient` và pytest theo [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/).

### Email thông báo comment chạy nền

`POST /api/tasks/{task_id}/comments` trả 201 sau khi comment được commit, rồi
FastAPI chạy `notifications.notify_comment(comment.id)` bằng `BackgroundTasks`.
Job chỉ nhận UUID, mở session riêng để đọc comment đã lưu và đóng session trước
khi kết nối SMTP. Cách thêm tác vụ sau response theo
[FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

Người nhận là chủ project và người được giao task tại thời điểm job đọc DB:
loại trùng, bỏ qua chính tác giả comment và user bị khóa. Mỗi người nhận có một
email riêng. Task chưa giao vẫn thông báo cho chủ project nếu chủ không phải
tác giả. Nếu comment/task đã bị xóa trước khi job đọc dữ liệu, job bỏ qua.
PATCH/DELETE comment không gửi thông báo.

Email mặc định **tắt**. Cấu hình SMTP trong `.env` để gửi thật, sau đó khởi động
lại API. Không cần đưa SMTP credentials vào request:

```dotenv
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_smtp_username
SMTP_PASSWORD=your_smtp_password
SMTP_FROM=notifications@your-domain.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=5
```

`SMTP_USE_TLS=true` dùng STARTTLS. Nếu nhà cung cấp dùng TLS ngay khi kết nối
(thường cổng 465), đặt `SMTP_USE_SSL=true`, `SMTP_USE_TLS=false`; không bật cả hai.
Với SMTP thử nghiệm cục bộ không xác thực, có thể để trống username/password và
tắt TLS/SSL theo cấu hình server. Timeout áp dụng cho thao tác mạng SMTP.

Lỗi gửi email được ghi log với ID comment và loại lỗi, không ghi nội dung,
địa chỉ email, mật khẩu hoặc phản hồi SMTP. Một người nhận lỗi không ngăn gửi
cho người còn lại; comment vẫn tồn tại và API vẫn trả 201. Lỗi đọc DB của job
cũng được ghi log. `BackgroundTasks` chạy trong tiến trình API, không có hàng
đợi bền vững hoặc retry tự động: nếu tiến trình dừng sau commit, email có thể
không được gửi. Nếu cần bảo đảm giao thông báo, bước tiếp theo là transactional
outbox và worker có retry.

`tests/test_background_tasks.py` kiểm tra job chạy sau response và sau commit,
chọn đúng người nhận, rollback không tạo job, SMTP lỗi không mất comment và cấu
hình STARTTLS/SSL. SMTP được giả lập nên không gửi email thật. `TestClient` chờ
background task hoàn tất trước khi trả kết quả cho test; test dùng sự kiện ASGI
để xác nhận response đã được gửi trước khi bắt đầu gửi email.

### Kiểm chứng SMTP thật bằng Mailpit cục bộ

Profile `mail` cung cấp [Mailpit](https://mailpit.axllent.org/docs/install/docker/):
SMTP nhận thư ở cổng 1025, hộp thư web ở 8025, chỉ publish trên localhost.
Thư được nhận qua kết nối SMTP thật và giữ trong Mailpit; không chuyển tiếp
ra Gmail/Outlook hoặc người dùng thật. Trong `.env`, cấu hình cho app Docker:

```dotenv
EMAIL_ENABLED=true
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=taskhub@example.com
SMTP_USE_TLS=false
SMTP_USE_SSL=false
```

```bash
docker compose --profile mail up -d --build --wait
```

Mở <http://127.0.0.1:8025>, rồi tạo comment bằng một user khác chủ project/người
được giao task. Mỗi người nhận đủ điều kiện có một thư riêng. Với `make dev`,
đổi `SMTP_HOST=127.0.0.1` và chỉ chạy `docker compose --profile mail up -d mailpit`.
Đổi cổng host bằng `MAILPIT_HTTP_PORT`/`MAILPIT_SMTP_PORT` nếu đang bị chiếm;
app Docker vẫn dùng `mailpit:1025`.

Test tích hợp dùng database tạm và kết nối SMTP loopback, không mock `smtplib`.
Nó tạo comment qua API rồi đọc hộp thư Mailpit qua HTTP để xác nhận người nhận,
nội dung tiếng Việt và comment ID. Có thêm test kết nối SMTP bị từ chối để
kiểm tra comment vẫn được commit và response vẫn là 201:

```bash
MAILPIT_HTTP_URL=http://127.0.0.1:8025 MAILPIT_SMTP_PORT=1025 \
  venv/bin/python3 -m pytest -q tests/test_smtp_delivery.py
```

Đặt cùng hai biến môi trường khi chạy toàn bộ test để bật kiểm thử gửi thư.
Nếu không đặt `MAILPIT_HTTP_URL`, chỉ test gửi thư tới Mailpit được skip.
Đây là xác minh SMTP cục bộ; gửi tới nhà cung cấp bên ngoài cần credentials và
địa chỉ nhận thử riêng, cùng cấu hình TLS tương ứng.

### Redis cache danh sách tag (tùy chọn)

Để trống `REDIS_URL` thì API đọc database như trước. Bật Redis cục bộ bằng:

```bash
docker compose --profile cache up -d --wait redis
```

Sau đó thêm vào `.env` và khởi động lại API:

```dotenv
REDIS_URL=redis://localhost:6379/0
TAGS_CACHE_TTL_SECONDS=60
TAGS_CACHE_PREFIX=taskhub:tags:v1
```

Container Redis chỉ mở cổng trên localhost; dùng `REDIS_PORT` nếu cần đổi cổng
và cập nhật URL cho khớp. `make dev` vẫn chỉ tự khởi động PostgreSQL. Dừng Redis
bằng `docker compose --profile cache stop redis`. Cache không cần lưu volume.
Dùng prefix riêng cho từng môi trường nếu dùng chung một Redis database.

`GET /api/tags?offset=0&limit=20` cache JSON của toàn bộ `Page[TagRead]` theo từng
cặp `offset/limit`, kể cả trang có `items: []`, với TTL mặc định 60 giây.
Trang vượt dữ liệu vẫn giữ tổng số tag trong `total`. Key dữ liệu có dạng
`{TAGS_CACHE_PREFIX}:page:v2:{generation}:{offset}:{limit}` để không đọc nhầm
cache dạng mảng của phiên bản cũ; generation key vẫn được dùng chung cho invalidation.
JWT và trạng thái tài khoản luôn được kiểm
tra trước khi đọc cache. Tạo/sửa tag thành công mới vô hiệu hóa các trang cache;
request thất bại giữ cache hiện tại. Cơ chế đổi mã phiên bản cache ngăn một
request đọc cũ đang chạy ghi đè dữ liệu vào phiên bản mới; trang cũ tự hết hạn.

Khi Redis mất kết nối, timeout hoặc JSON cache sai schema, API quay về đọc DB;
lỗi cache không làm thất bại thao tác tạo/sửa tag đã commit. Timeout kết nối/đọc
Redis là 0,2 giây mỗi thao tác, không retry. Nếu vô hiệu hóa cache thất bại hoặc
tag bị sửa trực tiếp trong DB, trang cũ có thể còn được đọc tới khi TTL hết hạn.
Client Redis được đóng khi ứng dụng dừng.

`tests/test_tag_cache.py` dùng `fakeredis` để kiểm tra cache hit/miss cùng trả
`Page`, phân trang và `total`, TTL, dữ liệu hỏng, bỏ qua cache mảng cũ,
invalidation, request đọc đang chạy, xác thực và Redis mất kết
nối. Bộ test không cần Redis thật và không dùng SMTP/Redis từ `.env`.

```bash
venv/bin/python3 -m pytest -q tests/test_background_tasks.py tests/test_tag_cache.py
```

## Bài 8: CORS, Logging và Docker triển khai

### Frontend gọi API qua CORS

Thiết lập các origin được phép trong `.env`, phân cách bằng dấu phẩy:

```dotenv
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,https://app.example.com
LOG_LEVEL=INFO
```

Origin gồm scheme, hostname và port, không có path hoặc dấu `/` cuối.
`localhost` và `127.0.0.1` là hai origin khác nhau. Mặc định cho phép hai origin
localhost ở trên; đặt `CORS_ORIGINS=` để không cho phép origin nào, không dùng `*`.
Sau khi đổi cấu hình cần khởi động lại API (với Docker: tạo lại container bằng
`docker compose up -d app`). CORS cho phép các phương thức API và hai header
`Authorization`, `Content-Type`. Frontend dùng Bearer token:

```javascript
const response = await fetch("http://localhost:8000/api/projects", {
  headers: { Authorization: `Bearer ${token}` },
});
console.log(response.headers.get("X-Request-ID"));
const page = await response.json();
const projects = page.items;
const hasNext = page.offset + projects.length < page.total;
```

Không cần `credentials: "include"` vì API không dùng cookie để xác thực.
CORS không thay thế JWT hoặc phân quyền. Preflight hợp lệ không cần đăng nhập;
request dữ liệu vẫn phải có token. `CORSMiddleware` bọc toàn bộ FastAPI để cả
response lỗi 500 cũng có CORS header cho origin được phép, theo hướng dẫn
[Starlette về CORS toàn cục](https://www.starlette.io/middleware/#corsmiddleware-global-enforcement).
`main:app` vẫn là entrypoint Uvicorn; đối tượng FastAPI bên trong là `main.api`
khi cần đăng ký route hoặc thay dependency trong test.

### Theo dõi lỗi và request

Log API xuất mỗi dòng một JSON ra stdout, có thời gian UTC, mức log, tên logger
và message. Access log thêm method, mẫu route (ví dụ `/api/tasks/{task_id}`),
status, thời gian xử lý `duration_ms` và `request_id`. Thời gian này bao gồm cả
background task chạy trong tiến trình. API tạo ID riêng cho từng request và
trả qua `X-Request-ID`; frontend được phép đọc header này qua CORS.

Lỗi chưa được xử lý ghi ở mức ERROR, kèm loại exception và vị trí các frame
trong traceback (file, dòng, hàm). Response 500 giữ thông báo chung. Formatter
không ghi exception message hoặc biến local vì chúng có thể chứa tham số SQL
hay mật khẩu. Access log không ghi body, query string, header Authorization
hoặc giá trị tham số URL. Khi viết log mới, cũng không đưa dữ liệu nhạy cảm vào
message. Access log mặc định của Uvicorn được tắt để tránh ghi raw URL trùng lặp.

```bash
docker compose logs -f --tail=100 app
docker compose logs --tail=100 migrate db
```

`LOG_LEVEL` nhận `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Chọn INFO để xem
request thông thường. Docker giới hạn log của app/migrate ở 10 MB mỗi file,
giữ tối đa 3 file. Log migration dùng cấu hình Alembic hiện có trên stderr.

### Chạy App + PostgreSQL bằng Docker

Yêu cầu Docker Engine và Docker Compose v2 trở lên. Không cần Python/venv trên
máy host để chạy stack. Nếu setup mới, sao chép `.env.example` thành `.env`;
giữ `.env` hiện có nếu đã cấu hình. Đặt `POSTGRES_PASSWORD` riêng và tạo
`JWT_SECRET_KEY` ngẫu nhiên tối thiểu 32 byte. Có thể tạo khóa bằng Docker:

```bash
docker run --rm python:3.15.0-slim-bookworm python -c 'import secrets; print(secrets.token_hex(32))'
```

Chép kết quả vào `.env`, cấu hình `CORS_ORIGINS` đúng địa chỉ frontend, rồi chạy:

```bash
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps -a
curl http://127.0.0.1:8000/health
```

Swagger: <http://127.0.0.1:8000/docs>. Nếu đang chạy `make dev`, dừng API local
trước hoặc đặt `APP_PORT=8001` trong `.env` để tránh trùng cổng.

Trình tự khởi động: PostgreSQL báo healthy → service `migrate` chạy
`alembic upgrade head` thành công → service `app` khởi động Uvicorn. Job migrate
thoát với mã 0 là bình thường; nếu migration thất bại, app mới không khởi động.
Compose dùng [điều kiện depends_on](https://docs.docker.com/compose/how-tos/startup-order/)
để kiểm soát thứ tự này. `/health` là liveness của tiến trình API, không phải
kiểm tra kết nối database hay Redis.

App trong container nối tới `db:5432`, lấy user/password/database từ các biến
`POSTGRES_*`. Compose đặt `DATABASE_HOST=db`; khi biến này có giá trị, cấu hình
ghép URL bằng SQLAlchemy và bỏ qua `DATABASE_URL` local. Vì vậy không phải đổi
`localhost` trong `.env` khi chuyển giữa Docker và `make dev`. Mật khẩu có ký tự
đặc biệt cũng được mã hóa đúng trong URL. `POSTGRES_PORT` chỉ là cổng trên host.
Không đặt `DATABASE_HOST` trong `.env` khi chạy local với `make dev`.

Image dùng Python 3.15.0, chỉ cài dependencies runtime, chạy bằng user `taskhub`
(UID 10001), không dùng `--reload` và không bind-mount mã nguồn.
`.dockerignore` loại `.env`, Git, venv, cache và database cục bộ khỏi build context.
Secrets chỉ được truyền lúc chạy qua `.env`, không được đóng vào image.
PostgreSQL lưu dữ liệu ở volume `taskhub_postgres_data` như cấu hình cũ.

Mặc định app chỉ publish ở `127.0.0.1:8000`. Khi triển khai trên server, có thể
đặt reverse proxy HTTPS phía trước hoặc đặt `APP_BIND_HOST=0.0.0.0` để truy cập
trực tiếp qua cổng `APP_PORT`. PostgreSQL vẫn chỉ publish trên localhost.
Cấu hình này cung cấp stack chạy trên một máy; backup database, HTTPS/domain
và giám sát của môi trường thật cần được thiết lập trên server triển khai.

Redis vẫn tùy chọn. Để bật cho app trong Docker, đặt
`DOCKER_REDIS_URL=redis://redis:6379/0` trong `.env`, rồi chạy:

```bash
docker compose --profile cache up -d --build --wait
```

`REDIS_URL` dùng cho API chạy local; Docker dùng `DOCKER_REDIS_URL` để tránh nối
nhầm tới localhost của container. Khi Redis chưa sẵn sàng, API quay về đọc DB.

Khi cập nhật phiên bản có migration, thực hiện trong thời gian bảo trì:

```bash
docker compose build
docker compose stop app
docker compose run --rm migrate
# Chỉ chạy tiếp nếu migration thành công:
docker compose up -d --wait
```

Dừng stack bằng `docker compose down`; volume database được giữ lại.
Không thêm `-v` nếu muốn giữ dữ liệu. Luồng `make dev` vẫn chỉ bật service `db`,
chạy migration và API local như trước.

Test CORS kiểm tra preflight, origin bị từ chối và JWT vẫn bắt buộc. Test log
kiểm tra request ID, lỗi 500 có CORS, thông tin trace và loại bỏ dữ liệu nhạy cảm:

```bash
venv/bin/python3 -m pytest -q tests/test_deployment.py
venv/bin/python3 -m pytest -q
```

## Final Review — 19/10/2026

Đã rà soát mã nguồn, chạy toàn bộ **172 test**, gồm SMTP thật tới Mailpit, và
**74 kiểm tra HTTP** của đợt review ban đầu trên stack
Docker riêng với PostgreSQL và Redis thật. Stack review dùng credentials, cổng
và volume tạm; đã dọn sau kiểm tra, không sử dụng database đang phát triển.
Đợt kiểm tra bổ sung chạy luồng cập nhật trạng thái → email SMTP → xóa task
trên PostgreSQL/Mailpit trong Docker, gồm hai request cập nhật cùng trạng thái
đồng thời (cả hai trả 200), hai request xóa đồng thời (204/404), và kiểm tra
cascade comment/bookmark/liên kết tag trong database.

| Luồng | Kết quả |
| --- | --- |
| Build → DB healthy → migration → API healthy | Đạt; `alembic check` khớp schema PostgreSQL |
| Đăng ký → đăng nhập → `/me`; username/email trùng, mật khẩu sai | Đạt; dữ liệu trả về không chứa password/hash |
| USER/Admin/chủ project; tài khoản bị khóa; chuyển chủ project | Đạt; quyền được đọc lại từ DB dù JWT chưa hết hạn |
| Project → tag → task; quan hệ, UTC, filter, phân trang | Đạt trên PostgreSQL |
| Giao task → comment → sửa/xóa theo quyền → bookmark lặp | Đạt; bookmark không tạo bản ghi trùng |
| CORS preflight, origin lạ, JWT bắt buộc, request ID | Đạt; cả lỗi 500 có CORS cho origin hợp lệ |
| Redis cache, JSON hỏng, invalidation, Redis dừng/phục hồi | Đạt; cache lỗi quay về DB |
| DB dừng/phục hồi, log lỗi, restart API | Đạt; 500 không lộ chi tiết DB, log có trace/request ID, dữ liệu còn nguyên |
| Email nền | Đạt: SMTP thật tới Mailpit, xác minh người nhận/nội dung; lỗi kết nối không mất comment |
| Vòng đời task | PATCH theo trạng thái và quyền, DELETE cascade, rollback khi lỗi đều có test |
| JWT lệch giờ | Test lùi 2 giây và biên dung sai đạt; hết hạn/nbf vẫn kiểm tra nghiêm ngặt |

**Lỗi đã sửa trong review:** cả `POST /api/tasks` và
`POST /api/projects/{project_id}/tasks` từng cho phép tạo task giao cho user bị
khóa, trong khi endpoint `/assign` từ chối. Hai đường tạo task giờ trả 409 và
không lưu dữ liệu; đã thêm hai regression test tái hiện lỗi trước khi sửa.

**Giới hạn còn lại:** chưa có API xóa User/Project/Tag; project/task vẫn được đọc chung bởi
các tài khoản đang hoạt động. Đây là phạm vi ứng dụng học tập hiện có, chưa phải
quy trình quản lý task đầy đủ cho nhiều nhóm riêng tư. Chưa có refresh token/thu hồi
token và chưa kiểm thử tải lớn.
`/health` vẫn chỉ là liveness; khi DB dừng, endpoint
này vẫn trả 200. TLS/domain và backup trên server thật chưa được kiểm chứng.

Đã tái hiện và xử lý JWT bị từ chối khi đồng hồ lùi nhỏ bằng regression test;
chưa có đủ log để kết luận đây chắc chắn là nguyên nhân của các lượt lỗi cũ.
Log độ lệch mới giúp chẩn đoán nếu lỗi tiếp diễn. TestClient còn cảnh báo
deprecation từ Starlette về HTTPX, không làm test thất bại.

## 9. Advance

### 9.1 Heavy Background Jobs & Cron Jobs

`BackgroundTasks` chạy trong tiến trình API: không có queue bền vững, retry hay
lịch chạy định kỳ. Luồng mới dùng **Celery + Redis + Celery Beat** để export Excel
và gửi email nhắc việc. Worker chạy độc lập, không giữ session của HTTP request.
Email thông báo comment ở phần học trước vẫn dùng `BackgroundTasks`, nên vẫn có
giới hạn mất thông báo khi API sập; cơ chế bền vững dưới đây áp dụng cho job mới.

#### Chạy bằng Docker

```bash
docker compose --profile jobs up -d --build
docker compose --profile jobs logs -f worker worker-maintenance beat
```

Profile `jobs` bật Redis, worker queue `heavy` (export), worker queue
`maintenance` (email và điều phối) và Beat. App/migration dùng chung image với
worker; migration `0005` tạo bảng `jobs`. Queue ngắn có worker riêng để export
không chặn lịch và email. Chỉ chạy **một Beat** cho mỗi lịch. Có thể tăng số worker,
nhưng không tăng số Beat. `/health` vẫn chỉ là liveness của API.

Redis bật AOF `everysec`, volume riêng và `noeviction`; không dùng Redis này làm
cache có eviction hoặc chạy `FLUSHALL`. Broker dùng DB 1, result backend DB 2,
cache tùy chọn dùng DB 0. Các Redis DB logic vẫn chia sẻ RAM và tiến trình.
Khi triển khai lớn, tách Redis cache khỏi Redis queue.

Local: cài lại `requirements-dev.txt`, chạy migration, bật Redis rồi chạy ba
terminal dưới đây cùng với `make dev`:

```bash
docker compose --profile jobs up -d --wait redis
venv/bin/python -m celery -A celery_app:celery_app worker -Q heavy --concurrency=2 -l INFO
venv/bin/python -m celery -A celery_app:celery_app worker -Q maintenance --concurrency=1 -l INFO
venv/bin/python -m celery -A celery_app:celery_app beat -l INFO --schedule=/tmp/taskhub-celerybeat-schedule
```

Local dùng `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`; container dùng
`DOCKER_CELERY_BROKER_URL`/`DOCKER_CELERY_RESULT_BACKEND` (mặc định hostname
`redis`). Không chạy đồng thời Beat local và Beat Docker với cùng broker.
Khi nâng cấp schema, dừng cả API, hai worker và Beat trước migration rồi khởi
động lại cùng phiên bản. Volume DB, Redis và lịch Beat được giữ khi `down`;
không dùng `down -v` nếu cần giữ dữ liệu.

#### Export Excel qua queue

Đăng nhập rồi gửi JWT của **chủ project hoặc admin**:

```http
POST /api/jobs/exports
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "project_id": "<project UUID>",
  "idempotency_key": "project-report-2026-10-20-v1"
}
```

API trả **202** với `id`, `status`, `attempts`, `updated_at`, `error_code`.
Gửi lại cùng key và payload trả cùng job; đổi payload nhưng giữ key trả **409**.
Key có scope theo người tạo và loại job, tối đa 128 ký tự
`A-Z a-z 0-9 _ . : -`. Muốn tạo báo cáo mới, dùng key mới.

| Endpoint | Ý nghĩa |
| --- | --- |
| `POST /api/jobs/exports` | Lưu job rồi đưa `job_id` vào queue |
| `GET /api/jobs/{job_id}` | Xem trạng thái job của mình |
| `GET /api/jobs/{job_id}/download` | Tải `.xlsx` khi `succeeded`; chưa sẵn sàng trả 409 |

Người khác nhận 404 khi truy cập job. Quyền quản lý project được kiểm tra lại
khi worker bắt đầu và khi tải, nên chuyển chủ project không để lại quyền tải cũ.
Báo cáo chứa tối đa 100.000 task của project, gồm ID, title, status, priority,
due date, assignee ID. Vượt giới hạn trả job `failed`, không trả file bị cắt.
Nội dung người dùng được ghi dưới dạng text, tránh Excel diễn giải thành formula.
Dữ liệu được đọc khi worker chạy, không phải snapshot tại thời điểm POST.

#### Idempotency, retry và phục hồi

1. API commit bản ghi `jobs` trước khi publish. Unique constraint
   `(owner_id, kind, idempotency_key)` phân xử cả các request đồng thời.
2. Worker nhận duy nhất `job_id`, mở session riêng, khóa row bằng PostgreSQL
   `FOR UPDATE SKIP LOCKED` và kiểm tra trạng thái. Job đã hoàn tất không chạy lại.
3. Export ghi file và trạng thái thành công **trong cùng transaction**. Worker
   sập trước commit thì transaction rollback; sập sau commit thì lần nhận lại
   chỉ trả trạng thái cũ. File nằm trong DB để API và worker không phụ thuộc
   filesystem chung.
4. Lỗi export có thể retry tối đa 5 lần thực thi, backoff 60/120/240/480 giây.
   Lỗi quyền hoặc giới hạn dữ liệu kết thúc ngay. Lỗi kết nối DB được Celery
   retry riêng; nếu DB không thể ghi trạng thái, bộ quét vẫn có thể thử lại sau
   khi DB phục hồi.
5. Beat quét tối đa 100 job chờ mỗi 30 giây. Publish lỗi giữ nguyên job; publish
   thành công nhưng không có kết quả sau 5 phút thì có thể publish lại.
   Lock và trạng thái DB chống tác dụng trùng; Celery `task_id` một mình không
   loại trùng. Nếu cả Beat dừng thì job còn trong DB, chờ Beat khởi động lại.

Celery bật `acks_late`, `task_reject_on_worker_lost`, prefetch 1 và JSON serializer.
Giới hạn task cứng 30 phút, visibility timeout Redis 60 phút. Redis result
backend giữ kết quả nhỏ trong 24 giờ; API dùng trạng thái trong DB làm nguồn
chính. AOF `everysec` vẫn có cửa sổ mất dữ liệu gần nhất khi máy sập; bản ghi job
trong PostgreSQL cho phép phục hồi publication của các job còn chờ.

#### Nhắc việc hằng ngày lúc 08:00

Beat dùng `crontab(hour=8, minute=0)` với `CELERY_TIMEZONE=Asia/Ho_Chi_Minh`.
Bật `EMAIL_ENABLED=true` và cấu hình SMTP như phần email. Mỗi user đang hoạt động
có task chưa DONE, đã quá hạn hoặc đến hạn trong ngày sẽ có một job với key
`daily:YYYY-MM-DD`. Chạy scheduler lặp trong cùng ngày không tạo job trùng.
Worker kiểm tra lại user/task, gửi một email tổng hợp tối đa 100 task; không còn
việc phù hợp hoặc email bị tắt thì chuyển `skipped`.

**SMTP không cung cấp exactly-once:** DB không thể commit nguyên tử cùng máy chủ
email. Worker commit trạng thái `sending` trước SMTP. Khi timeout hoặc lỗi gửi,
job chuyển `uncertain`; nếu worker chết, bộ quét chuyển `sending` quá 10 phút
sang `uncertain`. Các trạng thái này **không tự gửi lại**. Cách này tránh gửi hai
lần do retry nhưng có thể bỏ lỡ email nếu crash xảy ra trước khi SMTP nhận.
Kiểm tra log/provider trước khi quyết định gửi bù. Muốn vừa retry tự động vừa
chống trùng ở nhà cung cấp, cần dịch vụ email có hỗ trợ idempotency key; SMTP
`Message-ID` không đảm bảo điều đó.

Beat là scheduler, không phải lịch sử chạy bù: bản triển khai này không đảm bảo
nhắc lại từng ngày đã bỏ lỡ nếu toàn bộ scheduler/broker ngừng nhiều ngày.
Chưa thêm nén video vì TaskHub chưa có luồng upload/media; khi thêm, đưa vào
queue `heavy`, dùng `job_id` và object storage, publish artifact nguyên tử.
File Excel hiện lưu trong DB và chưa có retention tự động; cần chính sách dọn
artifact và giữ key đủ lâu trước khi dùng cho dữ liệu lớn.

Kiểm thử:

```bash
venv/bin/python -m pytest -q tests/test_jobs.py
venv/bin/python -m pytest -q
```

Test cover replay, unique constraint, quyền, formula injection, publish outage,
outbox recovery, retry, rollback khi worker crash, lịch theo timezone và SMTP
không gửi lại khi kết quả không xác định. SQLite không có row lock như
PostgreSQL; kiểm thử chạy đồng thời thực tế cần PostgreSQL và worker riêng.

Kiểm chứng ngày 20/10/2026: **184 test đạt, 1 test SMTP tùy chọn bỏ qua**.
Đã kiểm tra riêng trên stack Docker tạm với PostgreSQL, Redis, worker prefork,
Beat và Mailpit: 16 lần tạo job đồng thời cùng key chỉ sinh một row, hai lần
thực thi đồng thời chỉ export một lần, API → queue → tải Excel thành công,
gọi lịch nhắc việc hai lần vẫn chỉ có một email SMTP. `alembic check` khớp schema
PostgreSQL. Stack này dùng dữ liệu/volume riêng, không dùng DB phát triển.

Tham khảo chính thức:
[Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html),
[Periodic Tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html),
[Celery với Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html),
[Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

## Migration và kiểm thử

Schema chỉ được tạo bằng Alembic, không tự `create_all()` khi khởi động API.
Sau khi thay đổi model:

```bash
make migration m="describe model change"
# Đọc và kiểm tra file migration vừa sinh trước khi áp dụng.
alembic upgrade head
alembic check
python3 -m pytest -q
```

`make migration` dùng Python trong `venv` và yêu cầu mô tả qua `m="..."`.
Lệnh chỉ sinh file migration, chưa áp dụng thay đổi vào database.

Test tự tạo SQLite tạm, chạy migration thật, bật khóa ngoại và không sử dụng DB
trong `.env`. SQLite không bảo toàn timezone như PostgreSQL. Migration có
`downgrade()`; chỉ dùng rollback schema trên DB phù hợp vì có thể mất dữ liệu.

Project dùng FastAPI 0.143.0, HTTPX 0.28+ và pytest 9 để chạy trên Python 3.15.

## Tài liệu

- [FastAPI Request Body](https://fastapi.tiangolo.com/tutorial/body/)
- [FastAPI First Steps](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [FastAPI SQL Databases](https://fastapi.tiangolo.com/tutorial/sql-databases/)
  (tutorial hiện dùng SQLModel; project này dùng SQLAlchemy trực tiếp theo đề).
- [SQLAlchemy ORM Quick Start](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
