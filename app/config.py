import os

PORT: int = int(os.environ.get("PORT", "8000"))
ENV: str = os.environ.get("ENV", "development")
