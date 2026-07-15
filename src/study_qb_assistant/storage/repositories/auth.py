"""鉴权数据的 SQLAlchemy 仓储。"""

from __future__ import annotations

from sqlalchemy import func, select

from ...auth.records import EmailVerificationCodeRecord, UserRecord
from ..database import get_session_factory
from ..orm import EmailVerificationCodeEntity, UserEntity


class SqlAlchemyAuthRepository:
    """用户持久化仓储。"""

    def __init__(self, path_or_url) -> None:
        self.session_factory = get_session_factory(path_or_url)

    def has_users(self) -> bool:
        with self.session_factory() as session:
            return session.scalar(select(UserEntity.id).limit(1)) is not None

    def get_user(self, username: str) -> UserRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.username == username))
            return self._to_record(entity) if entity else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        """按邮箱读取用户记录，邮箱匹配大小写不敏感。"""

        normalized = (email or "").strip().lower()
        if not normalized:
            return None
        with self.session_factory() as session:
            entity = session.scalar(
                select(UserEntity).where(func.lower(UserEntity.email) == normalized)
            )
            return self._to_record(entity) if entity else None

    def get_user_by_login(self, login_id: str) -> UserRecord | None:
        """按用户名或邮箱读取用户记录。"""

        normalized = (login_id or "").strip()
        if not normalized:
            return None
        user = self.get_user(normalized)
        if user is not None:
            return user
        return self.get_user_by_email(normalized)

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.user_id == user_id))
            return self._to_record(entity) if entity else None

    def get_user_by_invite_code(self, invite_code: str) -> UserRecord | None:
        """按邀请码读取用户记录。"""

        normalized = (invite_code or "").strip()
        if not normalized:
            return None
        with self.session_factory() as session:
            entity = session.scalar(
                select(UserEntity).where(UserEntity.invite_code == normalized)
            )
            return self._to_record(entity) if entity else None

    def list_users(self) -> list[UserRecord]:
        with self.session_factory() as session:
            entities = session.scalars(select(UserEntity)).all()
            return [self._to_record(entity) for entity in entities]

    def save_user(self, record: UserRecord) -> None:
        with self.session_factory() as session:
            entity = session.scalar(
                select(UserEntity).where(UserEntity.username == record.username)
            )
            if entity is None:
                entity = UserEntity(username=record.username, user_id=record.user_id)
                session.add(entity)
            self._apply_record(entity, record)
            session.commit()

    def delete_user(self, username: str) -> bool:
        """删除指定用户记录。"""
        with self.session_factory() as session:
            entity = session.scalar(select(UserEntity).where(UserEntity.username == username))
            if entity is None:
                return False
            session.delete(entity)
            session.commit()
            return True

    def save_email_verification_code(self, record: EmailVerificationCodeRecord) -> None:
        """保存邮箱验证码记录。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(EmailVerificationCodeEntity).where(
                    EmailVerificationCodeEntity.code_id == record.code_id
                )
            )
            if entity is None:
                entity = EmailVerificationCodeEntity(code_id=record.code_id)
                session.add(entity)
            entity.email = record.email
            entity.purpose = record.purpose
            entity.code_hash = record.code_hash
            entity.expires_at = record.expires_at
            entity.attempts = record.attempts
            entity.send_ip_hash = record.send_ip_hash
            entity.created_at = record.created_at
            entity.consumed_at = record.consumed_at
            session.commit()

    def latest_email_verification_code(
        self, *, email: str, purpose: str
    ) -> EmailVerificationCodeRecord | None:
        """读取指定邮箱和用途下最近一条未消费验证码。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(EmailVerificationCodeEntity)
                .where(
                    EmailVerificationCodeEntity.email == email,
                    EmailVerificationCodeEntity.purpose == purpose,
                    EmailVerificationCodeEntity.consumed_at <= 0,
                )
                .order_by(EmailVerificationCodeEntity.created_at.desc())
                .limit(1)
            )
            return self._to_email_code_record(entity) if entity else None

    def latest_email_verification_send(
        self, *, email: str, purpose: str
    ) -> EmailVerificationCodeRecord | None:
        """读取指定邮箱和用途下最近一条验证码发送记录。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(EmailVerificationCodeEntity)
                .where(
                    EmailVerificationCodeEntity.email == email,
                    EmailVerificationCodeEntity.purpose == purpose,
                )
                .order_by(EmailVerificationCodeEntity.created_at.desc())
                .limit(1)
            )
            return self._to_email_code_record(entity) if entity else None

    def count_email_verification_sends(
        self, *, email: str, purpose: str, since: float
    ) -> int:
        """统计指定邮箱在时间窗口内的验证码发送次数。"""

        with self.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count(EmailVerificationCodeEntity.id)).where(
                        EmailVerificationCodeEntity.email == email,
                        EmailVerificationCodeEntity.purpose == purpose,
                        EmailVerificationCodeEntity.created_at >= since,
                    )
                )
                or 0
            )

    def count_email_verification_sends_by_ip(
        self, *, send_ip_hash: str, purpose: str, since: float
    ) -> int:
        """统计指定 IP 哈希在时间窗口内的验证码发送次数。"""

        with self.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count(EmailVerificationCodeEntity.id)).where(
                        EmailVerificationCodeEntity.send_ip_hash == send_ip_hash,
                        EmailVerificationCodeEntity.purpose == purpose,
                        EmailVerificationCodeEntity.created_at >= since,
                    )
                )
                or 0
            )

    def increment_email_verification_attempts(self, code_id: str) -> EmailVerificationCodeRecord:
        """增加验证码校验尝试次数，并返回更新后的记录。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(EmailVerificationCodeEntity).where(
                    EmailVerificationCodeEntity.code_id == code_id
                )
            )
            if entity is None:
                raise ValueError("email verification code not found")
            entity.attempts = int(entity.attempts or 0) + 1
            session.commit()
            return self._to_email_code_record(entity)

    def consume_email_verification_code(self, code_id: str, consumed_at: float) -> None:
        """标记验证码已消费。"""

        with self.session_factory() as session:
            entity = session.scalar(
                select(EmailVerificationCodeEntity).where(
                    EmailVerificationCodeEntity.code_id == code_id
                )
            )
            if entity is None:
                return
            entity.consumed_at = consumed_at
            session.commit()

    def _apply_record(self, entity: UserEntity, record: UserRecord) -> None:
        entity.user_id = record.user_id
        entity.username = record.username
        entity.role = record.role
        entity.status = record.status
        entity.salt = record.salt
        entity.password_hash = record.password_hash
        entity.email = record.email
        entity.points = record.points
        entity.created_at = record.created_at
        entity.invite_code = record.invite_code
        entity.invited_by = record.invited_by
        entity.reset_token_hash = record.reset_token_hash
        entity.reset_expires_at = record.reset_expires_at

    def _to_record(self, entity: UserEntity) -> UserRecord:
        return UserRecord(
            user_id=entity.user_id,
            username=entity.username,
            role=entity.role,
            status=entity.status,
            salt=entity.salt,
            password_hash=entity.password_hash,
            email=entity.email,
            points=entity.points,
            created_at=entity.created_at,
            invite_code=entity.invite_code or "",
            invited_by=entity.invited_by or "",
            reset_token_hash=entity.reset_token_hash,
            reset_expires_at=entity.reset_expires_at,
        )

    def _to_email_code_record(
        self, entity: EmailVerificationCodeEntity
    ) -> EmailVerificationCodeRecord:
        return EmailVerificationCodeRecord(
            code_id=entity.code_id,
            email=entity.email,
            purpose=entity.purpose,
            code_hash=entity.code_hash,
            expires_at=entity.expires_at,
            attempts=int(entity.attempts or 0),
            send_ip_hash=entity.send_ip_hash,
            created_at=entity.created_at,
            consumed_at=float(entity.consumed_at or 0.0),
        )
