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
database.py             # Engine, Base, SessionLocal, get_db
routers/                # HTTP, validation tham số, mã lỗi
schemas/                # Pydantic: dữ liệu đầu vào và response
crud/                   # Truy vấn ORM và commit/rollback
services/               # Nghiệp vụ, transaction, email nền và cache tag
models/                 # User, Project, Task, Comment, Tag, Bookmark
alembic/versions/       # Lịch sử migration
tests/                  # API, quan hệ và ràng buộc database
compose.yaml            # PostgreSQL; Redis tùy chọn qua profile cache
Makefile                # make dev: bật DB, migrate, chạy API
```

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
| GET | `/api/users/{user_id}` | Xem user |
| GET | `/api/users/{username}/profile` | Profile kèm projects, tasks và task được giao |
| POST / GET | `/api/projects` | Tạo / liệt kê project |
| GET | `/api/projects/{project_id}` | Xem project |
| PATCH | `/api/projects/{project_id}` | Cập nhật một phần project |
| GET / POST | `/api/projects/{project_id}/tasks` | Liệt kê / tạo task trong project, kèm assignee và tags |
| POST / GET | `/api/tags` | Tạo / liệt kê tag |
| PATCH | `/api/tags/{tag_id}` | Cập nhật tên tag |
| POST / GET | `/api/tasks` | Tạo / liệt kê task |
| GET | `/api/tasks/{task_id}` | Xem task |
| POST | `/api/tasks/{task_id}/bookmark` | Bookmark task cho user đang đăng nhập |
| POST | `/api/tasks/{task_id}/assign` | Giao lại task cho user (PM/Admin) |
| POST | `/api/tasks/{task_id}/comments` | Thêm comment với tác giả từ JWT |
| PATCH / DELETE | `/api/tasks/{task_id}/comments/{comment_id}` | Sửa / xóa comment (tác giả hoặc PM/Admin) |

Các API danh sách task nhận `skip` (mặc định 0), `limit` (mặc định 20, tối đa 100),
và vẫn hỗ trợ `offset` cũ. Danh sách User/Project/Tag dùng `offset` và `limit`.
Task có bộ lọc `project_id`, `status` (`TODO`, `IN_PROGRESS`, `DONE`) và
`priority` (`LOW`, `MEDIUM`, `HIGH`); xem Bài 5 bên dưới.

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

`assignee_id` và `due_date` có thể bỏ qua. Nếu gửi `due_date`, phải kèm múi giờ.
Priority nằm trong khoảng 1–5. API trả 201 khi tạo thành công, 404 khi không tìm
thấy tài nguyên, 409 khi xung đột và 422 khi dữ liệu không hợp lệ.

Phạm vi hiện tại: xác thực JWT, phân quyền admin/chủ project, tạo/xem User,
Project, Task, Tag, bookmark/giao lại task, thêm/sửa/xóa comment, cập nhật
Project/Tag và tài khoản hiện tại.
Các API đọc project/task vẫn dùng chung cho tài khoản đang hoạt động;
chưa có mô hình project riêng tư hoặc thành viên project. Chưa triển khai API
xóa User/Project/Task/Tag. Các đường dẫn `/tasks/...` cũ vẫn là ví dụ mock công khai,
nằm trong `routers/examples.py`.

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
Ví dụ `GET /api/tags`: `routers/tags.py` → `crud/tags.py` → `models/tag.py`
→ `TagRead`. Lỗi validation trả 422 trước khi chạy thân hàm endpoint.

Chạy `make dev`, mở <http://127.0.0.1:8000/docs>, chọn endpoint rồi bấm
**Try it out** → nhập tham số/body → **Execute**:

1. Tạo User và Project theo ví dụ phía trên. Gọi `GET /api/projects`, sau đó
   sao chép `id` vào `GET /api/projects/{project_id}` để xem chi tiết.
2. Gọi `PATCH /api/projects/{project_id}` với `{"description": "Bài thực hành CRUD"}`.
   Gọi GET chi tiết để xác nhận tên và owner vẫn giữ nguyên. Thử tiếp
   `{"description": null}` để xóa mô tả.
3. Gọi `POST /api/tags` với `{"name": "backend"}`. Sao chép `id` trả về và
   gọi `PATCH /api/tags/{tag_id}` với `{"name": "frontend"}`.
4. Gọi `GET /api/tags` với `offset=0`, `limit=20` để xem kết quả. Khi chưa tạo
   tag nào, danh sách trả `[]`.
5. Thử tên rỗng hoặc UUID sai định dạng (422), UUID hợp lệ nhưng không tồn tại
   khi xem/sửa project hoặc sửa tag (404), và tạo/sửa tag trùng tên (409).

Các schema gắn vào endpoint hiển thị trong mục **Schemas** của Swagger UI.
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

Trong Swagger, tạo user, project và tag, rồi gọi
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
tại trả 404, project chưa có task trả `[]`.

Gọi `GET /api/users/huy/profile` để xem `UserProfile`: thông tin user,
`projects` (mỗi project chứa `tasks`) và `assigned_tasks`. Mỗi task chứa
assignee và tags, nhưng không lồng ngược lại profile để tránh vòng tham chiếu.
`projects` chỉ gồm project user sở hữu; `assigned_tasks` có thể thuộc project
người khác. Endpoint profile trả toàn bộ các collection này, chưa phân trang;
với dữ liệu lớn nên dùng endpoint danh sách task theo project.

Trong `crud/tasks.py`, eager loading được khai báo bằng:

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

Profile dùng `selectinload` cho các collection `User.projects`, `Project.tasks`
và `User.assigned_tasks`, kết hợp `joinedload` assignee/tags của task. Cách này
tránh nhân chéo số hàng giữa projects và assigned_tasks khi JOIN tất cả cùng lúc.
Tham khảo [SQLAlchemy Relationship Loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html).

Test truy vấn thay dependency xác thực bằng user giả để đo riêng nghiệp vụ,
kể cả serialize response: với bộ dữ liệu
1 và 12 phần tử, danh sách task theo project đều dùng **2 SELECT** (kiểm tra project
+ tải tasks/assignee/tags), profile dùng **4 SELECT**. Với collection lớn hơn,
`selectinload` có thể chia thành nhiều batch; số query tăng theo batch thay vì từng
task. Khi dùng JWT thật, thêm một SELECT để lấy current user. Test cũng kiểm tra
phân trang không mất tag hoặc lặp task.

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
`/docs`, `/openapi.json`, `/health` và mock examples vẫn công khai. Router auth
được đăng ký trước router user để `/me` không bị hiểu là `/{user_id}`.

Thử bằng Swagger: đăng ký → **Authorize** → gọi `/me` → PUT đổi tên → GET kiểm tra.
Bấm **Logout** trong Authorize rồi gọi API dữ liệu để thấy 401. Token hết hạn thì
đăng nhập lại; bài này chưa có refresh token, thu hồi token hoặc đổi/reset mật khẩu.
Logout ở Swagger chỉ xóa token khỏi giao diện, không thu hồi token đã phát hành.

Các test auth dùng JWT và dependency thật, kiểm tra toàn bộ route được bảo vệ,
token sai chữ ký/thuật toán/hết hạn/thiếu claim, không lộ hash, cập nhật đúng user,
rollback khi trùng username/email và một luồng tạo project/tag/task đã đăng nhập.
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
  hoặc xem danh sách bằng `GET /api/users`. `/register` vẫn công khai.
- `verify_project_manager`: chủ sở hữu (`project.owner_id`) hoặc admin được
  sửa project và tạo task qua cả hai đường dẫn `/api/tasks` và
  `/api/projects/{project_id}/tasks`. User thường chỉ tạo project cho chính mình.
  Chủ project được chuyển quyền sở hữu; quyền quản lý chuyển sang chủ mới ngay.

Role và trạng thái hoạt động được đọc từ DB ở mỗi request. Các body đăng ký,
tạo hồ sơ và sửa `/me` không cho phép truyền `role` hay `is_active`. Để thực hành
admin, người vận hành có thể cập nhật tài khoản đã đăng ký trong PostgreSQL:

```sql
UPDATE users SET role = 'ADMIN' WHERE username = 'huy';
```

Thiếu JWT hoặc JWT không hợp lệ trả 401; thiếu quyền hoặc tài khoản bị khóa trả
403; tài nguyên không tồn tại trả 404; query/body không hợp lệ trả 422.

### Lọc và phân trang trực tiếp bằng Query Parameters

Các hàm GET task khai báo trực tiếp `skip`, `limit`, `status`, `priority`.
Các bộ lọc kết hợp bằng AND, chạy trước phân trang. Dữ liệu được sắp xếp theo
`created_at`, rồi `id` để phân trang có thứ tự ổn định. Response vẫn là mảng task.

| Tham số | Giá trị |
| --- | --- |
| `skip` | Số task bỏ qua, mặc định 0, không âm |
| `limit` | Số task tối đa, mặc định 20, từ 1 đến 100 |
| `status` | `TODO`, `IN_PROGRESS`, `DONE`; bỏ qua để lấy mọi trạng thái |
| `priority` | `LOW` = 1–2, `MEDIUM` = 3, `HIGH` = 4–5 |
| `project_id` | UUID lọc project trên `GET /api/tasks` |
| `offset` | Tương thích API cũ; bị đánh dấu deprecated trong Swagger |

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
```

