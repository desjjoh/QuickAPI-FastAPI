import os
import platform
import socket
import sys
from datetime import datetime

from app.api.system.models.info_model import InfoResponse
from app.config.environment import settings


class SystemInfoService:
    """Build the public, non-secret application runtime identity."""

    def __init__(self, started_at: datetime) -> None:
        self._started_at = started_at

    def info(self) -> InfoResponse:
        return InfoResponse(
            name=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.ENV,
            hostname=socket.gethostname(),
            pid=os.getpid(),
            python_version=platform.python_version() or sys.version.split()[0],
            platform=platform.system() or sys.platform,
            architecture=platform.machine() or "unknown",
            started_at=self._started_at,
            timezone=settings.TIMEZONE,
        )
