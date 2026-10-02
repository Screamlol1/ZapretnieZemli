import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game,RequestLimits,ThreadingHTTPServer,make_handler


class PublicTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.game=Game(self.root/'test.sqlite',reference_root=self.root/'assets')
        self.http=None

    def tearDown(self):
        if self.http:self.http.shutdown();self.http.server_close();self.thread.join()
        self.game.db.close();self.tmp.cleanup()

    def serve(self,**options):
        self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.game,public_test=True,**options))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def request(self,path,data=None,**headers):
        if data is not None:headers['Content-Type']='application/json'
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:r=urlopen(req,timeout=5)
        except HTTPError as e:r=e
        with r:return r.status,dict(r.headers),json.load(r) if r.headers['Content-Type'].startswith('application/json') else r.read()

    def test_rate_windows_isolate_addresses_and_operations_and_expire(self):
        limits=RequestLimits({'auth':(2,60),'write':(4,60),'read':(10,60)})
        with patch('server.time.monotonic',return_value=100):
            self.assertEqual(limits.retry_after('a','auth'),0)
            self.assertEqual(limits.retry_after('a','auth'),0)
            self.assertGreater(limits.retry_after('a','auth'),0)
            self.assertEqual(limits.retry_after('b','auth'),0)
            self.assertEqual(limits.retry_after('a','read'),0)
        with patch('server.time.monotonic',return_value=161):
            self.assertEqual(limits.retry_after('a','auth'),0)
            self.assertEqual(len(limits.windows),1)

    def test_http_throttling_has_retry_after_and_does_not_mix_visitors(self):
        self.serve(limits=RequestLimits({'auth':(2,60),'write':(10,60),'read':(2,60)}))
        for _ in range(2):self.assertEqual(self.request('/api/health',**{'CF-Connecting-IP':'visitor-a'})[0],200)
        status,headers,body=self.request('/api/health',**{'CF-Connecting-IP':'visitor-a'})
        self.assertEqual(status,429);self.assertGreater(int(headers['Retry-After']),0)
        self.assertEqual(self.request('/api/health',**{'CF-Connecting-IP':'visitor-b'})[0],200)
        self.assertEqual(self.request('/api/create',{'name':'GM'},**{'CF-Connecting-IP':'visitor-a'})[0],200)

    def test_campaign_cap_and_authenticated_views_and_origin_validation(self):
        self.serve(max_rooms=1)
        status,_,auth=self.request('/api/create',{'name':'GM'})
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/create',{'name':'Another GM'})[0],400)
        self.assertEqual(self.request('/api/state')[0],403)
        self.assertEqual(self.request('/api/state',Authorization=auth['token'])[0],200)
        self.assertEqual(self.request('/api/join',{'name':'Player','code':auth['code'],'key':auth['playerKey']},Origin='https://different.example')[0],403)
        self.assertEqual(self.request('/api/join',{'name':'Player','code':auth['code'],'key':auth['playerKey']})[0],200)

    def test_private_files_stay_outside_static_routes(self):
        self.serve()
        for path in ('/server.py','/campaigns.sqlite','/.runtime/test.sqlite','/../server.py','/local-assets/forbidden-lands.jpg'):
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/api/health')[2],{'ok':True,'publicTest':True})


if __name__=='__main__':unittest.main()
