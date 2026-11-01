"""Illustrations must preserve inventory state and remain separate from rules."""
import json
from pathlib import Path
import unittest
import test_server as support
from inventory_rules import ITEM_ART, validate


class InventoryArtManifestTests(unittest.TestCase):
    def test_shared_whitelist_accepts_every_image_and_rejects_external_paths(self):
        manifest=json.loads((Path(__file__).parents[1]/'public'/'inventory-art-data.json').read_text(encoding='utf-8'))
        self.assertEqual(ITEM_ART,tuple(item['id'] for item in manifest['items']))
        self.assertEqual(len(ITEM_ART),96)
        self.assertEqual(len(set(ITEM_ART)),96)
        for art in ITEM_ART:
            with self.subTest(art=art):
                item=validate(dict(name='Декоративная запись',art=art))
                self.assertEqual(item['art'],art)
                self.assertEqual(item['kind'],'gear')
                self.assertEqual(item['combatProfile'],'')
                self.assertEqual(item['bonus'],0)
        for invalid in ('../assets/private.png','https://example.com/picture.png','<script>',None,[],{}):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):validate(dict(name='Предмет',art=invalid))


class InventoryArtPersistenceTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def test_rename_preserves_catalog_identity_and_visual_override(self):
        c=self.make_pc()
        view=self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        original=next(item for item in view['items'] if item.get('catalogId'))
        renamed=dict(original,name='Именной подарок',art='lantern')
        view=self.game.action(self.gs,dict(action='itemEdit',id=original['id'],version=original['version'],item=renamed))
        updated=next(item for item in view['items'] if item['id']==original['id'])
        self.assertEqual(updated['catalogId'],original['catalogId'])
        self.assertEqual(updated['art'],'lantern')
        self.assertEqual(updated['name'],'Именной подарок')
        for key in ('kind','bonus','damage','armor','weight','quantity','combatProfile'):
            self.assertEqual(updated[key],original[key],key)
        saved=next(item for item in self.game.room(self.gs['room'])['items'] if item['id']==original['id'])
        self.assertEqual(saved,updated)

    def test_new_image_survives_split_transfer_and_reload_without_changing_properties(self):
        c=self.make_pc()
        view=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=c['id']),item=dict(name='Полевой фонарь',art='lantern',quantity=3,weight=.5,gmNote='Секретный отсек')))
        original=view['items'][-1]
        view=self.game.action(self.ps,dict(action='itemAppearance',id=original['id'],version=original['version'],art='oillamp'))
        item=next(item for item in view['items'] if item['id']==original['id'])
        self.assertEqual(item['kind'],'gear')
        self.assertEqual(item['bonus'],0)
        self.assertNotIn('gmNote',item)
        view=self.game.action(self.ps,dict(action='itemSplit',id=item['id'],version=item['version'],quantity=1))
        item=next(item for item in view['items'] if item['name']=='Полевой фонарь' and item['quantity']==1)
        self.game.action(self.gs,dict(action='itemTransfer',id=item['id'],version=item['version'],quantity=1,location=dict(kind='treasury',id='')))
        restored=support.Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        try:
            stacks=[item for item in restored.view(self.gs)['items'] if item['name']=='Полевой фонарь']
            self.assertEqual(sorted(item['quantity'] for item in stacks),[1,2])
            self.assertTrue(all(item['art']=='oillamp' and item['gmNote']=='Секретный отсек' for item in stacks))
            self.assertEqual(len([item for item in stacks if item['location']['kind']=='treasury']),1)
        finally:restored.db.close()


if __name__=='__main__':unittest.main()
