# Hướng dẫn viết API CRUD với FastAPI

Ví dụ: quản lý **Tag** trong TaskHub. CRUD là **tạo, đọc, sửa, xóa** dữ liệu.

> Đây là tài liệu hướng dẫn. Dự án hiện có tạo, liệt kê và sửa tag. GET chi tiết và DELETE tag bên dưới là phần có thể bổ sung, chưa được triển khai bởi tài liệu này.

## 1. Chốt yêu cầu

Trước khi viết code, xác định dữ liệu, quyền và lỗi cần xử lý.

- Tag có `id`, `name`, `created_at`.
- Tên dài 1–50 ký tự, không được trùng.
- User đang hoạt động được xem; chỉ admin được tạo, sửa, xóa.
- Danh sách phải phân trang.
- Xóa tag sẽ bỏ liên kết với task, không xóa task.

| Thao tác | Endpoint | Thành công |
| --- | --- | --- |
| Tạo | `POST /api/tags` | 201 |
| Danh sách | `GET /api/tags` | 200 |
| Chi tiết | `GET /api/tags/{tag_id}` | 200 |
| Sửa | `PATCH /api/tags/{tag_id}` | 200 |
| Xóa | `DELETE /api/tags/{tag_id}` | 204, không có body |

## 2. Hiểu vai trò từng lớp

```text
Client gửi request
    ↓
FastAPI tìm route, validate schema và kiểm tra quyền qua dependency
    ↓
Router gọi CRUD
    ↓
CRUD đọc/ghi database
    ↓
Router trả kết quả, response schema chọn trường được xuất
    ↓
Client nhận HTTP status và JSON
```

| File | Việc cần làm |
| --- | --- |
| `models/tag.py` | Khai báo bảng, cột và quan hệ |
| `schemas/tag.py` | Khai báo dữ liệu được gửi và được trả |
| `crud/tags.py` | Viết truy vấn database |
| `routers/tags.py` | Khai báo API, quyền và mã lỗi HTTP |
| `routers/dependencies.py` | Cung cấp session và kiểm tra người gọi |
| `main.py` | Đăng ký router vào ứng dụng |
| `tests/` | Kiểm tra API hoạt động đúng |

**Model là cách lưu dữ liệu. Schema là hợp đồng dữ liệu của API.**

## 3. Model và migration

Trong [models/tag.py](../models/tag.py), phần khai báo tên tag là:

```python
name: Mapped[str] = mapped_column(String(50), unique=True)
```

`unique=True` giúp database chặn tên trùng, kể cả khi hai request tạo cùng lúc. `EntityMixin` cung cấp `id` và `created_at`.

Chỉ khi tạo bảng hoặc đổi cấu trúc database mới cần migration:

```bash
make migration m="describe database change"
# Đọc và kiểm tra file migration trước khi chạy lệnh tiếp theo.
venv/bin/python -m alembic upgrade head
```

`make migration` dùng Python trong `venv` để tự sinh file migration; bắt buộc truyền mô tả qua `m="..."`. Lệnh này chưa áp dụng thay đổi vào database.

Bảng tag đã có trong dự án, không cần tạo lại. Thêm route hoặc đổi response schema không yêu cầu migration nếu cấu trúc DB không đổi.

## 4. Schema: kiểm tra đầu vào và giới hạn đầu ra

Trong [schemas/tag.py](../schemas/tag.py):

```python
class TagCreate(InputSchema):
    name: str = Field(min_length=1, max_length=50)


class TagRead(ReadSchema):
    name: str
```

- `TagCreate`: client phải gửi tên hợp lệ.
- `InputSchema`: bỏ khoảng trắng đầu/cuối và từ chối trường thừa.
- `TagRead`: trả `name` cùng `id`, `created_at` kế thừa từ `ReadSchema`.
- `TagUpdate` hiện có cho phép bỏ qua `name`, nhưng từ chối `name: null`.

Với PATCH:

| Body | Ý nghĩa |
| --- | --- |
| `{}` | Giữ nguyên |
| `{"name": "frontend"}` | Đổi tên |
| `{"name": null}` | Không hợp lệ, trả 422 |

## 5. CRUD: đọc và ghi database

Trong [crud/tags.py](../crud/tags.py), mỗi hàm làm một việc:

| Hàm | Công việc |
| --- | --- |
| `create()` | Tạo object Tag rồi lưu |
| `get()` | Tìm theo ID, không có thì trả `None` |
| `list_tags()` | Trả `(items, total)`: một trang danh sách và tổng số tag |
| `update()` | Sửa những trường client gửi |
| `delete()` — cần bổ sung | Xóa bản ghi rồi commit |

Ví dụ tạo:

```python
def create(db: Session, data: TagCreate) -> Tag:
    tag = Tag(**data.model_dump())
    return save(db, tag)
```

