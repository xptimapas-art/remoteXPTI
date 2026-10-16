"""Impede que páginas de outra origem comandem a API desktop local."""
from urllib.parse import urlparse


def allow_local_request(host, origin=None, fetch_site=None):
    destination = urlparse('http://' + host)
    if destination.hostname not in ('127.0.0.1', 'localhost'):
        return False
    if fetch_site == 'cross-site':
        return False
    if origin:
        source = urlparse(origin)
        return source.scheme == 'http' and source.netloc.lower() == destination.netloc.lower()
    return True  # Cliente nativo; não há identidade remota implícita.
