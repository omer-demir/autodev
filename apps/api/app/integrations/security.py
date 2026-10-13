import ipaddress
import socket
from urllib.parse import urlparse

from ..registry import RegistryError


def validate_public_https(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RegistryError(
            "Import URL must be public HTTPS without embedded credentials")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RegistryError("Import host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise RegistryError(
                "Import URL must resolve only to public addresses")
