"""Prompt persistence, backup compatibility and hostile-input regressions."""
from copy import deepcopy
import http.client
import json
import threading
import unittest

from skillpane.catalog import Catalog
from skillpane.library import Library
from skillpane.server import AppServer
from skillpane.storage import Annotations
from skillpane.transfers import Transfers
from test_catalog import fixture_root, skill


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture_root()
        self.source=skill(self.base/'home','.agents/skills/fixture','fixture','Synthetic helper','Source sentinel')
        self.original=self.source.read_bytes()
        self.server=AppServer(port=0,home=self.base/'home',state_dir=self.base/'state')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.id=self.server.library.snapshot()['skills'][0]['id']
        self.prompt={'id':'synthetic-prompt','title':'查詢前確認環境','body':'使用 fixture\n先確認 {{環境}}，再執行唯讀查詢。'}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.assertEqual(self.source.read_bytes(),self.original)

    def request(self,method,path,payload=None,origin=None):
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        conn.request(method,path,json.dumps(payload) if payload is not None else None,
                     {'Origin':origin or self.server.origin,'Content-Type':'application/json','X-Skillpane-Client':'1'})
        response=conn.getresponse();status,body=response.status,response.read();conn.close()
        return status,json.loads(body) if 'json' in response.getheader('Content-Type','') else body

    def patch(self,payload,**kwargs):
        return self.request('PATCH','/api/annotation?id='+self.id,payload,**kwargs)

    def test_create_edit_remove_preserves_notes_and_survives_restart(self):
        self.assertEqual(self.patch({'note':'Independent note','favorite':True})[0],200)
        self.assertEqual(self.patch({'prompts':[self.prompt],'prompts_base':[]})[0],200)
        changed={**self.prompt,'body':'Edited\nmultiline body'}
        status,saved=self.patch({'prompts':[changed],'prompts_base':[self.prompt]})
        self.assertEqual(status,200);self.assertEqual(saved['note'],'Independent note')
        restart=Annotations(self.base/'state')
        self.assertEqual(restart.snapshot()[self.id]['prompts'],[changed])
        self.assertEqual(self.patch({'prompts':[],'prompts_base':[changed]})[0],200)
        self.assertEqual(self.server.annotations.snapshot()[self.id],{'note':'Independent note','favorite':True,'prompts':[]})
        self.assertGreaterEqual(len(self.server.transfers.backups()),3)

    def test_stale_prompt_base_cannot_overwrite_newer_prompts(self):
        self.patch({'prompts':[self.prompt],'prompts_base':[]})
        before=self.server.annotations.path.read_bytes()
        self.assertEqual(self.patch({'prompts':[],'prompts_base':[]})[0],409)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)
        self.patch({'note':'Note changed in another window'})
        self.assertEqual(self.patch({'prompts':[],'prompts_base':[self.prompt]})[0],200)
        self.assertEqual(self.server.annotations.snapshot()[self.id]['note'],'Note changed in another window')

    def test_prompt_base_is_required_and_validated(self):
        before=self.server.annotations.path.read_bytes()
        for payload in [{'prompts':[self.prompt]},{'prompts':[self.prompt],'prompts_base':None},
                        {'prompts':[],'prompts_base':[{'id':'invalid'}]},{'prompts_base':[]}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.patch(payload)[0],400)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_invalid_prompt_corpus_is_atomic(self):
        invalid=[None,True,{},'string',[self.prompt]*21,[self.prompt,self.prompt]]
        for field,values in {'id':['bad/id','',False],'title':['','  ','x'*81,'bad\x00',None],
                             'body':['','\n','x'*4001,'bad\x00',[]]}.items():
            invalid.extend([{**self.prompt,field:value}] for value in values)
        invalid.extend([[{**self.prompt,'unexpected':'field'}],[{'id':'missing-fields'}]])
        before=self.server.annotations.path.read_bytes()
        for prompts in invalid:
            with self.subTest(prompts_type=type(prompts).__name__):
                self.assertEqual(self.patch({'prompts':prompts,'prompts_base':[]})[0],400)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_prompt_backup_roundtrip_and_invalid_import_preserve_current_data(self):
        self.patch({'note':'Keep note','prompts':[self.prompt],'prompts_base':[]})
        backup=self.server.transfers.export()
        self.assertEqual(backup['version'],2)
        other=Annotations(self.base/'other-state')
        library=Library(Catalog(self.base/'home'),other);transfer=Transfers(library)
        preview=transfer.preview_import(backup)
        transfer.apply_import({'token':preview['token'],'choices':{row['id']:row['target'] for row in preview['rows']},'mode':'replace','restore_settings':False})
        self.assertEqual(next(iter(other.snapshot().values()))['prompts'],[self.prompt])
        bad=deepcopy(backup);bad['records'][0]['annotation']['prompts'].append({'id':'invalid'})
        before=self.server.annotations.path.read_bytes()
        with self.assertRaises(ValueError):self.server.transfers.preview_import(bad)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_legacy_data_without_prompts_is_unchanged_and_still_readable(self):
        self.patch({'note':'Old version-2 note'})
        before=self.server.annotations.path.read_bytes()
        store=Annotations(self.base/'state');library=Library(Catalog(self.base/'home'),store)
        self.assertEqual(library.snapshot()['annotations'][self.id]['note'],'Old version-2 note')
        self.assertEqual(self.server.annotations.path.read_bytes(),before)

    def test_cross_origin_prompt_writes_and_asset_boundary(self):
        before=self.server.annotations.path.read_bytes()
        self.assertEqual(self.patch({'prompts':[self.prompt],'prompts_base':[]},origin='https://attacker.invalid')[0],403)
        self.assertEqual(self.server.annotations.path.read_bytes(),before)
        self.assertEqual(self.request('GET','/prompts.js')[0],200)
        self.assertEqual(self.request('GET','/../web/prompts.js')[0],404)


if __name__=='__main__':unittest.main()
