from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POWERNEXT_",
        extra="ignore",
        env_file=Path(__file__).resolve().parents[2] / ".env",
    )
    artifacts_dir: Path = Path(__file__).resolve().parents[2] / "artifacts"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    calibration_wall_time_seconds: float = Field(default=600, gt=0, allow_inf_nan=False)
    calibration_max_attempts: int = Field(default=24, ge=1, le=10000)
    gemini_model: str = Field(default="gemini-flash-latest", validation_alias="GEMINI_MODEL")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_timeout_seconds: float = Field(default=30, gt=0, le=120)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )

    def search_defaults(self):
        return {
            "wall_time_seconds": self.calibration_wall_time_seconds,
            "max_proposals": self.calibration_max_attempts,
            "max_forward_evaluations": self.calibration_max_attempts,
            "max_ml_evaluations": self.calibration_max_attempts,
        }

    def with_search_defaults(self, request):
        """Resolve omitted fields once; explicit request values remain authoritative."""
        search = request.search
        defaults = {
            key: value
            for key, value in self.search_defaults().items()
            if key not in search.model_fields_set
        }
        resolved = type(search).model_validate({**search.model_dump(), **defaults})
        return request.model_copy(update={"search": resolved})
