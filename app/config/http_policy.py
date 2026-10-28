"""HTTP policy syntax shared by settings and transport middleware."""

from ipaddress import IPv4Network, IPv6Network, ip_network

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
FORBIDDEN_HEADERS = frozenset(
    {
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "proxy-connection",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "forwarded",
        "via",
        "client-ip",
        "true-client-ip",
    }
)


def proxy_network(value: str) -> IPv4Network | IPv6Network:
    if "%" in value:
        raise ValueError("Scoped proxy addresses are not supported")
    if "/" in value and not value.split("/", 1)[1].isascii():
        raise ValueError("Use a numeric CIDR prefix")
    if "/" in value and not value.split("/", 1)[1].isdecimal():
        raise ValueError("Use a numeric CIDR prefix")
    network = ip_network(value, strict=False)
    if network.prefixlen == 0:
        raise ValueError("Blanket proxy trust is not supported")
    return network
