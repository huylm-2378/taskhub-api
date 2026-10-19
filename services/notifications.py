import logging
import smtplib
import ssl
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

import config
from database import SessionLocal
from models import Comment, Task, User

logger = logging.getLogger(__name__)


def send_email(recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = config.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if config.SMTP_USE_SSL else smtplib.SMTP
    options = {"timeout": config.SMTP_TIMEOUT_SECONDS}
    if config.SMTP_USE_SSL:
        options["context"] = ssl.create_default_context()
    with smtp_class(config.SMTP_HOST, config.SMTP_PORT, **options) as smtp:
        if config.SMTP_USE_TLS:
            smtp.starttls(context=ssl.create_default_context())
        if config.SMTP_USERNAME:
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(message)


def notify_comment(comment_id: UUID) -> None:
    if not config.EMAIL_ENABLED:
        return
    try:
        # Background work owns its session; never retain a request's ORM objects.
        with SessionLocal() as db:
            comment = db.scalar(
                select(Comment).where(Comment.id == comment_id).options(
                    joinedload(Comment.task).joinedload(Task.project), joinedload(Comment.author),
                )
            )
            if comment is None:
                return  # The comment/task may have been deleted since the response.
            recipient_ids = {comment.task.project.owner_id, comment.task.assignee_id} - {None, comment.author_id}
            recipients = db.scalars(
                select(User.email).where(User.id.in_(recipient_ids), User.is_active.is_(True))
            ).all()
            subject = f"TaskHub: new comment on task {comment.task_id}"
            body = (
                f"Task: {comment.task.title}\n"
                f"Author: {comment.author.name}\n\n{comment.content}\n\n"
                f"Task ID: {comment.task_id}\nComment ID: {comment.id}\n"
            )
        # Release the database connection before slow SMTP I/O.
        for recipient in recipients:
            try:
                send_email(recipient, subject, body)
            except Exception as exc:
                # Avoid logging addresses, content, SMTP replies or credentials.
                logger.error("Comment email failed: comment_id=%s error=%s", comment_id, type(exc).__name__)
    except Exception as exc:
        logger.error("Comment notification failed: comment_id=%s error=%s", comment_id, type(exc).__name__)