Bookmark không cần body: user được lấy từ JWT, task lấy từ path. Thành công trả
200 với `user_id`, `task_id`, `created_at`. Gọi lại trả bookmark đã lưu, không
tạo bản sao; hai user bookmark cùng task sẽ có hai bản ghi riêng. Mọi tài khoản
đang hoạt động đều được bookmark task, không yêu cầu quyền quản lý project.

Các test mới kiểm tra quyền bằng JWT thật, chặn tự nâng quyền, thu hồi quyền khi
đổi role/khóa tài khoản/chuyển chủ project, bookmark riêng từng user, xóa theo
khóa ngoại, bộ lọc kết hợp và phân trang sau khi lọc. Test migration kiểm tra
schema và dữ liệu cũ trên SQLite tạm; không sửa database trong `.env`.

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
transaction gây lỗi sau flush hoặc trước commit cho cả bốn nghiệp vụ, xác nhận
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

`GET /api/tags?offset=0&limit=20` cache JSON theo từng cặp `offset/limit`, kể cả
mảng rỗng, với TTL mặc định 60 giây. JWT và trạng thái tài khoản luôn được kiểm
tra trước khi đọc cache. Tạo/sửa tag thành công mới vô hiệu hóa các trang cache;
request thất bại giữ cache hiện tại. Cơ chế đổi mã phiên bản cache ngăn một
request đọc cũ đang chạy ghi đè dữ liệu vào phiên bản mới; trang cũ tự hết hạn.

