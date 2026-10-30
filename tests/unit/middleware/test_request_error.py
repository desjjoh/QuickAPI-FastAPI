import asyncio
import json
from unittest.mock import Mock

import pytest
from starlette.types import Message, Receive, Scope, Send

from app.common.middleware.request_error import RequestErrorASGIMiddleware

pytestmark = pytest.mark.unit
SCOPE: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}


@pytest.mark.parametrize(
    'state', ['before_headers', 'streaming', 'completed', 'cancelled']
)
async def test_failures_never_replace_a_started_response(
    state: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[Message] = []
    logger = Mock()

    monkeypatch.setattr('app.common.handlers.exception_handler.log', logger)

    async def receive() -> Message:
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        messages.append(message)

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        if state in {'streaming', 'completed'}:
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send(
                {
                    'type': 'http.response.body',
                    'body': b'partial',
                    'more_body': state == 'streaming',
                }
            )

        if state == 'cancelled':
            raise asyncio.CancelledError

        raise RuntimeError('private provider details')

    app = RequestErrorASGIMiddleware(downstream)

    if state == 'before_headers':
        await app(dict(SCOPE), receive, send)

        assert [message['type'] for message in messages] == [
            'http.response.start',
            'http.response.body',
        ]
        assert messages[0]['status'] == 500
        assert json.loads(messages[1]['body'])['message'] == 'Internal Server Error'
        assert b'private' not in messages[1]['body']
        logger.error.assert_called_once()
    else:
        with pytest.raises(
            asyncio.CancelledError if state == 'cancelled' else RuntimeError
        ):
            await app(dict(SCOPE), receive, send)

        assert len(messages) == (0 if state == 'cancelled' else 2)
        logger.error.assert_not_called()
