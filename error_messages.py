"""Application error messages shared by API, validation, configuration and workers.

Keep this module free of application imports so it is safe to use at startup.
HTTP status codes and exception types belong to the calling code.
"""

# Authentication and authorization.
INVALID_CREDENTIALS = "Could not validate credentials"
INCORRECT_USERNAME_OR_PASSWORD = "Incorrect username or password"
INACTIVE_USER = "Inactive user"
ADMIN_ROLE_REQUIRED = "Admin role required"
PROJECT_MANAGER_REQUIRED = "Project manager permission required"
COMMENT_AUTHOR_OR_PROJECT_MANAGER_REQUIRED = "Comment author or project manager permission required"
PROJECT_MANAGER_EDIT_REQUIRED = "Only the project manager can edit task details"
CANNOT_CREATE_PROJECT_FOR_ANOTHER_USER = "Cannot create a project for another user"

# Resources and conflicts.
USER_NOT_FOUND = "User not found"
PROJECT_NOT_FOUND = "Project not found"
TASK_NOT_FOUND = "Task not found"
TAG_NOT_FOUND = "Tag not found"
COMMENT_NOT_FOUND = "Comment not found"
OWNER_NOT_FOUND = "Owner not found"
ASSIGNEE_NOT_FOUND = "Assignee not found"
JOB_NOT_FOUND = "Job not found"
OWNER_INACTIVE = "Owner is inactive"
ASSIGNEE_INACTIVE = "Assignee is inactive"
EMAIL_OR_USERNAME_EXISTS = "Email or username already exists"
TAG_NAME_EXISTS = "Tag name already exists"
PROJECT_REFERENCES_CHANGED = "Project references changed; retry the request"
TASK_REFERENCES_CHANGED = "Task references changed; retry the request"
BOOKMARK_REFERENCES_CHANGED = "Bookmark references changed; retry the request"
JOB_REFERENCES_CHANGED = "Job references changed; retry the request"
TASK_DATA_CHANGED = "Task data changed; retry the request"
INVALID_TASK_STATUS_TRANSITION = "Task status must follow TODO -> IN_PROGRESS -> DONE"
IDEMPOTENCY_KEY_CONFLICT = "Idempotency key already used with another payload"
EXPORT_NOT_READY = "Export is not ready"

# Input validation.
PAGINATION_OFFSETS_MISMATCH = "skip and offset must match when both are provided"
FIELD_CANNOT_BE_NULL = "Field cannot be null"
TAG_NAME_CANNOT_BE_NULL = "name cannot be null"
PASSWORD_TOO_MANY_BYTES = "Password must not exceed 72 UTF-8 bytes"
DUE_DATE_IN_PAST = "due_date must not be in the past"
JWT_IAT_NOT_INTEGER = "Issued At claim (iat) must be an integer."
JWT_IAT_IN_FUTURE = "The token is not yet valid (iat)"

# Configuration errors. Templates accept named values only.
DATABASE_URL_REQUIRED = "Set DATABASE_URL in .env (see .env.example)."
INVALID_DATABASE_POOL_SETTINGS = "Invalid database pool settings."
INVALID_JWT_IAT_LEEWAY = "JWT_IAT_LEEWAY_SECONDS must be between 0 and 30."
INVALID_ACCESS_TOKEN_EXPIRY = "ACCESS_TOKEN_EXPIRE_MINUTES must be positive."
INVALID_CORS_ORIGINS = "CORS_ORIGINS must list explicit frontend origins, not *."
INVALID_LOG_LEVEL = "Invalid LOG_LEVEL."
INVALID_BOOLEAN_ENV = "{name} must be true/false or 1/0."
INVALID_SMTP_SENDER = "Email requires SMTP_HOST and a valid SMTP_FROM."
CONFLICTING_SMTP_TLS_OPTIONS = "Use either SMTP_USE_TLS (STARTTLS) or SMTP_USE_SSL, not both."
INVALID_SMTP_PORT_OR_TIMEOUT = "Invalid SMTP port or timeout."
INCOMPLETE_SMTP_CREDENTIALS = "Set both SMTP_USERNAME and SMTP_PASSWORD, or neither."
INVALID_TAG_CACHE_SETTINGS = "Tag cache requires a positive TTL and a nonempty prefix."
INVALID_JWT_SECRET = "Set JWT_SECRET_KEY to a random secret of at least 32 bytes in .env."

# Background jobs.
EXPORT_PERMISSION_UNAVAILABLE = "Export permission no longer available"
EXPORT_ROW_LIMIT_EXCEEDED = "Export row limit exceeded"