Khi Redis mất kết nối, timeout hoặc JSON cache sai schema, API quay về đọc DB;
lỗi cache không làm thất bại thao tác tạo/sửa tag đã commit. Timeout kết nối/đọc
Redis là 0,2 giây mỗi thao tác, không retry. Nếu vô hiệu hóa cache thất bại hoặc
tag bị sửa trực tiếp trong DB, trang cũ có thể còn được đọc tới khi TTL hết hạn.
Client Redis được đóng khi ứng dụng dừng.

`tests/test_tag_cache.py` dùng `fakeredis` để kiểm tra cache hit/miss, phân trang,
TTL, dữ liệu hỏng, invalidation, request đọc đang chạy, xác thực và Redis mất kết
nối. Bộ test không cần Redis thật và không dùng SMTP/Redis từ `.env`.

```bash
venv/bin/python3 -m pytest -q tests/test_background_tasks.py tests/test_tag_cache.py
```

## Migration và kiểm thử

Schema chỉ được tạo bằng Alembic, không tự `create_all()` khi khởi động API.
Sau khi thay đổi model:

```bash
alembic revision --autogenerate -m "describe model change"
# Đọc và kiểm tra file migration vừa sinh trước khi áp dụng.
alembic upgrade head
alembic check
python3 -m pytest -q
```

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
