"""Resolve forwarding only from explicit IP/CIDR peers, once, before context."""

from ipaddress import ip_address

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.http_policy import proxy_network


class TrustedProxyASGIMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        trusted_proxies: list[str],
        max_header_bytes: int = 4096,
        max_header_count: int = 100,
        max_total_header_bytes: int = 8192,
    ) -> None:
        self.app = app
        self.networks = [proxy_network(value) for value in trusted_proxies]
        self.max_header_bytes = max_header_bytes
        self.max_header_count = max_header_count
        self.max_total_header_bytes = max_total_header_bytes

    def trusted(self, host: str) -> bool:
        try:
            return any(ip_address(host) in network for network in self.networks)
        except ValueError:
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        client = scope.get("client")

        if scope["type"] == "http" and client and self.trusted(client[0]):
            self.apply_forwarding(scope)

        await self.app(scope, receive, send)

    def apply_forwarding(self, scope: Scope) -> None:
        raw_headers = scope.get("headers", [])
        sizes = [len(name) + len(value) for name, value in raw_headers]

        # Do not strip consumed headers until the original header budget passes.
        # The normal limit middleware renders any rejection, including preflights.
        if (
            len(raw_headers) > self.max_header_count
            or sum(sizes) > self.max_total_header_bytes
            or any(size > self.max_header_bytes for size in sizes)
        ):
            return

        selected: dict[bytes, str] = {}

        for name, value in scope.get("headers", []):
            key = name.lower()

            if key not in {b"x-forwarded-for", b"x-forwarded-proto"}:
                continue

            # Leave invalid/duplicate headers intact for the normal 400 renderer.
            if key in selected:
                return

            try:
                decoded = value.decode("ascii")

                if any(ord(char) < 32 or ord(char) == 127 for char in decoded):
                    return

                selected[key] = decoded.strip()
            except UnicodeDecodeError:
                return

        forwarded_client: str | None = None

        try:
            if b"x-forwarded-for" in selected:
                raw_hosts = selected[b"x-forwarded-for"].split(",")

                if any("%" in host for host in raw_hosts):
                    return

                hosts = [str(ip_address(host.strip())) for host in raw_hosts]
                forwarded_client = hosts[0]

                for host in reversed(hosts):
                    if not self.trusted(host):
                        forwarded_client = host

                        break

            scheme = selected.get(b"x-forwarded-proto")

            if scheme is not None and scheme not in {"http", "https"}:
                return
        except ValueError:
            return

        if forwarded_client is not None:
            scope["client"] = (forwarded_client, 0)

        if scheme is not None:
            scope["scheme"] = scheme

        # These two headers were consumed. Other forwarding headers stay forbidden.
        scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() not in selected
        ]
