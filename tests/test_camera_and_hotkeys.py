import ast
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image

sys.modules.setdefault('logger', types.SimpleNamespace(log=MagicMock()))
from camera_snapshots import CameraError, CameraSnapshots
from hotkey_capture import CaptureKeys


class CameraSnapshotTests(unittest.TestCase):
    def setUp(self):
        buffer=io.BytesIO();Image.new('RGB',(20,10),(30,60,90)).save(buffer,format='JPEG')
        self.jpeg=buffer.getvalue()
        self.connection={'host':'fixture.invalid','port':80,'protocol':'http','username':'fixture-user','password':'fixture-password'}
        self.clock=[0.0]
        self.camera=CameraSnapshots(clock=lambda:self.clock[0])
        self.session_patch=patch('camera_snapshots.requests.Session')
        self.session_factory=self.session_patch.start();self.addCleanup(self.session_patch.stop)
        self.session=self.session_factory.return_value.__enter__.return_value
        self.session.get.return_value=self.response(200,self.jpeg)

    def response(self,status,body):
        response=MagicMock();response.__enter__.return_value=response
        response.status_code=status;response.iter_content.return_value=[body]
        return response

    def test_credentials_stay_out_of_url_and_cached_frame_avoids_duplicate_polling(self):
        self.assertEqual(self.camera.get(self.connection),self.jpeg)
        self.assertEqual(self.camera.get(self.connection),self.jpeg)
        self.session.get.assert_called_once()
        url=self.session.get.call_args.args[0]
        self.assertNotIn('fixture-password',url)
        self.assertNotIn('fixture-user',url)
        self.assertTrue(url.endswith('/101/picture'))
        self.assertFalse(self.session.get.call_args.kwargs['allow_redirects'])
        self.assertTrue(self.session.get.call_args.kwargs['stream'])
        self.assertFalse(self.session.trust_env)

    def test_channel_fallback_and_reuse(self):
        self.session.get.side_effect=[self.response(404,b''),self.response(200,self.jpeg),self.response(200,self.jpeg)]
        self.camera.get(self.connection)
        self.assertTrue(self.session.get.call_args.args[0].endswith('/1/picture'))
        self.clock[0]=2;self.camera.get(self.connection)
        self.assertTrue(self.session.get.call_args.args[0].endswith('/1/picture'))
        self.assertEqual(self.session.get.call_count,3)

    def test_authentication_error_is_cached_without_leaking_device_response(self):
        self.session.get.return_value=self.response(401,b'private fixture body')
        for _ in range(2):
            with self.assertRaisesRegex(CameraError,'recusou'):
                self.camera.get(self.connection)
        self.session.get.assert_called_once()

    def test_invalid_payload_is_not_accepted_as_a_camera_frame(self):
        self.session.get.return_value=self.response(200,b'<html>not an image</html>')
        with self.assertRaisesRegex(CameraError,'JPEG'):
            self.camera.get(self.connection)

    def test_oversize_frame_is_bounded(self):
        self.session.get.return_value=self.response(200,b'x'*(4*1024*1024+1))
        with self.assertRaisesRegex(CameraError,'tamanho'):
            self.camera.get(self.connection)

    def test_configuration_change_does_not_return_previous_device_frame(self):
        self.camera.get(self.connection)
        self.camera.get({**self.connection,'host':'second-fixture.invalid'})
        self.assertEqual(self.session.get.call_count,2)

    def test_invalid_channel_and_address_do_not_issue_requests(self):
        for conn,channel in [({**self.connection,'host':'user@host'},1),({**self.connection,'protocol':'ftp'},1),(self.connection,0)]:
            with self.assertRaises(CameraError):self.camera.get(conn,channel)
        self.session.get.assert_not_called()


class ShortcutCaptureTests(unittest.TestCase):
    def test_main_key_is_swallowed_until_release_and_result_matches_native_parser(self):
        keys=CaptureKeys()
        self.assertTrue(keys.event(0x77,True))
        self.assertEqual(keys.state,'releasing')
        self.assertEqual(keys.hotkey,'F8')
        self.assertTrue(keys.event(0x77,True))
        self.assertTrue(keys.event(0x77,False))
        self.assertEqual(keys.state,'completed')

    def test_modifiers_do_not_finish_capture(self):
        keys=CaptureKeys()
        self.assertFalse(keys.event(0x11,True));self.assertFalse(keys.event(0x12,True))
        self.assertEqual(keys.state,'recording')
        self.assertTrue(keys.event(ord('K'),True));keys.event(ord('K'),False)
        self.assertEqual(keys.hotkey,'Ctrl+Alt+K')

    def test_escape_cancels_without_changing_shortcut(self):
        keys=CaptureKeys();self.assertTrue(keys.event(0x1B,True));keys.event(0x1B,False)
        self.assertEqual(keys.state,'cancelled');self.assertEqual(keys.hotkey,'')

    def test_unsupported_key_is_not_saved(self):
        keys=CaptureKeys();self.assertTrue(keys.event(0xBA,True));keys.event(0xBA,False)
        self.assertEqual(keys.state,'error');self.assertEqual(keys.hotkey,'')

    def test_pageup_and_initial_modifiers(self):
        keys=CaptureKeys(['shift']);keys.event(0x21,True);keys.event(0x21,False)
        self.assertEqual(keys.hotkey,'Shift+PageUp')


class CameraAndCaptureEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi import HTTPException
        from fastapi.responses import Response
        self.HTTPException=HTTPException
        names={'_resolve_door_camera','get_door_camera','start_hotkey_capture','get_hotkey_capture','cancel_hotkey_capture'}
        tree=ast.parse((Path(__file__).resolve().parents[1]/'desktop_backend.py').read_text('utf-8'))
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        for node in nodes:node.decorator_list=[]
        self.manager=MagicMock();self.camera=MagicMock();self.capture=MagicMock();self.gate=MagicMock()
        self.context={'tuya_mgr':self.manager,'camera_snapshots':self.camera,'hotkey_capture':self.capture,
                      'require_dev_access':self.gate,'HTTPException':HTTPException,'Response':Response,'CameraError':CameraError}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<camera-and-capture-handlers>','exec'),self.context)

    def test_all_new_endpoints_require_authentication(self):
        self.gate.side_effect=self.HTTPException(status_code=403)
        for name,args in [('get_door_camera',('a',)),('start_hotkey_capture',()),('get_hotkey_capture',('id',)),('cancel_hotkey_capture',('id',))]:
            with self.assertRaises(self.HTTPException):self.context[name](*args)
        self.manager.get_door.assert_not_called();self.capture.start.assert_not_called()

    def test_camera_can_be_viewed_without_opening_the_door(self):
        self.manager.get_door.return_value={'id':'a','mode':'hikvision','camera':{'source':'door'}}
        self.camera.get.return_value=b'jpeg fixture'
        result=self.context['get_door_camera']('a')
        self.assertEqual(result.body,b'jpeg fixture');self.assertEqual(result.headers['cache-control'],'no-store')
        self.manager.open_door.assert_not_called()

    def test_unlinked_camera_does_not_access_network(self):
        self.manager.get_door.return_value={'id':'a'}
        with self.assertRaises(self.HTTPException):self.context['get_door_camera']('a')
        self.camera.get.assert_not_called()


if __name__=='__main__':unittest.main()
