"""
test_facial_door.py - Suíte de testes automatizados para integração do botão Facial Hikvision no RemoteXPTI.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ajusta encoding Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tuya_access_manager import TuyaAccessManager


class TestFacialHikvisionIntegration(unittest.TestCase):

    def setUp(self):
        self.mgr = TuyaAccessManager()

    def test_01_door_present_in_config(self):
        """Verifica se a porta facial Hikvision está cadastrada e carregada."""
        doors = self.mgr.get_doors()
        facial_doors = [d for d in doors if d.get("id") == "door_facial_hikvision"]
        self.assertTrue(len(facial_doors) > 0, "A porta 'door_facial_hikvision' deve estar presente na lista de portas.")
        
        fdoor = facial_doors[0]
        self.assertEqual(fdoor.get("mode"), "hikvision")
        self.assertEqual(fdoor.get("host"), "192.168.12.94")
        self.assertEqual(fdoor.get("port"), 80)
        self.assertEqual(fdoor.get("username"), "admin")
        self.assertEqual(fdoor.get("door_id"), 1)
        print("✅ Test 01: Porta facial presente nas configurações com parâmetros corretos.")

    def test_02_facial_door_online_without_tuya_cloud(self):
        """A porta facial deve constar como online/local mesmo que a nuvem Tuya esteja offline."""
        self.mgr._cloud_connected = False
        doors = self.mgr.get_doors()
        fdoor = next(d for d in doors if d.get("id") == "door_facial_hikvision")
        self.assertTrue(fdoor.get("cloud_online"), "A porta facial deve ter cloud_online=True mesmo com Tuya offline.")
        self.assertTrue(fdoor.get("is_local"), "A porta facial deve ter is_local=True.")

        tuya_doors = [d for d in doors if d.get("mode") != "hikvision"]
        for td in tuya_doors:
            self.assertFalse(td.get("cloud_online"), "Portas Tuya convencionais devem refletir Nuvem offline.")
        print("✅ Test 02: Status de disponibilidade independente da Nuvem Tuya validado.")

    def test_03_hikvision_config_fallback(self):
        """Testa o extrator de parâmetros com fallbacks."""
        cfg = self.mgr._get_hikvision_config({"id": "dummy"})
        self.assertEqual(cfg["host"], "192.168.12.94")
        self.assertEqual(cfg["port"], 80)
        self.assertEqual(cfg["username"], "admin")
        self.assertEqual(cfg["door_id"], 1)

        custom_cfg = self.mgr._get_hikvision_config({
            "id": "dummy",
            "host": "10.0.0.99",
            "port": 8080,
            "door_id": 2
        })
        self.assertEqual(custom_cfg["host"], "10.0.0.99")
        self.assertEqual(custom_cfg["port"], 8080)
        self.assertEqual(custom_cfg["door_id"], 2)
        print("✅ Test 03: Extração e fallback de configurações ISAPI validado.")

    @patch("requests.put")
    def test_04_open_door_mock_success(self, mock_put):
        """Testa abertura com sucesso simulado (200 OK)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<statusCode>1</statusCode><subStatusCode>ok</subStatusCode>"
        mock_put.return_value = mock_resp

        success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste Automatizado")
        self.assertTrue(success)
        self.assertIn("sucesso", msg.lower())

        # Verifica log de acesso
        logs = self.mgr.get_access_logs()
        self.assertTrue(len(logs) > 0)
        self.assertEqual(logs[0]["door_id"], "door_facial_hikvision")
        self.assertTrue(logs[0]["success"])
        print("✅ Test 04: Disparo de abertura com retorno 200 e log de acesso validado.")

    @patch("requests.put")
    def test_05_open_door_mock_auth_error(self, mock_put):
        """Testa abertura com erro de autenticação (401 Unauthorized)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_put.return_value = mock_resp

        success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste Automatizado")
        self.assertFalse(success)
        self.assertIn("401", msg)
        print("✅ Test 05: Tratamento de erro 401 Unauthorized validado.")

    @patch("requests.put")
    def test_06_open_door_mock_timeout(self, mock_put):
        """Testa tratamento de timeout de conexão."""
        import requests
        mock_put.side_effect = requests.exceptions.ConnectTimeout("Timeout")

        success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste Automatizado")
        self.assertFalse(success)
        self.assertIn("limite", msg.lower())
        print("✅ Test 06: Tratamento de ConnectTimeout validado.")

    def test_07_open_disabled_door(self):
        """Testa tentativa de acionar porta facial desabilitada."""
        fdoor = next(d for d in self.mgr.config.get("doors", []) if d.get("id") == "door_facial_hikvision")
        orig_enabled = fdoor.get("enabled", True)
        try:
            fdoor["enabled"] = False
            success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste")
            self.assertFalse(success)
            self.assertIn("desabilitada", msg.lower())
            print("✅ Test 07: Bloqueio de porta desabilitada validado.")
        finally:
            fdoor["enabled"] = orig_enabled

    def test_08_live_door_opening(self):
        """Testa a abertura real da porta no terminal facial conectado na rede física."""
        try:
            success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste Real de Bancada")
            print(f"📡 Test 08 Disparo Físico Real: sucesso={success}, msg='{msg}'")
            self.assertTrue(success, f"Falha ao acionar porta física real: {msg}")
            print("✅ Test 08: Comunicação real com o terminal 192.168.12.94 funcionou perfeitamente!")
        except Exception as e:
            print(f"⚠️ Test 08 Exceção no teste físico: {e}")
            raise


    @patch("requests.put")
    def test_09_open_door_mock_device_rejection_200(self, mock_put):
        """Testa resposta 200 OK da Hikvision mas com statusCode de erro no corpo XML."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ResponseStatus version="2.0">\n'
            '    <statusCode>4</statusCode>\n'
            '    <statusString>Invalid Operation</statusString>\n'
            '    <subStatusCode>deviceBusy</subStatusCode>\n'
            '</ResponseStatus>'
        )
        mock_put.return_value = mock_resp

        success, msg = self.mgr.open_door("door_facial_hikvision", source="Teste Automatizado")
        self.assertFalse(success, "Resposta 200 com statusCode != 1 não deve ser considerada sucesso.")
        self.assertIn("rejeitou", msg.lower())
        print("✅ Test 09: Tratamento de rejeição interna do firmware (HTTP 200 com erro XML) validado.")

    def test_10_safe_port_and_door_id_conversion(self):
        """Testa resiliência de parsing de portas com campos vazios ou inválidos."""
        cfg = self.mgr._get_hikvision_config({
            "id": "dummy",
            "host": "192.168.12.94",
            "port": "",
            "door_id": ""
        })
        self.assertEqual(cfg["port"], 80)
        self.assertEqual(cfg["door_id"], 1)

        cfg_invalid = self.mgr._get_hikvision_config({
            "id": "dummy",
            "host": "192.168.12.94",
            "port": "abc",
            "door_id": "xyz"
        })
        self.assertEqual(cfg_invalid["port"], 80)
        self.assertEqual(cfg_invalid["door_id"], 1)
        print("✅ Test 10: Parsing seguro de portas e relés vazios ou inválidos validado.")

    def test_11_cloud_push_filters_local_facial(self):
        """Testa que portas locais (Hikvision ISAPI) não são enviadas ao Supabase."""
        from cloud_sync import CloudSyncManager
        import json
        from unittest.mock import patch

        captured_payloads = []
        def fake_urlopen(req, timeout=None):
            if req.data:
                data = json.loads(req.data.decode("utf-8"))
                captured_payloads.append(data)
            resp = MagicMock()
            resp.status = 200
            return resp

        cfg_to_push = {
            "enabled": True,
            "doors": [
                {"id": "door_tuya", "name": "Porta Nuvem", "mode": "cloud_scene"},
                {"id": "door_facial_hikvision", "name": "Facial Local", "mode": "hikvision"}
            ]
        }

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with patch.object(CloudSyncManager, "is_configured", return_value=True):
                with patch("config_manager.ConfigManager.get_supabase_config", return_value={
                    "enabled": True, "url": "https://fake.supabase.co", "key": "fakekey"
                }):
                    CloudSyncManager.push_doors_config(cfg_to_push)

        self.assertTrue(len(captured_payloads) > 0)
        pushed_notes = json.loads(captured_payloads[0][0]["notes"])
        pushed_doors = pushed_notes.get("doors", [])
        self.assertEqual(len(pushed_doors), 1)
        self.assertEqual(pushed_doors[0]["id"], "door_tuya")
        self.assertFalse(any(d.get("id") == "door_facial_hikvision" for d in pushed_doors))
        print("✅ Test 11: Isolamento e omissão do terminal facial no push para o Supabase validado.")

    def test_12_door_deletion_preserves_after_migration(self):
        """Testa que uma porta excluída intencionalmente pelo usuário não é ressuscitada ao recarregar a config."""
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_cfg = Path(tmpdir) / "doors_config.json"
            # Config já migrada com facial_initialized=True, mas sem a porta facial (usuário a deletou)
            tmp_cfg.write_text(json.dumps({
                "enabled": True,
                "facial_initialized": True,
                "doors": [
                    {"id": "door_operacional", "name": "Porta 1"}
                ]
            }), encoding="utf-8")

            old_path = self.mgr.config_path
            try:
                self.mgr.config_path = tmp_cfg
                loaded = self.mgr.load_config()
                door_ids = [d.get("id") for d in loaded.get("doors", [])]
                self.assertNotIn("door_facial_hikvision", door_ids, "Porta deletada não deve ser ressuscitada.")
                print("✅ Test 12: Permanência da exclusão de porta após migração inicial validada.")
            finally:
                self.mgr.config_path = old_path


if __name__ == "__main__":
    unittest.main()
