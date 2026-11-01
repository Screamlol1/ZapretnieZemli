import copy
import unittest
import test_server as support
from visual_appearance import validate_visual

VISUAL=dict(body='slim',cloak='#176963',cloth='#a37942',skin='#c79b73',hair='#513120',monster='beast')

class AppearanceTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def test_legacy_optional_layers_and_strict_bounds(self):
        self.assertEqual(validate_visual(VISUAL),VISUAL)
        for change in ({'hairStyle':'https://example/a.png'},{'body':False},{'cloak':'#123456<script>'},{'image':'secret.png'},{'mainHand':['axe']}):
            with self.assertRaises(ValueError):validate_visual({**VISUAL,**change})

    def test_owner_can_save_layers_and_resume_without_affecting_rules(self):
        cid=self.make_pc()['id'];before=copy.deepcopy(next(c for c in self.game.view(self.ps)['characters'] if c['id']==cid))
        visual={**VISUAL,'hairStyle':'braid','beard':'short','outfit':'mail','headwear':'helmet','mainHand':'axe','offHand':'shield','direction':'left'}
        after=self.game.action(self.ps,dict(action='visual',id=cid,visual=visual))['characters'][0]
        self.assertEqual(after['visual'],visual);self.assertEqual(after['sheet'],before['sheet']);self.assertEqual(after['runtime'],before['runtime'])
        other=self.game.login(dict(name='Гость',code=self.gm['code'],key=self.gm['playerKey']));ss=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.game.action(ss,dict(action='visual',id=cid,visual=VISUAL))
        from server import Game
        self.game.db.close();self.game=Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(next(c for c in self.game.view(self.ps)['characters'] if c['id']==cid)['visual'],visual)

if __name__=='__main__':unittest.main()
