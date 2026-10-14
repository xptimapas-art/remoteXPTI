import ast
import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules.setdefault('logger',types.SimpleNamespace(log=MagicMock()))
from camera_streams import CameraStream, h264_mime, secondary_rtsp_url
from camera_snapshots import CameraError

CONNECTION={'host':'fixture.invalid','username':'fixture','password':'test # percent%'}

class StreamFormatTests(unittest.TestCase):
    def test_secondary_stream_url_encodes_password_and_uses_separate_rtsp_port(self):
        url=secondary_rtsp_url(CONNECTION,1,13699)
        self.assertTrue(url.endswith(':13699/Streaming/Channels/102'))
        self.assertNotIn('test # percent%',url)
        self.assertIn('test%20%23%20percent%25',url)

    def test_nvr_channels_always_use_secondary_stream(self):
        self.assertTrue(secondary_rtsp_url(CONNECTION,2).endswith('/202'))
        self.assertTrue(secondary_rtsp_url(CONNECTION,201).endswith('/202'))

    def test_invalid_address_and_ports_do_not_start_networking(self):
        for connection,channel,port in [({**CONNECTION,'host':'user@host'},1,554),(CONNECTION,1,0),(CONNECTION,0,554)]:
            with self.assertRaises(CameraError):secondary_rtsp_url(connection,channel,port)

    def test_h264_profiles_from_both_rtsp_and_mp4_extradata(self):
        self.assertEqual(h264_mime(b'\x00\x00\x00\x01\x67\x4d\x00\x1f'),'video/mp4; codecs="avc1.4d001f"')
        self.assertEqual(h264_mime(b'\x01\x42\x00\x32'),'video/mp4; codecs="avc1.420032"')
        with self.assertRaises(CameraError):h264_mime(b'no codec data')

    def test_stopped_stream_rejects_further_output(self):
        stream=CameraStream(CONNECTION);stream.stop()
        with self.assertRaises(OSError):stream.write(b'frame')
        self.assertEqual(stream.read(0),b'')

    def test_output_buffer_is_bounded(self):
        stream=CameraStream(CONNECTION)
        self.assertEqual(stream._queue.maxsize,64)
        with self.assertRaises(CameraError):stream.write(b'x'*(2*1024*1024+1))

    def test_concurrency_limit_rejects_before_starting_network(self):
        stream=CameraStream(CONNECTION)
        with patch('camera_streams._STREAM_SLOTS') as slots:
            slots.acquire.return_value=False
            with self.assertRaises(CameraError) as error:stream.start()
            self.assertEqual(error.exception.status_code,429)
        self.assertFalse(stream._thread.is_alive())


class StreamEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi import HTTPException,Request
        from fastapi.responses import StreamingResponse
        self.HTTPException=HTTPException
        tree=ast.parse((Path(__file__).resolve().parents[1]/'desktop_backend.py').read_text('utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='get_door_camera_stream')
        node.decorator_list=[]
        self.gate=MagicMock();self.stream=MagicMock();self.factory=MagicMock();self.factory.return_value.start.return_value=self.stream
        self.stream.mime='video/mp4; codecs="avc1.4d001f"'
        self.request=MagicMock();self.request.is_disconnected=MagicMock(side_effect=lambda:asyncio.sleep(0,result=False))
        self.config=MagicMock();self.config.is_dev_authenticated.return_value=True
        self.context={'HTTPException':HTTPException,'Request':Request,'StreamingResponse':StreamingResponse,'CameraError':CameraError,
                      'CameraStream':self.factory,'require_dev_access':self.gate,'_resolve_door_camera':lambda key:(CONNECTION,{'channel':1,'rtsp_port':13699}),
                      'config_mgr':self.config,'asyncio':asyncio}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<stream-endpoint>','exec'),self.context)

    def test_requires_authenticated_operator_before_opening_rtsp(self):
        self.gate.side_effect=self.HTTPException(status_code=403)
        with self.assertRaises(self.HTTPException):self.context['get_door_camera_stream']('a',self.request)
        self.factory.assert_not_called()

    def test_disconnect_closes_worker_and_video_is_not_cached(self):
        self.stream.read.side_effect=[b'ftyp',b'moov',b'']
        response=self.context['get_door_camera_stream']('a',self.request)
        self.assertEqual(response.headers['cache-control'],'no-store')
        async def consume():return [chunk async for chunk in response.body_iterator]
        self.assertEqual(asyncio.run(consume()),[b'ftyp',b'moov'])
        self.stream.stop.assert_called_once()
        self.factory.assert_called_once_with(CONNECTION,1,13699)

    def test_logout_stops_an_existing_stream(self):
        self.config.is_dev_authenticated.return_value=False
        response=self.context['get_door_camera_stream']('a',self.request)
        async def consume():return [chunk async for chunk in response.body_iterator]
        self.assertEqual(asyncio.run(consume()),[])
        self.stream.read.assert_not_called();self.stream.stop.assert_called_once()

if __name__=='__main__':unittest.main()
