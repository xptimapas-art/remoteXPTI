"""Exercise AJIN route code without initializing live profiles or devices."""
import ast
import json
import math
from pathlib import Path
import threading
import sys
import tempfile
import types
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError


class AjinApiTests(unittest.TestCase):
    def setUp(self):
        names = {'EditLabelRequest', 'SetOnuLocationRequest', '_validate_onu_coordinates',
                 '_store_onu_location', '_enrich_ajin_telemetry', 'save_ajin_label',
                 'set_onu_location', 'force_refresh_ajin', 'AjinOnuRequest', 'AjinDeviceRequest',
                 'AjinRegisterRequest', 'scan_ajin_onus', 'delete_ajin_onu', 'register_ajin_onus'}
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'desktop_backend.py').read_text('utf-8-sig'))
        selected = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
                node.decorator_list = []
                selected.append(node)
        self.ctx = {'BaseModel':BaseModel, 'Field':Field, 'Optional':Optional, 'Any':Any, 'Dict':Dict, 'List':List,
                    'math':math, 'threading':threading, 'HTTPException':HTTPException,
                    'ajin_mgr':MagicMock(), 'onu_coordinates':{}, 'onu_coordinates_lock':threading.RLock(),
                    '_save_onu_coordinates':MagicMock(), 'broadcast_ws':MagicMock()}
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'AJIN routes', 'exec'), self.ctx)
        self.ctx['ajin_mgr'].get_data.return_value = {'rows':[{'port':'PON-1','id':'1','name':'Novo'}]}

    def request(self, **values):
        return self.ctx['EditLabelRequest'](port='PON-1', onu_id='1', name='Novo', **values)

    def test_hub_failure_does_not_report_success_or_change_coordinates(self):
        self.ctx['ajin_mgr'].update_label.return_value = False
        with self.assertRaises(HTTPException) as caught:
            self.ctx['save_ajin_label'](self.request(latitude=0, longitude=0))
        self.assertEqual(caught.exception.status_code, 502)
        self.ctx['_save_onu_coordinates'].assert_not_called()
        self.ctx['broadcast_ws'].assert_not_called()

    def test_scanner_failure_and_negative_delete_ack_are_reported_as_errors(self):
        self.ctx['ajin_mgr'].scan_onus.side_effect = OSError('fixture')
        with self.assertRaises(HTTPException) as error:
            self.ctx['scan_ajin_onus']()
        self.assertEqual(error.exception.status_code,502)
        self.ctx['ajin_mgr'].delete_onu.return_value = False
        with self.assertRaises(HTTPException):
            self.ctx['delete_ajin_onu'](self.ctx['AjinOnuRequest'](port='PON-1',onu_id='1'))

    def test_delete_returns_collector_confirmed_snapshot(self):
        result=self.ctx['delete_ajin_onu'](self.ctx['AjinOnuRequest'](port='PON-1',onu_id='1'))
        self.assertEqual(result['status'],'deleted')
        self.assertIn('telemetry',result)

    def test_registration_rejects_empty_duplicate_and_stale_selections(self):
        with self.assertRaises(ValidationError):
            self.ctx['AjinRegisterRequest'](devices=[])
        device={'port':'PON-1','id':'1','serial':'AA'}
        with self.assertRaises(HTTPException) as error:
            self.ctx['register_ajin_onus'](self.ctx['AjinRegisterRequest'](devices=[device,device]))
        self.assertEqual(error.exception.status_code,422)
        self.ctx['ajin_mgr'].register_onus.side_effect = ValueError('A descoberta mudou')
        with self.assertRaises(HTTPException) as error:
            self.ctx['register_ajin_onus'](self.ctx['AjinRegisterRequest'](devices=[device]))
        self.assertEqual(error.exception.status_code,409)

    def test_zero_coordinates_save_and_explicit_nulls_remove_them(self):
        response = self.ctx['save_ajin_label'](self.request(latitude=0, longitude=0))
        self.assertEqual(response['telemetry']['rows'][0]['latitude'], 0)
        self.assertIn('PON-1_1', self.ctx['onu_coordinates'])
        self.ctx['save_ajin_label'](self.request(latitude=None, longitude=None))
        self.assertNotIn('PON-1_1', self.ctx['onu_coordinates'])

    def test_legacy_label_request_without_location_preserves_coordinates(self):
        self.ctx['onu_coordinates'] = {'PON-1_1':{'latitude':1,'longitude':2}}
        self.ctx['save_ajin_label'](self.request())
        self.assertEqual(self.ctx['onu_coordinates']['PON-1_1']['latitude'], 1)
        self.ctx['_save_onu_coordinates'].assert_not_called()

    def test_shared_notes_are_forwarded_and_legacy_requests_preserve_them(self):
        self.ctx['save_ajin_label'](self.request(notes='Observação compartilhada\nSegunda linha'))
        self.ctx['ajin_mgr'].update_label.assert_called_with('PON-1','1','Novo','',notes='Observação compartilhada\nSegunda linha')
        self.ctx['save_ajin_label'](self.request())
        self.ctx['ajin_mgr'].update_label.assert_called_with('PON-1','1','Novo','')
        with self.assertRaises(ValidationError):
            self.request(notes='x'*4001)

    def test_map_visibility_can_be_saved_as_false_without_changing_coordinates_or_notes(self):
        self.ctx['save_ajin_label'](self.request(map_enabled=False))
        self.ctx['ajin_mgr'].update_label.assert_called_with('PON-1','1','Novo','',map_enabled=False)
        self.ctx['_save_onu_coordinates'].assert_not_called()

    def test_shared_coordinates_override_local_legacy_seeds_including_explicit_removal(self):
        self.ctx['onu_coordinates']={'PON-1_1':{'latitude':-27.4,'longitude':-48.4}}
        for latitude,longitude in [(0,0),(None,None)]:
            data={'rows':[{'port':'PON-1','id':'1','latitude':latitude,'longitude':longitude,'coordinates_shared':True}]}
            row=self.ctx['_enrich_ajin_telemetry'](data)['rows'][0]
            self.assertEqual((row['latitude'],row['longitude']),(latitude,longitude))
        self.ctx['save_ajin_label'](self.request(latitude=0,longitude=0))
        self.ctx['ajin_mgr'].update_label.assert_called_with('PON-1','1','Novo','',latitude=0,longitude=0)

    def test_invalid_coordinates_fail_before_sending_identification(self):
        for lat, lon in [(91,0), (0,181), (None,10), (10,None), (float('nan'),0), (0,float('inf'))]:
            with self.subTest(lat=lat, lon=lon), self.assertRaises(HTTPException) as caught:
                self.ctx['save_ajin_label'](self.request(latitude=lat, longitude=lon))
            self.assertEqual(caught.exception.status_code, 422)
        self.ctx['ajin_mgr'].update_label.assert_not_called()

    def test_failed_disk_write_preserves_previous_in_memory_coordinates(self):
        self.ctx['onu_coordinates'] = {'PON-1_1':{'latitude':1,'longitude':2}}
        self.ctx['_save_onu_coordinates'].side_effect = OSError('fixture')
        with self.assertRaises(OSError):
            self.ctx['set_onu_location'](self.ctx['SetOnuLocationRequest'](port='PON-1',onu_id='1',latitude=0,longitude=0))
        self.assertEqual(self.ctx['onu_coordinates']['PON-1_1']['latitude'], 1)

    def test_refresh_waits_for_actual_result_and_returns_the_snapshot(self):
        self.ctx['ajin_mgr'].fetch_telemetry_async.side_effect = lambda **kw:kw['callback'](True)
        result = self.ctx['force_refresh_ajin']()
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(len(result['telemetry']['rows']), 1)

    def test_failed_refresh_returns_an_error_instead_of_refreshing_forever(self):
        self.ctx['ajin_mgr'].fetch_telemetry_async.side_effect = lambda **kw:kw['callback'](False)
        with self.assertRaises(HTTPException) as caught:
            self.ctx['force_refresh_ajin']()
        self.assertEqual(caught.exception.status_code, 502)

    def test_refresh_timeout_is_reported(self):
        with patch.object(threading, 'Event') as event:
            event.return_value.wait.return_value = False
            with self.assertRaises(HTTPException) as caught:
                self.ctx['force_refresh_ajin']()
        self.assertEqual(caught.exception.status_code, 504)

    def test_failed_atomic_coordinate_write_preserves_original_file(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'desktop_backend.py').read_text('utf-8-sig'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_save_onu_coordinates')
        context = {'json':json, 'HTTPException':HTTPException, 'log':MagicMock(), 'onu_coordinates':{}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'AJIN atomic write', 'exec'), context)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config = types.SimpleNamespace(get_config_dir=lambda:folder)
            with patch.dict(sys.modules, {'config_manager':config}):
                context['_save_onu_coordinates']({'old':{'latitude':1,'longitude':2}})
                before = (folder/'onu_coordinates.json').read_bytes()
                with patch.object(Path, 'replace', side_effect=OSError('fixture')):
                    with self.assertRaises(HTTPException) as caught:
                        context['_save_onu_coordinates']({'new':{'latitude':0,'longitude':0}})
                self.assertEqual(caught.exception.status_code, 500)
                self.assertEqual((folder/'onu_coordinates.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
