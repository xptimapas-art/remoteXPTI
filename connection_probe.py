"""Read-only TCP checks that distinguish local measurement errors from RDP loss."""
import errno
import socket


_LOCAL_ERRORS = {
    errno.ENETDOWN, errno.ENETUNREACH, errno.EADDRNOTAVAIL, errno.ENOBUFS,
    errno.EMFILE, errno.ENFILE, errno.EACCES, errno.EPERM,
    10024, 10049, 10050, 10051, 10055, 10013,
}
_TIMEOUT_ERRORS = {errno.ETIMEDOUT, 10060}
_REFUSED_ERRORS = {errno.ECONNREFUSED, 10061}
_REMOTE_ERRORS = {errno.EHOSTUNREACH, errno.ECONNRESET, errno.ECONNABORTED, 10065, 10054, 10053}


def probe_connection(host, port=3389, timeout=1.2):
    """Return (True/False/None, reason). None means no valid remote measurement."""
    try:
        if not isinstance(host, str) or not host.strip():
            raise ValueError
        host = host.strip()
        if host.startswith('['):
            end = host.index(']')
            suffix = host[end + 1:]
            if suffix:
                if not suffix.startswith(':'):
                    raise ValueError
                port = int(suffix[1:])
            host = host[1:end]
        elif host.count(':') == 1:
            host, raw_port = host.rsplit(':', 1)
            port = int(raw_port)
        port = int(port)
        if not host or not 1 <= port <= 65535 or any(char.isspace() or char in '/\\@?#' for char in host):
            raise ValueError
    except (ValueError, TypeError):
        return None, 'Endereço ou porta RDP inválidos; teste não realizado.'
    try:
        # create_connection closes sockets on failed attempts; context closes success.
        with socket.create_connection((host, port), timeout=timeout):
            return True, f'RDP respondeu na porta {port}.'
    except socket.gaierror:
        return None, 'Falha ao resolver DNS neste computador; teste RDP inconclusivo.'
    except OSError as error:
        code = getattr(error, 'winerror', None) or error.errno
        if code in _LOCAL_ERRORS:
            return None, f'Teste RDP indisponível neste computador (erro de rede local {code}).'
        if isinstance(error, TimeoutError) or code in _TIMEOUT_ERRORS:
            return False, f'Tempo de resposta RDP esgotado na porta {port}.'
        if isinstance(error, ConnectionRefusedError) or code in _REFUSED_ERRORS:
            return False, f'Conexão RDP recusada na porta {port}.'
        if code in _REMOTE_ERRORS:
            return False, f'Destino RDP inacessível a partir deste computador (erro {code}).'
        return None, f'Teste RDP inconclusivo neste computador (erro {code or "desconhecido"}).'
