"""Request activity shared by transport and mutation owners."""

import time
from dataclasses import dataclass

from starlette.exceptions import HTTPException
from starlette.types import Scope

ACTIVITY_KEY = 'quickapi.request_activity'
RESPONSE_DEADLINE_MESSAGE = 'Application response deadline exceeded.'


class RequestExpired(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(408, detail)


@dataclass
class RequestActivity:
    expires_at: float = float('inf')
    abandoned: str | None = None
    owns_mutation: bool = False

    def abandon(self, reason: str) -> None:
        if self.abandoned is None:
            self.abandoned = reason

    def assert_active(self) -> None:
        if self.abandoned is not None:
            raise RequestExpired(self.abandoned)

        if time.monotonic() >= self.expires_at:
            self.abandon(RESPONSE_DEADLINE_MESSAGE)

            raise RequestExpired(self.abandoned or RESPONSE_DEADLINE_MESSAGE)


def request_activity(scope: Scope) -> RequestActivity:
    activity = scope.get(ACTIVITY_KEY)

    if activity is None:
        activity = RequestActivity()
        scope[ACTIVITY_KEY] = activity

    if not isinstance(activity, RequestActivity):
        raise RuntimeError('Invalid request activity owner.')

    return activity
