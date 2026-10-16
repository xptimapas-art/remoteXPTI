import errno
import socket
import unittest
from unittest.mock import patch

from connection_probe import probe_connection


class ProbeTests(unittest.TestCase):
    @patch('connection_probe.socket.create_connection')
    def test_success_closes_socket_and_uses_configured_timeout(self, connect):
        online, message = probe_connection('192.0.2.10', 3390, timeout=3)
        self.assertTrue(online)
        connect.assert_called_once_with(('192.0.2.10',3390), timeout=3)
        connect.return_value.__exit__.assert_called_once()
        self.assertIn('3390', message)

    @patch('connection_probe.socket.create_connection')
    def test_timeout_and_refusal_are_real_remote_failures(self, connect):
        for error, reason in ((TimeoutError(), 'esgotado'),
                              (ConnectionRefusedError(errno.ECONNREFUSED, 'fixture'), 'recusada'),
                              (OSError(10060, 'fixture'), 'esgotado'),
                              (OSError(10061, 'fixture'), 'recusada')):
            connect.side_effect = error
            reachable, message = probe_connection('fixture', 3389)
            self.assertFalse(reachable)
            self.assertIn(reason, message)

    @patch('connection_probe.socket.create_connection')
    def test_local_network_dns_resources_and_firewall_are_inconclusive(self, connect):
        errors = [socket.gaierror(-1, 'fixture'), OSError(errno.ENETDOWN, 'fixture'),
                  OSError(errno.EMFILE, 'fixture'), OSError(errno.EACCES, 'fixture'),
                  OSError(10051, 'fixture'), OSError(10055, 'fixture'), OSError(10049, 'fixture')]
        for error in errors:
            connect.side_effect = error
            reachable, message = probe_connection('fixture')
            self.assertIsNone(reachable)
            self.assertNotIn('fixture', message)

    @patch('connection_probe.socket.create_connection')
    def test_invalid_target_never_opens_socket(self, connect):
        for host, port in [('',3389), ('fixture',0), ('fixture',65536),
                           ('fixture',None), ('fixture:bad',3389), ('https://fixture',3389)]:
            self.assertIsNone(probe_connection(host, port)[0])
        connect.assert_not_called()

    @patch('connection_probe.socket.create_connection')
    def test_ipv4_hostname_and_ipv6_are_supported(self, connect):
        for host, target in [('fixture:3390',('fixture',3390)),
                             ('[2001:db8::1]:3390',('2001:db8::1',3390)),
                             ('2001:db8::1',('2001:db8::1',3389))]:
            self.assertTrue(probe_connection(host)[0])
            connect.assert_called_with(target, timeout=1.2)

    @patch('connection_probe.socket.create_connection', side_effect=OSError(999, 'private diagnostic'))
    def test_unknown_local_error_does_not_leak_raw_exception(self, connect):
        reachable, message = probe_connection('fixture')
        self.assertIsNone(reachable)
        self.assertNotIn('private diagnostic', message)


if __name__ == '__main__':
    unittest.main()
