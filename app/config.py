"""Settings for the scheduled pipelines.

Deliberately smaller than the application's own config. These jobs need
a database connection and one optional API key; carrying the app's full
settings object would publish the shape of its auth, storage and vision
integrations for no benefit here.

Values come from the environment (GitHub Actions secrets in CI) or a
local `.env`, which is gitignored.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    # Required in every real run. The SQLite default exists so an
    # import-only check (CI linting, `python -c "import scripts.x"`)
    # doesn't need a live database.
    database_url: str = "sqlite+aiosqlite:///./local.db"

    # Optional. pokemontcg.io serves the Cardmarket top-up without a
    # key at a lower rate limit; set it to raise that ceiling.
    pokemontcg_api_key: str = ""


settings = Settings()
