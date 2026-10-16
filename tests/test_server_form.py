"""New-server persistence, group safety and offline city lookup."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
from typing import Optional
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("logger", types.SimpleNamespace(log=MagicMock()))
with tempfile.TemporaryDirectory() as directory, patch("runtime_paths.get_data_dir", return_value=Path(directory)):
    from storage import StorageManager
from server_location import resolve_location, location_update, municipality_catalog
from atomic_storage import PersistenceError
from fastapi import HTTPException
from pydantic import BaseModel, Field


class LocationTests(unittest.TestCase):
    def test_offline_city_matches_accents_and_uf_without_using_server_name(self):
        found = resolve_location(dict(name='COPE',city='florianopolis',state='sc'))
        self.assertEqual(found['city'],'Florianópolis')
        self.assertEqual(found['state'],'SC')
        self.assertTrue(found['location_approximate'])
        self.assertEqual(found['location_source'],'city')
        self.assertTrue(-28<found['latitude']<-27)
        self.assertGreater(len(municipality_catalog()),5500)

    def test_exact_coordinates_override_city_and_zero_is_valid(self):
        found=resolve_location(dict(city='Não existe',state='SC',latitude=0,longitude=0))
        self.assertEqual((found['latitude'],found['longitude']),(0,0))
        self.assertFalse(found['location_approximate'])

    def test_empty_location_stays_empty_even_for_legacy_known_name(self):
        found=resolve_location(dict(name='COPE',city='',state=''))
        self.assertEqual(found['location_source'],'none')
        self.assertIsNone(found['latitude'])

    def test_invalid_coordinates_city_or_state_never_get_a_guessed_position(self):
        for changes in [dict(city='Florianópolis'),dict(state='SC'),dict(city='Florianópolis',state='SP'),
                        dict(city='Cidade inexistente',state='SC'),dict(city='Fraiburgo',state='XX'),
                        dict(latitude=1),dict(latitude=91,longitude=10),
                        dict(latitude=float('nan'),longitude=10),dict(latitude=True,longitude=10)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                resolve_location(changes)

    def test_city_change_repositions_approximate_but_preserves_exact_location(self):
        approximate=resolve_location(dict(city='Florianópolis',state='SC'))
        updated=location_update(approximate,dict(city='Joinville',state='SC'))
        self.assertNotEqual(updated['latitude'],approximate['latitude'])
        unchanged=location_update(approximate,dict(latitude=approximate['latitude'],longitude=approximate['longitude']))
        self.assertTrue(unchanged['location_approximate'])
        manual=resolve_location(dict(city='Florianópolis',state='SC',latitude=1,longitude=2))
        updated=location_update(manual,dict(city='Joinville',state='SC'))
        self.assertEqual((updated['latitude'],updated['longitude']),(1,2))
        self.assertFalse(updated['location_approximate'])


class ServerFormStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'servers.json'
        self.corporate=dict(id='company',name='Company fixture',host='192.0.2.1',port=3389,
                            group='BEMTEVI',scope='corporate',password='encrypted-fixture',
                            latitude=None,longitude=None,location_source='none',is_shared=True)
        self.path.write_text(json.dumps({'servers':[self.corporate]}),encoding='utf-8')
        self.vault=types.SimpleNamespace(encrypt=lambda value:'enc:'+value,decrypt=lambda value:value)
        self.manager=StorageManager(self.path,vault=self.vault)

    def test_default_and_empty_groups_persist_and_deleted_default_does_not_return(self):
        self.assertTrue({'BEMTEVI','SEJURI','XPTI'}<=set(self.manager.get_groups()))
        self.manager.add_group('VAZIO')
        self.manager.delete_group('XPTI')
        loaded=StorageManager(self.path,vault=self.vault)
        self.assertIn('VAZIO',loaded.get_groups())
        self.assertNotIn('XPTI',loaded.get_groups())
        self.assertEqual(loaded.servers,[self.corporate])

    def test_used_group_cannot_be_deleted_even_when_calling_storage_directly(self):
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.manager.delete_group('bemtevi')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.manager.servers,[self.corporate])

    def test_rename_preserves_server_ids_passwords_and_membership(self):
        self.manager.rename_group('BEMTEVI','EMPRESA')
        expected={**self.corporate,'group':'EMPRESA'}
        self.assertEqual(self.manager.servers,[expected])
        self.assertEqual(StorageManager(self.path,vault=self.vault).servers,[expected])
        with self.assertRaises(ValueError):
            self.manager.delete_group('EMPRESA')

    def test_dev_cannot_rename_company_group(self):
        before=self.path.read_bytes()
        with self.assertRaises(PermissionError):
            self.manager.rename_group('BEMTEVI','OUTRO',allow_corporate=False)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(self.manager.group_details(allow_corporate=False)[0]['rename_allowed'])

    def test_duplicate_and_invalid_names_do_not_change_registry(self):
        before=self.path.read_bytes()
        for name in (' bemtevi ','','\n','a'*61):
            with self.assertRaises(ValueError):
                self.manager.add_group(name)
        self.assertEqual(self.path.read_bytes(),before)

    def test_failed_group_save_rolls_back_registry_and_servers_together(self):
        before,raw=deepcopy(self.manager.servers),self.path.read_bytes()
        groups=self.manager.get_groups()
        with patch('atomic_storage.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(PersistenceError):
                self.manager.rename_group('BEMTEVI','EMPRESA')
        self.assertEqual(self.manager.servers,before)
        self.assertEqual(self.manager.get_groups(),groups)
        self.assertEqual(self.path.read_bytes(),raw)

    def test_new_server_city_persists_approximation_and_later_coordinates_replace_it(self):
        created=self.manager.add_server(dict(name='COPE teste',host='127.0.0.1',scope='local',
                                            group='XPTI',city='Florianópolis',state='SC'))
        self.assertEqual(created['location_source'],'city')
        loaded=StorageManager(self.path,vault=self.vault).get_server(created['id'])
        self.assertEqual(loaded['city'],'Florianópolis')
        exact=self.manager.update_server(created['id'],dict(latitude=-27.1,longitude=-48.1))
        self.assertEqual(exact['location_source'],'manual')
        self.assertFalse(exact['location_approximate'])
        self.assertEqual(self.manager.servers[0],self.corporate)

    def test_new_server_without_location_does_not_gain_guessed_coordinates_after_reload(self):
        created=self.manager.add_server(dict(name='COPE',host='127.0.0.1',scope='local',city='',state=''))
        loaded=StorageManager(self.path,vault=self.vault).get_server(created['id'])
        self.assertIsNone(loaded['latitude'])

    def test_group_api_enforces_count_and_dev_write_guards(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'desktop_backend.py').read_text(encoding='utf-8-sig'))
        names={'GroupRequest','RenameGroupRequest','get_server_groups','add_server_group',
               'rename_server_group','delete_server_group'}
        nodes=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names]
        for node in nodes: node.decorator_list=[]
        context=dict(BaseModel=BaseModel,Field=Field,HTTPException=HTTPException,
                     storage_mgr=self.manager,is_development=lambda:True,broadcast_ws=MagicMock(),
                     CloudSyncManager=MagicMock(can_write_servers=MagicMock(return_value=False)),threading=MagicMock())
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<group routes>','exec'),context)
        with self.assertRaises(HTTPException) as failure:
            context['delete_server_group'](context['GroupRequest'](name='BEMTEVI'))
        self.assertEqual(failure.exception.status_code,409)
        with self.assertRaises(HTTPException) as failure:
            context['rename_server_group'](context['RenameGroupRequest'](name='BEMTEVI',new_name='EMPRESA'))
        self.assertEqual(failure.exception.status_code,403)
        context['add_server_group'](context['GroupRequest'](name='VAZIO'))
        context['rename_server_group'](context['RenameGroupRequest'](name='VAZIO',new_name='VAZIO 2'))
        context['delete_server_group'](context['GroupRequest'](name='VAZIO 2'))
        self.assertNotIn('VAZIO 2',self.manager.get_groups())
        self.assertEqual(self.manager.servers,[self.corporate])
        context['threading'].Thread.assert_not_called()


if __name__=='__main__':
    unittest.main()
