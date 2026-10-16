import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet, InvalidToken
sys.modules.setdefault('logger', types.SimpleNamespace(log=MagicMock()))
from shared_doors import FIELD, decrypt_config, encrypt_config, merge_config, password_key, protect_key, revision
from cloud_sync import CloudSyncManager
from config_manager import ConfigManager
from tuya_access_manager import TuyaAccessManager


class SharedDoorsTests(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key()
        self.config = {'enabled':True,'hotkeys_enabled':False,'doors':[
            {'id':'gate','mode':'cloud_scene','name':'Gate','scene_id':'fixture','home_id':'fixture',
             'camera':{'source':'external','host':'192.0.2.2','password':'CAMERA_SECRET_FIXTURE'}},
            {'id':'facial','mode':'hikvision','host':'192.0.2.3','password':'FACIAL_SECRET_FIXTURE','camera':{'source':'door'}}]}

    def test_password_is_never_present_in_cloud_plaintext_and_other_keys_cannot_read(self):
        envelope = {FIELD:encrypt_config(self.config,self.key)}
        serialized = json.dumps(envelope)
        for secret in ('CAMERA_SECRET_FIXTURE','FACIAL_SECRET_FIXTURE','192.0.2.2','192.0.2.3'):
            self.assertNotIn(secret,serialized)
        self.assertEqual(decrypt_config(envelope,self.key)['doors'],self.config['doors'])
        with self.assertRaises(InvalidToken):
            decrypt_config(envelope,Fernet.generate_key())

    def test_merge_updates_facial_and_camera_credentials_but_keeps_local_keys_and_switches(self):
        local={'enabled':False,'hotkeys_enabled':False,'feedback_sound':False,'doors':[
            {'id':'gate','hotkey':'F7','enabled':False,'camera':{'password':'old'}},
            {'id':'private','share_with_company':False}]}
        merged=merge_config(local,self.config)
        self.assertFalse(merged['enabled']);self.assertFalse(merged['hotkeys_enabled'])
        self.assertFalse(merged['feedback_sound'])
        gate=next(d for d in merged['doors'] if d['id']=='gate')
        self.assertEqual(gate['hotkey'],'F7');self.assertFalse(gate['enabled'])
        self.assertEqual(gate['camera']['password'],'CAMERA_SECRET_FIXTURE')
        self.assertEqual({d['id'] for d in merged['doors']},{'gate','facial','private'})

    def test_removed_shared_access_is_deleted_while_private_access_stays(self):
        merged=merge_config({'doors':[{'id':'old','_cloud_managed':True},{'id':'private'}]}, {'doors':[]})
        self.assertEqual(merged['doors'],[{'id':'private'}])

    def test_authenticated_key_is_bound_to_windows_user_and_removed_on_logout(self):
        key=password_key('fixture-password')
        protected=protect_key(key)
        self.assertNotIn(key.decode(),protected)
        self.assertEqual(protect_key(protected,decrypt=True),key)
        manager=object.__new__(ConfigManager)
        manager.data={'dev_authenticated':True,'doors_sync_key':protected}
        manager.save=MagicMock()
        self.assertEqual(manager.get_doors_sync_key(),key)
        manager.logout_dev()
        self.assertIsNone(manager.get_doors_sync_key())
        self.assertNotIn('doors_sync_key',manager.data)

    def test_dev_without_reauthentication_does_not_fetch_private_settings(self):
        with patch('cloud_sync.ConfigManager') as config, patch('cloud_sync.urllib.request.urlopen') as request:
            config.return_value.get_supabase_config.return_value={'doors_sync_enabled':True,'url':'https://fixture.invalid','key':'fixture'}
            config.return_value.get_doors_sync_key.return_value=None
            self.assertIsNone(CloudSyncManager.fetch_doors_config())
            self.assertFalse(CloudSyncManager.push_doors_config(self.config))
        request.assert_not_called()

    def test_encrypted_upload_keeps_old_tuya_clients_compatible_without_camera_secrets(self):
        response=MagicMock();response.__enter__.return_value=response
        response.read.return_value=b'[{"id":"fixture"}]'
        with patch('cloud_sync.ConfigManager') as config, \
                patch.object(CloudSyncManager,'_read_doors_notes',return_value='{"doors":[]}'), \
                patch('cloud_sync.urllib.request.urlopen',return_value=response) as request:
            config.return_value.get_supabase_config.return_value={'doors_sync_enabled':True,'url':'https://fixture.invalid','key':'fixture'}
            config.return_value.get_doors_sync_key.return_value=self.key
            self.assertTrue(CloudSyncManager.push_doors_config(self.config))
        sent=json.loads(request.call_args.args[0].data)
        self.assertNotIn('SECRET_FIXTURE',json.dumps(sent))
        envelope=json.loads(sent['notes'])
        self.assertEqual([d['id'] for d in envelope['doors']],['gate'])
        self.assertNotIn('camera',envelope['doors'][0])
        self.assertEqual(len(decrypt_config(envelope,self.key)['doors']),2)

    def test_stale_client_cannot_publish_over_newer_private_config(self):
        previous=json.dumps({FIELD:encrypt_config(self.config,self.key)})
        changed={**self.config,'doors':[{'id':'gate','name':'stale'}],'_shared_revision':'wrong'}
        with patch('cloud_sync.ConfigManager') as config, \
                patch.object(CloudSyncManager,'_read_doors_notes',return_value=previous), \
                patch('cloud_sync.urllib.request.urlopen') as request:
            config.return_value.get_supabase_config.return_value={'doors_sync_enabled':True,'url':'https://fixture.invalid','key':'fixture'}
            config.return_value.get_doors_sync_key.return_value=self.key
            with self.assertRaises(ValueError):CloudSyncManager.push_doors_config(changed)
        request.assert_not_called()

    def test_failed_publish_does_not_commit_a_local_edit_as_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=object.__new__(TuyaAccessManager);manager._lock=threading.RLock()
            manager.config=self.config.copy();manager.config_path=Path(directory)/'doors_config.json'
            manager.config_path.write_text(json.dumps(manager.config));manager.reload_hotkeys=MagicMock()
            original=manager.config_path.read_text()
            with patch.object(CloudSyncManager,'can_share_doors',return_value=True), \
                    patch.object(CloudSyncManager,'push_doors_config',side_effect=ValueError('fixture conflict')):
                with self.assertRaises(ValueError):manager.save_config({'doors':[]})
            self.assertEqual(manager.config_path.read_text(),original)
            manager.reload_hotkeys.assert_not_called()


if __name__=='__main__':unittest.main()
