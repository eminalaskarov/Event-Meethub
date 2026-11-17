import base64

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def decode_qr_key(value: str) -> bytes:
    key = base64.b64decode(value, altchars=b"-_", validate=True)
    if len(key) != 32:
        raise ValueError("QR_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    api_prefix: str = "/api/v1"

    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: SecretStr

    seat_hold_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    hold_sweep_interval_seconds: float = Field(default=5, gt=0)

    qr_encryption_key: SecretStr
    google_maps_server_api_key: SecretStr = SecretStr("")

    cors_origins: str = "http://localhost:5173"

    @field_validator("qr_encryption_key")
    @classmethod
    def validate_qr_encryption_key(cls, value: SecretStr) -> SecretStr:
        decode_qr_key(value.get_secret_value())
        return value

    @property
    def qr_key_bytes(self) -> bytes:
        return decode_qr_key(self.qr_encryption_key.get_secret_value())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()