`model_dump()` đổi schema thành dictionary. Hàm `save()` trong dự án thực hiện:

```text
add → commit → refresh → trả object
          ↓ nếu vi phạm ràng buộc DB
       rollback → chuyển lỗi lên router
```

- `commit`: lưu thay đổi.
- `rollback`: hủy transaction đang lỗi.
- `refresh`: đọc lại dữ liệu từ DB.

Khi cập nhật, dùng:

```python
changes = data.model_dump(exclude_unset=True)
```

Để body `{}` tạo ra dictionary rỗng, không vô tình ghi đè trường bị bỏ qua.

Khi lấy danh sách, phân trang ngay trong SQL:

```python
from crud.pagination import paginate

statement = select(Tag).order_by(Tag.created_at, Tag.id)
return paginate(db, statement, offset, limit)
```

`offset=20&limit=20` nghĩa là bỏ 20 bản ghi đầu và lấy tối đa 20 bản ghi tiếp theo. Không tải toàn bộ rồi cắt list bằng Python.

Helper `paginate()` đếm tổng trước khi áp dụng offset/limit. Service cache tag
chuyển kết quả thành `Page[TagRead]` gồm `items`, `total`, `offset`, `limit` và
cache toàn bộ object này. Trang không có phần tử vẫn giữ đúng tổng số tag.

## 6. Router: nối request với CRUD

Ví dụ từ [routers/tags.py](../routers/tags.py):

```python
import error_messages as errors

@router.post("", response_model=TagRead, status_code=201)
def create_tag(data: TagCreate, db: DBSession, current_user: AdminUser):
    try:
        tag = tags.create(db, data)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=errors.TAG_NAME_EXISTS,
        ) from None

    tag_cache.invalidate()
    return tag
```

- `TagCreate`: kiểm tra body.
- `DBSession`: cung cấp kết nối làm việc với DB qua session.
- `AdminUser`: kiểm tra quyền admin trước khi chạy thân hàm.
- `response_model`: chỉ xuất những trường được phép.
- `IntegrityError → 409`: chuyển lỗi DB thành lỗi HTTP dễ hiểu.
- `tag_cache.invalidate()`: vô hiệu hóa cache sau khi ghi thành công.

Luồng các thao tác còn lại:

```text
GET chi tiết: tìm tag → không có trả 404 → có thì trả 200
GET danh sách: kiểm tra offset/limit → đọc cache hoặc DB → trả Page (items, total, offset, limit)
PATCH: tìm tag → không có trả 404 → cập nhật → làm mới cache → trả 200
DELETE: tìm tag → không có trả 404 → xóa, commit → làm mới cache → trả 204
```

## 7. Đăng ký route và quản lý session

`main.py` đã đăng ký router tag với `get_current_active_user`, nên mọi API tag cần tài khoản đang hoạt động. POST/PATCH và DELETE nếu bổ sung dùng thêm `AdminUser`.

`get_db()` mở session cho request và đóng khi xử lý xong. Đóng session không tự lưu dữ liệu; muốn lưu phải commit.

Với một tài nguyên mới, nhớ import và đăng ký router trong `main.py`, nếu không endpoint sẽ chưa xuất hiện trong ứng dụng.

## 8. Test trước khi hoàn tất

Luồng kiểm tra đầy đủ sau khi có cả GET chi tiết và DELETE:

```text
Tạo tag → xem lại → đổi tên → xem lại → xóa → xem lại nhận 404
```

Test thêm các trường hợp lỗi:

| Trường hợp | Kết quả |
| --- | --- |
| Tên rỗng/quá dài hoặc body có trường thừa | 422 |
| Tên trùng | 409 |
| ID không tồn tại | 404 |
| Thiếu token hoặc token sai | 401 |
| User thường gọi thao tác ghi | 403, dữ liệu không đổi |
| Danh sách rỗng | 200 với `[]` |
| Xóa tag có liên kết task | Tag/liên kết mất, task vẫn tồn tại |

Test HTTP với database là **test tích hợp API**. Unit test có thể kiểm tra riêng schema, ví dụ tên rỗng bị từ chối.

Trong dự án, fixture `client` giả lập admin. Kiểm tra quyền user thường phải dùng `anonymous_client` và JWT thật.

Chạy các test hiện có liên quan đến tag:

```bash
venv/bin/python -m pytest tests/test_api.py tests/test_permissions.py tests/test_tag_cache.py -q
git diff --check
```

## 9. Hoàn tất công việc

1. Kiểm tra test đạt.
2. Cập nhật README: endpoint, quyền, body, response và lỗi.
3. Xem lại `git diff` để biết chính xác thay đổi.
4. Commit, push nhánh và tạo PR.

**Thứ tự thực hiện:** yêu cầu → model → migration nếu cần → schema → CRUD → router/quyền → đăng ký router → test → README → commit.
