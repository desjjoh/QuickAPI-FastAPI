from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "QuickAPI"
    version: str = "1.0.0"
    debug: bool = True

    class Config:
        """
        Pydantic settings configuration.

        Specifies the source for environment variables and enables automatic
        loading from a `.env` file when present.
        """
        env_file = ".env"



settings = Settings()
