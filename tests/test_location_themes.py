import copy
import unittest
import test_server as support
from location_maps import generate, settings, KINDS
from location_themes import CULTURES, ART_IDS


class CultureTerrainTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def test_every_culture_and_template_is_deterministic_and_bounded(self):
        self.assertEqual(len(CULTURES),12)
        self.assertEqual(len(set(ART_IDS)),36)
        for c in CULTURES:
            for kind in KINDS:
                cfg=settings(dict(culture=c['id'],kind=kind,seed='culture-test',size='small'))
                m=generate(cfg);self.assertEqual(m,generate(cfg))
                self.assertEqual(m['ground'],c['ground'])
                for f in m['features']:
                    self.assertGreaterEqual(f['x'],0);self.assertGreaterEqual(f['y'],0)
                    self.assertLessEqual(f['x']+f['w'],m['width']);self.assertLessEqual(f['y']+f['h'],m['height'])
                if kind=='settlement':
                    f=next(f for f in m['features'] if f.get('themeRole')=='home')
                    self.assertEqual(f['w']*m['metersPerCell']/m['cellSize'],c['assets'][0]['width'])

    def test_restyle_preserves_manual_work_visibility_and_undo(self):
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Торг',settings=dict(culture='saurian',seed='style')))['locationMaps'][-1]
        m=self.game.action(self.gs,dict(action='locationMapFeature',id=m['id'],version=m['version'],feature=m['features'][0]['id'],label='Имя Мастера',note='Видимое',gmNote='PRIVATE',secret=True,art='ogre-home'))['locationMaps'][-1]
        m=self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))['locationMaps'][-1]
        before=copy.deepcopy(m)
        command=dict(action='locationMapStyle',id=m['id'],version=m['version'],settings=dict(culture='elf',ground='ash',roadSurface='planks'))
        with self.assertRaises(PermissionError):self.game.action(self.ps,command)
        m=self.game.action(self.gs,command)['locationMaps'][-1]
        self.assertEqual(m['features'][0],before['features'][0]);self.assertEqual(m['paths'],before['paths'])
        self.assertEqual([(f['x'],f['y'],f['w'],f['h']) for f in m['features']],[(f['x'],f['y'],f['w'],f['h']) for f in before['features']])
        self.assertTrue(m['revealed']);self.assertEqual(m['ground'],'ash');self.assertEqual(m['culture'],'elf')
        with self.assertRaises(ValueError):self.game.action(self.gs,command)
        public=self.game.view(self.ps)['locationMaps'][0]
        self.assertNotIn('settings',public);self.assertNotIn('PRIVATE',str(public));self.assertEqual(public['culture'],'elf')
        restored=self.game.action(self.gs,dict(action='locationMapUndo',id=m['id'],version=m['version']))['locationMaps'][-1]
        for k in ('features','paths','culture','ground','roadSurface','settings'):self.assertEqual(restored[k],before[k])
        self.assertGreater(restored['version'],m['version'])

    def test_unknown_styles_are_rejected_and_legacy_defaults_work(self):
        for raw in ({'culture':'<script>'},{'culture':[]},{'ground':'bad'},{'roadSurface':'bad'}):
            with self.assertRaises(ValueError):settings(raw)
        old=settings(dict(seed='old'));self.assertEqual(old['culture'],'neutral')
        m=generate(old);self.assertEqual(m['features'][0]['label'],m['features'][0]['baseLabel'])


if __name__=='__main__':unittest.main()
