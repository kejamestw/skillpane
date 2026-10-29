"""Synthetic concurrency, capacity and I/O-failure prompt regressions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from skillpane.server import AppServer, ANNOTATION_REQUEST_LIMIT, Handler
from skillpane.storage import MAX_BYTES
from test_catalog import fixture_root, skill


class PromptResilienceTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture_root()
        self.source=skill(self.base/'home','.agents/skills/fixture','fixture','Synthetic helper','Source sentinel')
        self.original=self.source.read_bytes()
        self.server=AppServer(port=0,home=self.base/'home',state_dir=self.base/'state')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.id=self.server.library.snapshot()['skills'][0]['id']
        self.assertEqual(self.request({'note':'Keep independent note','favorite':True,'prompts':[],'prompts_base':[]})[0],200)
        self.store=self.server.annotations

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.assertEqual(self.source.read_bytes(),self.original)

    def request(self,payload):
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=12)
        conn.request('PATCH','/api/annotation?id='+self.id,json.dumps(payload),
                     {'Origin':self.server.origin,'Content-Type':'application/json','X-Skillpane-Client':'1'})
        response=conn.getresponse();status=response.status;body=response.read();conn.close()
        return status,json.loads(body)

    def prompt(self,index=0):
        return {'id':'prompt-'+str(index),'title':'Synthetic prompt','body':'Synthetic multiline\n{{environment}}'}

    def test_twelve_simultaneous_editors_have_one_winner(self):
        barrier=threading.Barrier(12)
        before=len(list((self.base/'state/backups').glob('*.json')))
        def write(index):
            barrier.wait(timeout=10)
            return index,self.request({'prompts':[self.prompt(index)],'prompts_base':[]})[0]
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(write,range(12)))
        self.assertEqual(sum(status==200 for _,status in results),1)
        self.assertEqual(sum(status==409 for _,status in results),11)
        winner=next(index for index,status in results if status==200)
        self.assertEqual(self.store.snapshot()[self.id],{'note':'Keep independent note','favorite':True,'prompts':[self.prompt(winner)]})
        self.assertEqual(len(list((self.base/'state/backups').glob('*.json'))),before+1)

    def test_parallel_note_and_prompt_updates_merge(self):
        barrier=threading.Barrier(2)
        def write(payload):
            barrier.wait(timeout=10)
            return self.request(payload)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(write,[{'note':'Updated note'},{'prompts':[self.prompt()],'prompts_base':[]}]))
        self.assertEqual(statuses,[200,200])
        saved=self.store.snapshot()[self.id]
        self.assertEqual(saved['note'],'Updated note');self.assertEqual(saved['prompts'],[self.prompt()])

    def test_maximum_prompt_payload_and_unicode_roundtrip(self):
        prompts=[{'id':'max-'+str(i),'title':'😀'*80,'body':'😀'*4000} for i in range(20)]
        self.assertEqual(self.request({'prompts':prompts,'prompts_base':[]})[0],200)
        self.assertEqual(self.request({'prompts':prompts,'prompts_base':prompts})[0],200)
        self.assertEqual(self.store.snapshot()[self.id]['prompts'],prompts)
        before=self.store.path.read_bytes()
        invalid=[prompts+[self.prompt()], [{**self.prompt(),'title':'標'*81}],
                 [{**self.prompt(),'body':'x'*4001}], [{**self.prompt(),'body':'bad\ud800'}]]
        for payload in invalid:
            self.assertEqual(self.request({'prompts':payload,'prompts_base':prompts})[0],400)
            self.assertEqual(self.store.path.read_bytes(),before)

    def test_annotation_request_size_is_still_bounded(self):
        handler=object.__new__(Handler)
        from email.message import Message
        handler.headers=Message()
        handler.headers['Content-Length']=str(ANNOTATION_REQUEST_LIMIT+1)
        handler.rfile=unittest.mock.Mock()
        with self.assertRaises(ValueError):handler.body(ANNOTATION_REQUEST_LIMIT)
        handler.rfile.read.assert_not_called()

    def test_backup_failure_is_atomic_and_retryable(self):
        before=self.store.path.read_bytes();state=deepcopy(self.store.state)
        with patch('skillpane.storage.shutil.copy2',side_effect=OSError('Synthetic backup failure')):
            self.assertEqual(self.request({'prompts':[self.prompt()],'prompts_base':[]})[0],400)
        self.assertEqual(self.store.path.read_bytes(),before);self.assertEqual(self.store.state,state)
        self.assertEqual(self.request({'prompts':[self.prompt()],'prompts_base':[]})[0],200)

    def test_replace_failure_is_atomic_and_retryable(self):
        before=self.store.path.read_bytes();state=deepcopy(self.store.state)
        with patch('skillpane.storage.Path.replace',side_effect=OSError('Synthetic replace failure')):
            self.assertEqual(self.request({'prompts':[self.prompt()],'prompts_base':[]})[0],400)
        self.assertEqual(self.store.path.read_bytes(),before);self.assertEqual(self.store.state,state)
        self.assertEqual(self.request({'prompts':[self.prompt()],'prompts_base':[]})[0],200)

    def test_total_store_size_limit_does_not_change_state_or_backups(self):
        next_state=deepcopy(self.store.state)
        prompts=[{'id':'limit-'+str(i),'title':'Limit','body':'x'*4000} for i in range(20)]
        for i in range(60):next_state['annotations']['synthetic-'+str(i)]={'prompts':prompts}
        self.assertGreater(len(json.dumps(next_state).encode()),MAX_BYTES)
        before=self.store.path.read_bytes();state=deepcopy(self.store.state)
        backups=set((self.base/'state/backups').glob('*.json'))
        with self.assertRaises(ValueError):self.store.commit(next_state)
        self.assertEqual(self.store.path.read_bytes(),before);self.assertEqual(self.store.state,state)
        self.assertEqual(set((self.base/'state/backups').glob('*.json')),backups)


if __name__=='__main__':unittest.main()
