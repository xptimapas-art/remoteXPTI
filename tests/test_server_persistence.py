"""Regression coverage for saves, favorites and incomplete cloud snapshots."""
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from typing import Optional
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("logger", types.SimpleNamespace(log=MagicMock()))
import runtime_paths
with tempfile.TemporaryDirectory() as import_directory, patch("runtime_paths.get_data_dir", return_value=Path(import_directory)):
    from storage import StorageManager
from atomic_storage import PersistenceError, write_json_atomic
from server_snapshot import CompleteServerSnapshot, SyncConflictError
from cloud_sync import CloudSyncManager
from config_manager import ConfigManager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


def server(key, scope="corporate"):
    return {"id":key, "name":key, "host":"192.0.2.1", "port":3389,
            "username":"fixture", "password":"", "scope":scope,
            "group":"Fixture", "notes":"", "latitude":0, "longitude":0}


def vault():
    return types.SimpleNamespace(encrypt=lambda value:value, decrypt=lambda value:value)


def request_asgi(app, method, path, payload=None):
    """Exercise routing and exception handling without an HTTP server/client dependency."""
    async def request():
        messages=[]
        async def receive():
            return {"type":"http.request", "body":json.dumps(payload).encode(), "more_body":False}
        async def send(message):
            messages.append(message)
        scope={"type":"http", "asgi":{"version":"3.0"}, "http_version":"1.1",
               "method":method,"scheme":"http","path":path,"raw_path":path.encode(),
               "query_string":b"","root_path":"","headers":[(b"content-type",b"application/json")],
               "client":("127.0.0.1",12345),"server":("127.0.0.1",8765)}
        await app(scope,receive,send)
        status=next(m["status"] for m in messages if m["type"]=="http.response.start")
        body=json.loads(b"".join(m.get("body",b"") for m in messages if m["type"]=="http.response.body"))
        return status,body
    return asyncio.run(request())


class ServerPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "servers.json"
        self.path.write_text(json.dumps({"servers":[server("a"), server("b"), server("local", "local")]}), encoding="utf-8")
        self.manager = StorageManager(self.path, vault=vault())

    def test_favorite_survives_reload_and_does_not_follow_cloud_preference(self):
        self.assertIs(self.manager.toggle_favorite("a"), True)
        loaded = StorageManager(self.path, vault=vault())
        self.assertTrue(loaded.get_server("a")["favorite"])
        self.manager.merge_cloud_servers(CompleteServerSnapshot((server("a"), server("b"))))
        self.assertTrue(self.manager.get_server("a")["favorite"])
        self.assertIs(self.manager.toggle_favorite("a"), False)
        self.assertIsNone(self.manager.toggle_favorite("missing"))
        remote_favorite={**server("new"),"favorite":True}
        self.manager.merge_cloud_servers([remote_favorite,{**server("b"),"favorite":True}])
        self.assertFalse(self.manager.get_server("new").get("favorite",False))
        self.assertFalse(self.manager.get_server("b").get("favorite",False))

    def test_failed_add_update_delete_favorite_and_merge_keep_memory_and_disk(self):
        operations = [lambda:self.manager.add_server({**server("new"),"scope":"local"}),
                      lambda:self.manager.update_server("a", {"name":"Changed"}),
                      lambda:self.manager.delete_server("a"),
                      lambda:self.manager.toggle_favorite("a"),
                      lambda:self.manager.merge_cloud_servers([server("new")])]
        for operation in operations:
            with self.subTest(operation=operations.index(operation)):
                before, raw, revision = self.manager.servers, self.path.read_bytes(), self.manager.revision
                with patch("atomic_storage.os.replace", side_effect=PermissionError("fixture")):
                    with self.assertRaises(PersistenceError):
                        operation()
                self.assertEqual(self.manager.servers, before)
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(self.manager.revision, revision)
                self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_unverified_partial_or_empty_list_never_deletes(self):
        self.manager.merge_cloud_servers([server("a")])
        self.manager.merge_cloud_servers([])
        self.assertEqual({s["id"] for s in self.manager.servers}, {"a","b","local"})

    def test_complete_snapshot_deletes_only_absent_corporate_and_backs_up(self):
        self.manager.merge_cloud_servers(CompleteServerSnapshot((server("a"),)))
        self.assertEqual({s["id"] for s in self.manager.servers}, {"a","local"})
        backup = self.path.with_name("servers.json.pre-sync.bak")
        self.assertEqual({s["id"] for s in json.loads(backup.read_text())["servers"]}, {"a","b","local"})
        self.manager.merge_cloud_servers(CompleteServerSnapshot(()))
        self.assertEqual([s["id"] for s in self.manager.servers], ["local"])

    def test_backup_failure_aborts_deletion(self):
        before = self.manager.servers
        with patch("atomic_storage.os.replace", side_effect=PermissionError("fixture")):
            with self.assertRaises(PersistenceError):
                self.manager.merge_cloud_servers(CompleteServerSnapshot(()))
        self.assertEqual(self.manager.servers,before)
        self.assertEqual(len(json.loads(self.path.read_text())["servers"]),3)

    def test_commit_failure_after_backup_preserves_original_data(self):
        before,raw=self.manager.servers,self.path.read_bytes()
        replace=os.replace
        def fail_main(source,target):
            if Path(target)==self.path:
                raise PermissionError("fixture")
            return replace(source,target)
        with patch("atomic_storage.os.replace",side_effect=fail_main):
            with self.assertRaises(PersistenceError):
                self.manager.merge_cloud_servers(CompleteServerSnapshot(()))
        self.assertEqual(self.manager.servers,before)
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertEqual(json.loads(self.path.with_name("servers.json.pre-sync.bak").read_text())["servers"],before)

    def test_edit_during_cloud_read_rejects_stale_snapshot(self):
        revision = self.manager.revision
        self.manager.update_server("a", {"name":"Local edit"})
        with self.assertRaises(SyncConflictError):
            self.manager.merge_cloud_servers(CompleteServerSnapshot(()), expected_revision=revision)
        self.assertEqual(self.manager.get_server("a")["name"],"Local edit")
        self.assertEqual(len(self.manager.servers),3)

    def test_backend_sync_captures_revision_before_network_and_reports_conflict(self):
        tree=ast.parse((ROOT/"desktop_backend.py").read_text(encoding="utf-8-sig"))
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="sync_supabase_servers")
        cloud=MagicMock()
        cloud.is_configured.return_value=True
        def during_fetch():
            self.manager.update_server("a",{"name":"Edited during network"})
            return CompleteServerSnapshot(())
        cloud.fetch_servers.side_effect=during_fetch
        namespace={"sync_shared_doors":lambda:False,"storage_mgr":self.manager,"CloudSyncManager":cloud,"log":MagicMock(),"broadcast_ws":MagicMock()}
        exec(compile(ast.Module(body=[function],type_ignores=[]),"sync route","exec"),namespace)
        ok,count,message=namespace["sync_supabase_servers"]()
        self.assertFalse(ok)
        self.assertIn("durante",message)
        self.assertEqual(self.manager.get_server("a")["name"],"Edited during network")
        self.assertEqual(len(self.manager.servers),3)
        namespace["broadcast_ws"].assert_not_called()
        cloud.fetch_servers.side_effect=lambda:CompleteServerSnapshot((server("a"),server("b")))
        self.assertTrue(namespace["sync_supabase_servers"]()[0])
        namespace["broadcast_ws"].assert_called_once_with({"type":"servers_status_updated"})

    def test_duplicate_or_missing_ids_cannot_delete_anything(self):
        before = self.manager.servers
        for rows in [(server("a"),server("a")), ({"host":"invalid"},), (None,)]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.manager.merge_cloud_servers(CompleteServerSnapshot(rows))
            self.assertEqual(self.manager.servers,before)

    def test_callers_cannot_mutate_persisted_objects_without_commit(self):
        self.manager.servers[0]["favorite"] = True
        self.manager.get_corporate_servers()[0]["favorite"] = True
        self.assertNotIn("favorite",self.manager.get_server("a"))

    def test_concurrent_adds_and_toggles_do_not_lose_commits(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda i:self.manager.add_server({**server(str(i)),"scope":"local"}),range(24)))
            list(executor.map(lambda i:self.manager.toggle_favorite("a"),range(31)))
        self.assertEqual(len(self.manager.servers),27)
        self.assertTrue(self.manager.get_server("a")["favorite"])
        self.assertEqual(json.loads(self.path.read_text())["servers"],self.manager.servers)

    def test_http_save_error_returns_507_without_starting_cloud_write(self):
        names = {"AddServerRequest","UpdateServerRequest","add_server","update_server","delete_server","toggle_favorite","persistence_error_handler"}
        tree = ast.parse((ROOT/"desktop_backend.py").read_text(encoding="utf-8-sig"))
        nodes=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name in names]
        for node in nodes:
            node.decorator_list=[]
        context={"BaseModel":BaseModel,"Optional":Optional,"storage_mgr":self.manager,
                 "config_mgr":MagicMock(),"CloudSyncManager":MagicMock(),"threading":MagicMock(),
                 "HTTPException":HTTPException,"Request":Request,"JSONResponse":JSONResponse,
                 "PersistenceError":PersistenceError,"log":MagicMock()}
        context["Field"]=Field
        context["broadcast_ws"]=MagicMock()
        context["is_development"]=lambda:False
        exec(compile(ast.Module(body=nodes,type_ignores=[]),"server routes","exec"),context)
        app=FastAPI()
        app.add_exception_handler(PersistenceError,context["persistence_error_handler"])
        app.post("/add")(context["add_server"])
        app.put("/servers/{server_id}")(context["update_server"])
        app.delete("/servers/{server_id}")(context["delete_server"])
        app.post("/favorite/{server_id}")(context["toggle_favorite"])
        with patch("atomic_storage.os.replace",side_effect=PermissionError("fixture")):
            for method,url,payload in [("POST","/add",server("new")),("PUT","/servers/a",server("a")),("DELETE","/servers/a",None),("POST","/favorite/a",None)]:
                status,body=request_asgi(app,method,url,payload)
                self.assertEqual(status,507,body)
                self.assertIn("salvar",body["detail"])
        context["threading"].Thread.assert_not_called()
        self.assertTrue(request_asgi(app,"POST","/favorite/a")[1]["favorite"])
        self.assertFalse(request_asgi(app,"POST","/favorite/a")[1]["favorite"])
        self.assertEqual(request_asgi(app,"POST","/favorite/missing")[0],404)

        # Source DEV may favorite company entries and add local fixtures, but
        # company edits/deletes must fail before any memory/disk/cloud mutation.
        context["is_development"]=lambda:True
        context["CloudSyncManager"].can_write_servers.return_value=False
        original=self.manager.servers
        for method in ("PUT","DELETE"):
            status,body=request_asgi(app,method,"/servers/a",server("a") if method=="PUT" else None)
            self.assertEqual(status,403,body)
        self.assertEqual(self.manager.servers,original)
        context["threading"].Thread.assert_not_called()
        status,body=request_asgi(app,"POST","/add",server("test-local"))
        self.assertEqual(status,200,body)
        self.assertEqual(body["server"]["scope"],"local")
        context["threading"].Thread.assert_not_called()

    def test_config_save_is_atomic_and_failure_restores_last_saved_preferences(self):
        manager=object.__new__(ConfigManager)
        with patch("config_manager.get_config_file",return_value=Path(self.temp.name)/"config.json"):
            manager._init()
        before, raw = deepcopy(manager.data), manager.file_path.read_bytes()
        with patch("atomic_storage.os.replace",side_effect=PermissionError("fixture")):
            with self.assertRaises(PersistenceError):
                manager.set_supabase_config("https://fixture.invalid","fixture",False)
        self.assertEqual(manager.data,before)
        self.assertEqual(manager.file_path.read_bytes(),raw)

    def test_corrupt_files_are_not_replaced_with_empty_defaults(self):
        self.path.write_text("{broken",encoding="utf-8")
        before=self.manager.servers
        with self.assertRaises(PersistenceError):
            self.manager.load()
        self.assertEqual(self.path.read_text(),"{broken")
        self.assertEqual(self.manager.servers,before)
        manager=object.__new__(ConfigManager)
        manager.file_path=self.path
        manager.data={}
        with self.assertRaises(PersistenceError):
            manager.load()
        self.assertEqual(self.path.read_text(),"{broken")

    def test_migration_writer_never_overwrites_existing_target(self):
        raw=self.path.read_bytes()
        self.assertFalse(write_json_atomic(self.path,{"servers":[]},overwrite=False))
        self.assertEqual(self.path.read_bytes(),raw)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_blocked_parent_is_a_failure_even_for_non_overwriting_migration(self):
        blocked=Path(self.temp.name)/"not-a-directory"
        blocked.write_text("original")
        with self.assertRaises(PersistenceError):
            write_json_atomic(blocked/"session.json",{},overwrite=False)
        self.assertEqual(blocked.read_text(),"original")


