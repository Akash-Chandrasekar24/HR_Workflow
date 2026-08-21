import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise Automated Resume Screening System"
    ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000

    # Security
    HMAC_SECRET: str = "change-this-super-secret-hmac-key-for-google-apps-script"

    # AI & Google Gemini LLM Configuration (First Priority Engine)
    GEMINI_API_KEY: str = ""
    AI_AUTO_ACCEPT_THRESHOLD: float = 90.0  # Scores >= 90% are automatically approved by AI

    # Auto Clean Data on Startup (Clears old candidates & files on server restart)
    AUTO_CLEAR_DATA_ON_STARTUP: bool = True

    # File & Processing Constraints
    MAX_FILE_SIZE_MB: int = 10
    # Email / SMTP Settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SENDER_EMAIL: str = ""
    HR_NOTIFICATION_EMAIL: str = "akashchandrasekar24@gmail.com"
    # Google Spreadsheet & Drive Integration
    GOOGLE_SPREADSHEET_URL: str = "https://docs.google.com/spreadsheets/d/1ADbUgOVNNCAxFhZGpTxnOpHtmIeSF6MkMMyeI55ABQk/edit"
    GOOGLE_SPREADSHEET_ID: str = "1ADbUgOVNNCAxFhZGpTxnOpHtmIeSF6MkMMyeI55ABQk"
    GOOGLE_SPREADSHEET_GID: str = "1147998574"
    GOOGLE_DRIVE_FOLDER_URL: str = "https://drive.google.com/drive/folders/1ffGKAYBJDhMVE6oqubPklYnK5NAdBxCZ0sF3HKsJB8XOcp8QwEWh6QGDUW2AKq7rWSDUhSKY"


    # Domo Webform & DataSet Integration
    DOMO_CLIENT_ID: str = ""
    DOMO_CLIENT_SECRET: str = ""
    DOMO_DATASET_ID: str = ""
    DOMO_API_HOST: str = "api.domo.com"
    DOMO_WEBHOOK_URL: str = ""
    ENABLE_DOMO_SYNC: bool = True

    # Storage Paths


    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CSV_DATA_PATH: str = "app/data/screening_results.csv"
    JOB_RULES_PATH: str = "app/config/job_rules.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def csv_absolute_path(self) -> Path:
        path = Path(self.CSV_DATA_PATH)
        if not path.is_absolute():
            path = self.BASE_DIR / path
        return path

    @property
    def rules_absolute_path(self) -> Path:
        path = Path(self.JOB_RULES_PATH)
        if not path.is_absolute():
            path = self.BASE_DIR / path
        return path


settings = Settings()
