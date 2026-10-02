import json
import gzip
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
        with r:
            raw=r.read()
            if r.headers.get('Content-Encoding')=='gzip':raw=gzip.decompress(raw)
            return r.status,dict(r.headers),json.loads(raw) if raw and r.headers.get('Content-Type','').startswith('application/json') else raw

    def test_conditional_state_tracks_presence_changes_and_checks_auth(self):
        self.serve()
        _,_,gm=self.request('/api/create',{'name':'GM'})
        _,headers,original=self.request('/api/state',Authorization=gm['token'])
        tag=headers['ETag']
        self.assertEqual(self.request('/api/state',Authorization=gm['token'],**{'If-None-Match':tag})[0],304)
        self.assertEqual(self.request('/api/state',**{'If-None-Match':tag})[0],403)
        _,_,player=self.request('/api/join',{'name':'Player','code':gm['code'],'key':gm['playerKey']})
        status,headers,current=self.request('/api/state',Authorization=gm['token'],**{'If-None-Match':tag})
        self.assertEqual(status,200);self.assertEqual(len(current['members']),2)
        self.assertNotEqual(tag,headers['ETag'])
        self.assertEqual(self.request('/api/state',Authorization=player['token'],**{'If-None-Match':headers['ETag']})[0],200)
        self.request('/api/action',{'action':'chat','text':'Update'},Authorization=player['token'])
        self.assertEqual(self.request('/api/state',Authorization=gm['token'],**{'If-None-Match':headers['ETag']})[0],200)

    def test_gzip_preserves_json_and_respects_client_preference(self):
        self.serve()
        _,_,gm=self.request('/api/create',{'name':'GM'})
        self.request('/api/action',{'action':'chat','text':'Long message. '*70},Authorization=gm['token'])
        _,plain_headers,plain=self.request('/api/state',Authorization=gm['token'])
        _,compressed_headers,compressed=self.request('/api/state',Authorization=gm['token'],**{'Accept-Encoding':'br, gzip'})
        self.assertEqual(plain,compressed)
        self.assertEqual(compressed_headers['Content-Encoding'],'gzip')
        self.assertLess(int(compressed_headers['Content-Length']),int(plain_headers['Content-Length']))
        self.assertNotIn('Content-Encoding',self.request('/api/state',Authorization=gm['token'],**{'Accept-Encoding':'gzip;q=0'})[1])

    def test_resume_after_server_session_loss_keeps_identity_and_role(self):
        self.serve()
        _,_,gm=self.request('/api/create',{'name':'GM'})
        _,_,player=self.request('/api/join',{'name':'Player','code':gm['code'],'key':gm['playerKey']})
        owner=self.request('/api/state',Authorization=player['token'])[2]['me']['owner']
        self.game.sessions.clear()
        status,_,resumed=self.request('/api/resume',{'code':gm['code'],'resume':player['resume'],'role':'gm','name':'Spoofed'})
        self.assertEqual(status,200);self.assertEqual(resumed['role'],'player');self.assertIsNone(resumed['gmKey'])
        me=self.request('/api/state',Authorization=resumed['token'])[2]['me']
        self.assertEqual(me,{'owner':owner,'role':'player','name':'Player'})
        self.assertEqual(self.request('/api/resume',{'code':gm['code'],'resume':'wrong'})[0],403)
        self.assertEqual(self.request('/api/resume',{'code':gm['code'],'resume':gm['resume']})[2]['role'],'gm')

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