class CloudServerPaginationTests(unittest.TestCase):
    def setUp(self):
        self.patch=patch("cloud_sync.ConfigManager")
        self.config=self.patch.start()
        self.addCleanup(self.patch.stop)
        self.config.return_value.get_supabase_config.return_value={"enabled":True,"url":"https://fixture.invalid","key":"fixture"}

    def page(self, rows, content_range, status=200):
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=status
        response.headers={"Content-Range":content_range} if content_range is not None else {}
        response.read.return_value=json.dumps(rows).encode()
        return response

    def test_personal_favorite_is_not_uploaded_with_shared_server_edits(self):
        item=server("a")
        item["favorite"]=True
        with patch("cloud_sync.is_development",return_value=False), patch("cloud_sync.urllib.request.urlopen",return_value=self.page({},None,201)) as request:
            ok,_=CloudSyncManager.push_single_server(item)
        self.assertTrue(ok)
        uploaded=json.loads(request.call_args.args[0].data)[0]
        self.assertNotIn("favorite",uploaded)
        self.assertEqual(uploaded["name"],"a")

    def test_dev_blocks_all_company_server_writes_even_with_enabled_config(self):
        with patch("cloud_sync.is_development",return_value=True),patch("cloud_sync.urllib.request.urlopen") as request:
            self.assertFalse(CloudSyncManager.can_write_servers())
            self.assertFalse(CloudSyncManager.push_servers([server("a")])[0])
            self.assertFalse(CloudSyncManager.push_single_server(server("a"))[0])
            self.assertFalse(CloudSyncManager.delete_remote_server("a")[0])
        request.assert_not_called()

    def test_dev_can_receive_servers_without_enabling_bidirectional_sync(self):
        cfg=self.config.return_value.get_supabase_config.return_value
        cfg.update(enabled=False,server_pull_enabled=True)
        with patch("cloud_sync.is_development",return_value=True),patch("cloud_sync.urllib.request.urlopen",return_value=self.page([server("a")],"0-0/1")) as request:
            self.assertTrue(CloudSyncManager.is_configured())
            self.assertEqual(len(CloudSyncManager.fetch_servers()),1)
        self.assertEqual(request.call_args.args[0].get_method(),"GET")

    def test_reads_all_pages_even_when_server_caps_page_size_and_filters_reserved_last(self):
        responses=[self.page([server("a"),server("b")],"0-1/4",206),self.page([server("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),server("ffffffff-ffff-ffff-ffff-ffffffffffff")],"2-3/4")]
        with patch("cloud_sync.urllib.request.urlopen",side_effect=responses) as request:
            snapshot=CloudSyncManager.fetch_servers()
        self.assertIsInstance(snapshot,CompleteServerSnapshot)
        self.assertEqual([s["id"] for s in snapshot.rows],["a","b"])
        self.assertIn("offset=2",request.call_args.args[0].full_url)
        self.assertIn("order=id.asc",request.call_args.args[0].full_url)
        self.assertEqual(request.call_args.args[0].headers["Prefer"],"count=exact")

    def test_unknown_count_invalid_interval_shape_duplicate_or_missing_id_never_return_snapshot(self):
        cases=[self.page([],None),self.page([],"*/*"),self.page({},"*/0"),self.page([server("a")],"1-1/1"),self.page([server("a")],"0-1/2"),self.page([server("a"),server("a")],"0-1/2"),self.page([{}],"0-0/1"),self.page([],"*/2"),self.page([server("a")],"0-0/1",500)]
        for response in cases:
            with self.subTest(response=response), patch("cloud_sync.urllib.request.urlopen",return_value=response):
                self.assertIsNone(CloudSyncManager.fetch_servers())

    def test_second_page_failure_total_change_or_repeated_page_discards_entire_response(self):
        for second in [OSError("fixture"),self.page([server("b")],"1-1/3"),self.page([server("a")],"1-1/2")]:
            with self.subTest(second=second),patch("cloud_sync.urllib.request.urlopen",side_effect=[self.page([server("a")],"0-0/2"),second]):
                self.assertIsNone(CloudSyncManager.fetch_servers())

    def test_counted_empty_snapshot_is_distinct_from_failed_or_disabled_fetch(self):
        with patch("cloud_sync.urllib.request.urlopen",return_value=self.page([],"*/0")):
            self.assertEqual(CloudSyncManager.fetch_servers(),CompleteServerSnapshot(()))
        self.config.return_value.get_supabase_config.return_value["enabled"]=False
        with patch("cloud_sync.urllib.request.urlopen") as request:
            self.assertIsNone(CloudSyncManager.fetch_servers())
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
