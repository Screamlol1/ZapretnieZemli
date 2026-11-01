import copy
import json
import random
import re
import unittest
from pathlib import Path
import test_server as support
from location_maps import generate as plan, settings
from settlement_population import DATA, ACTIONS, COMMUNITY_KINS, generate, feature_tags, public_population
from save_points import capture


class SettlementPopulationGeneratorTests(unittest.TestCase):
    def map(self):
        return dict(id='map',kind='settlement',source=dict(kind='library'),**plan(settings(dict(kind='settlement',seed='buildings'))))

    def test_seeded_count_modes_and_kins_without_geometry_changes(self):
        for mode in DATA['modes']:
            for kin in DATA['kins']:
                with self.subTest(mode=mode,kin=kin):
                    a=self.map();b=copy.deepcopy(a);geometry=copy.deepcopy(a)
                    state=random.getstate()
                    generate({},a,dict(count=37,seed='fixed-population',kin=kin,mode=mode))
                    generate({},b,dict(count=37,seed='fixed-population',kin=kin,mode=mode))
                    self.assertEqual(a,b)
                    self.assertEqual(random.getstate(),state)
                    self.assertEqual({k:v for k,v in a.items() if k!='population'},geometry)
                    pop=a['population'];self.assertEqual(len(pop['residents']),37)
                    self.assertEqual(len({r['id'] for r in pop['residents']}),37)
                    households={h['id'] for h in pop['households']}
                    self.assertTrue(all(r['householdId'] in households and r['kin']==kin for r in pop['residents']))
                    for hid in households:
                        names=[r['name'] for r in pop['residents'] if r['householdId']==hid]
                        self.assertEqual(len(names),len(set(names)),'Names inside one generated household must be distinct')
                    self.assertTrue(all(not r['revealed'] for r in pop['residents']))
                    self.assertTrue(all(h['homeFeatureId'] for h in pop['households']))
                    if mode in ('guards','artisans','rulers'):
                        self.assertEqual({r['role'] for r in pop['residents']},{dict(guards='guard',artisans='artisan',rulers='ruler')[mode]})
                    elif kin not in COMMUNITY_KINS:
                        self.assertTrue(any(r['ageGroup']=='child' and r['familyRole']=='child' for r in pop['residents']))
                    if kin in COMMUNITY_KINS:
                        self.assertTrue(all(r['ageGroup']=='adult' and r['familyRole']=='member' for r in pop['residents']))
                        self.assertTrue(all(h['name'].startswith('Дом ') for h in pop['households']))

    def test_communities_do_not_impose_biological_parentage_or_restrict_authored_families(self):
        from settlement_population import resident_save
        for kin in COMMUNITY_KINS:
            m=self.map();generate({},m,dict(count=12,seed='community',kin=kin,mode='families'))
            resident=m['population']['residents'][0]
            self.assertNotIn(resident['familyRole'],('parent','partner','child'))
            # An explicitly authored adoption or exceptional story remains valid.
            resident_save(m,dict(id=resident['id'],ageGroup='child',familyRole='child',description='Приёмный ребёнок; история задана Мастером.'))
            changed=next(r for r in m['population']['residents'] if r['id']==resident['id'])
            self.assertEqual(changed['ageGroup'],'child')
            self.assertEqual(changed['familyRole'],'child')

    def test_maximum_and_explicit_append_preserve_manual_records(self):
        m=self.map();generate({},m,dict(count=10,seed='one',mode='families'))
        pop=m['population'];pop['residents'][0].update(name='Авторское имя',gmNote='Не потерять')
        pop['households'][0]['note']='Авторский дом'
        before=copy.deepcopy(pop)
        generate({},m,dict(count=390,seed='two',mode='guards',append=True))
        self.assertEqual(len(m['population']['residents']),400)
        self.assertEqual(m['population']['residents'][:10],before['residents'])
        self.assertEqual(m['population']['households'][:len(before['households'])],before['households'])
        self.assertEqual(len({r['id'] for r in m['population']['residents']}),400)
        house_names=[h['name'].casefold() for h in m['population']['households']]
        self.assertEqual(len(house_names),len(set(house_names)),'Append must not reuse existing household names')
        for data in (dict(count=1,append=True),dict(count=1),dict(count=401,replace=True),dict(count=True,replace=True),dict(count=2.5,replace=True),dict(count=0,replace=True),dict(count=1,append=True,replace=True)):
            with self.subTest(data=data),self.assertRaises(ValueError):generate({},m,data)
        generate({},m,dict(count=1,seed='new',mode='rulers',replace=True))
        self.assertEqual(len(m['population']['residents']),1)

    def test_large_settlement_house_names_are_distinct_and_append_keeps_manual_names(self):
        m=self.map();generate({},m,dict(count=380,seed='many-families',kin='human',mode='families'))
        m['population']['households'][0]['name']='Семья мастера Глина'
        before=copy.deepcopy(m['population']['households'])
        generate({},m,dict(count=20,seed='more-families',kin='human',mode='families',append=True))
        self.assertEqual(len(m['population']['residents']),400)
        self.assertEqual(m['population']['households'][:len(before)],before)
        names=[h['name'].casefold() for h in m['population']['households']]
        self.assertEqual(len(names),len(set(names)))
        self.assertTrue(any(' · 2' in name for name in names))

    def test_roles_use_existing_appropriate_buildings(self):
        m=self.map();generate({},m,dict(count=25,seed='roles',mode='mixed',kin='human'))
        features={f['id']:f for f in m['features']};houses={h['id']:h for h in m['population']['households']}
        rulers=[r for r in m['population']['residents'] if r['role']=='ruler']
        self.assertTrue(rulers)
        for r in rulers:self.assertIn('ruler',feature_tags(features[houses[r['householdId']]['homeFeatureId']]))
        m=self.map();generate({},m,dict(count=6,seed='craft',mode='artisans',kin='human'))
        self.assertTrue(all('artisan' in feature_tags(features[r['workplaceFeatureId']]) for r in m['population']['residents']))
        self.assertEqual({r['occupation'] for r in m['population']['residents']},{'Кузнец'})

    def test_specialized_new_jobs_never_replace_manual_occupations(self):
        from settlement_population import assign
        m=self.map();generate({},m,dict(count=6,seed='craft',mode='artisans',kin='human'))
        old=m['population']['residents'][0];old.update(occupation='Смотритель семейного музея',workplaceFeatureId='')
        old_id=old['id'];assign(m)
        self.assertEqual(old['occupation'],'Смотритель семейного музея')
        generate({},m,dict(count=4,seed='apprentices',mode='artisans',kin='human',append=True))
        self.assertEqual(next(r for r in m['population']['residents'] if r['id']==old_id)['occupation'],'Смотритель семейного музея')
        self.assertTrue(all(r['occupation']=='Кузнец' for r in m['population']['residents'][-4:]))

    def test_new_saurian_artisans_use_suitable_names_and_nonmetal_home_crafts(self):
        from settlement_population import SAURIAN_CRAFTS
        self.assertTrue(all(not re.search('[иояёыюэ]',name.lower()) for name in DATA['kins']['saurian']['names']))
        m=self.map();generate({},m,dict(count=12,seed='marsh',mode='artisans',kin='saurian'))
        households={h['id']:h for h in m['population']['households']}
        smithy=next(f['id'] for f in m['features'] if f.get('baseLabel')=='Кузница')
        for resident in m['population']['residents']:
            self.assertIn(resident['occupation'],SAURIAN_CRAFTS)
            self.assertEqual(resident['workplaceFeatureId'],households[resident['householdId']]['homeFeatureId'])
            self.assertNotEqual(resident['workplaceFeatureId'],smithy)
        # An exceptional resident written by the GM is never normalized away.
        m['population']['residents'][0].update(occupation='Чеканщик по истории Мастера',workplaceFeatureId=smithy)
        old=copy.deepcopy(m['population']['residents'])
        generate({},m,dict(count=4,seed='new-marsh',mode='artisans',kin='saurian',append=True))
        self.assertEqual(m['population']['residents'][:12],old)

    def test_default_count_uses_workshop_size(self):
        for key,expected in (('outpost',12),('hamlet',40),('village',180)):
            m=self.map();m['source']=dict(kind='workshop',id='draft')
            room=dict(workshop=[dict(id='draft',fields=dict(size=DATA['presets'][key]['label']+' · диапазон жителей'))])
            generate(room,m,dict(seed=key))
            self.assertEqual(len(m['population']['residents']),expected)

    def test_public_allowlists_secret_links_and_idempotence(self):
        pop=dict(generatorVersion=1,seed='SECRET-SEED',source='SECRET-SOURCE',
            households=[
                dict(id='h1',name='Открытая семья',homeFeatureId='home',note='Для игроков',gmNote='SECRET-HOUSE',revealed=True,secretExtra='SECRET-EXTRA'),
                dict(id='h2',name='HIDDEN-HOUSE',homeFeatureId='hidden',note='',revealed=True),
                dict(id='h3',name='UNREVEALED-HOUSE',homeFeatureId='',note='',revealed=False),
                dict(id='h4',name='Временные гости',homeFeatureId='',note='',revealed=True)],
            residents=[
                dict(id='r1',name='Открытый',householdId='h1',workplaceFeatureId='',revealed=True,gmNote='SECRET-PERSON',characterId='SECRET-ACTOR'),
                dict(id='r2',name='HIDDEN-WORK',householdId='h1',workplaceFeatureId='hidden',revealed=True),
                dict(id='r3',name='HIDDEN-HOME',householdId='h2',workplaceFeatureId='',revealed=True),
                dict(id='r4',name='UNREVEALED-PERSON',householdId='h1',workplaceFeatureId='',revealed=False),
                dict(id='r5',name='MISSING-HOUSE',householdId='missing',workplaceFeatureId='',revealed=True),
                dict(id='r6',name='Гость',householdId='h4',workplaceFeatureId='',revealed=True),
                dict(id='r7',name='UNREVEALED-FAMILY',householdId='h3',workplaceFeatureId='',revealed=True)])
        safe=public_population(pop,{'home'})
        self.assertEqual([r['id'] for r in safe['residents']],['r1','r6'])
        self.assertEqual({h['id'] for h in safe['households']},{'h1','h4'})
        text=json.dumps(safe)
        for secret in ('SECRET','HIDDEN','UNREVEALED','MISSING'):self.assertNotIn(secret,text)
        self.assertEqual(public_population(safe,{'home'}),safe)
        self.assertEqual(pop['residents'][0]['gmNote'],'SECRET-PERSON')

    def test_explicit_false_stays_hidden_even_with_public_marker(self):
        pop=dict(public=True,households=[
            dict(id='open',name='Открытый дом',homeFeatureId='home'),
            dict(id='closed',name='Скрытый дом',homeFeatureId='home',revealed=False)],residents=[
            dict(id='open',name='Открытый житель',householdId='open',workplaceFeatureId=''),
            dict(id='closed',name='Скрытый житель',householdId='open',workplaceFeatureId='',revealed=False),
            dict(id='hidden-home',name='Житель скрытого дома',householdId='closed',workplaceFeatureId='',revealed=True)])
        safe=public_population(pop,{'home'})
        self.assertEqual([r['id'] for r in safe['residents']],['open'])
        self.assertEqual([h['id'] for h in safe['households']],['open'])
        self.assertEqual(public_population(safe,{'home'}),safe)


class SettlementPopulationCampaignTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def create(self):
        return self.game.action(self.gs,dict(action='locationMapGenerate',title='Семейный Брод',settings=dict(kind='settlement',seed='settlement-test')))['locationMaps'][0]

    def act(self,m,action,**values):
        return self.game.action(self.gs,dict(action=action,id=m['id'],version=m['version'],**values))['locationMaps'][0]

    def populated(self):
        return self.act(self.create(),'locationMapPopulationGenerate',count=24,seed='town',kin='human',mode='mixed')

    def test_permissions_versions_and_malformed_actions_leave_saved_state_unchanged(self):
        m=self.populated()
        for action in ACTIONS:
            with self.subTest(action=action),self.assertRaises(PermissionError):
                self.game.action(self.ps,dict(action=action,id=m['id'],version=m['version']))
        before=self.game.view(self.gs)
        for action,values in (
            ('locationMapPopulationGenerate',dict(count=400,append=True)),
            ('locationMapPopulationGenerate',dict(count=1)),
            ('locationMapPopulationGenerate',dict(count=1,replace=True,kin='unknown')),
            ('locationMapPopulationReveal',dict(revealed='yes')),
            ('locationMapResidentDelete',dict(resident=m['population']['residents'][0]['id'])),
            ('locationMapResidentSave',dict(resident=dict(name='Чужак',householdId='missing'))),
            ('locationMapResidentSave',dict(resident=dict(name='Чужак',role='unknown'))),
            ('locationMapResidentSave',dict(resident=dict(name='Чужак',workplaceFeatureId='missing'))),
            ('locationMapHouseholdSave',dict(household=dict(name='Дом',homeFeatureId='missing')))):
            with self.subTest(action=action,values=values),self.assertRaises(ValueError):self.act(m,action,**values)
            self.assertEqual(self.game.view(self.gs),before)
        changed=self.act(m,'locationMapPopulationReveal',revealed=True)
        with self.assertRaises(ValueError):self.act(m,'locationMapPopulationAssign')
        self.assertGreater(changed['version'],m['version'])

    def test_partial_manual_saves_append_and_persistence(self):
        m=self.populated();r=m['population']['residents'][0];house=m['population']['households'][0]
        m=self.act(m,'locationMapResidentSave',resident=dict(id=r['id'],name='Мастер Глин',gmNote='PRIVATE'))
        changed=next(x for x in m['population']['residents'] if x['id']==r['id'])
        for key in set(r)-{'name','gmNote'}:self.assertEqual(changed[key],r[key])
        m=self.act(m,'locationMapHouseholdSave',household=dict(id=house['id'],note='Гостям рады',gmNote='HOUSE-PRIVATE'))
        changed_house=next(x for x in m['population']['households'] if x['id']==house['id'])
        self.assertEqual(changed_house['homeFeatureId'],house['homeFeatureId'])
        before=copy.deepcopy(m['population'])
        m=self.act(m,'locationMapPopulationGenerate',count=4,seed='extra',mode='guards',kin='dwarf',append=True)
        self.assertEqual(m['population']['residents'][:24],before['residents'])
        m=self.act(m,'locationMapResidentSave',resident=dict(name='Новый гость',kin='elf',role='merchant',public=True))
        new=m['population']['residents'][-1]
        self.assertEqual(len(m['population']['residents']),29)
        self.assertTrue(any(h['id']==new['householdId'] for h in m['population']['households']))
        self.assertNotIn('public',new)
        saved=capture(self.game.room(self.gs['room']),'campaign')
        self.assertEqual(saved['locationMaps'][0]['population'],m['population'])
        other=support.Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        try:self.assertEqual(other.view(self.gs)['locationMaps'][0]['population'],m['population'])
        finally:other.db.close()

    def test_links_survive_move_rotate_style_delete_undo_and_regeneration(self):
        m=self.populated();pop=copy.deepcopy(m['population']);fid=pop['households'][0]['homeFeatureId']
        f=next(f for f in m['features'] if f['id']==fid)
        m=self.act(m,'locationMapEdit',op='move',kind='feature',target=fid,point=[250,250])
        m=self.act(m,'locationMapEdit',op='rotate',kind='feature',target=fid,angle=45)
        m=self.act(m,'locationMapStyle',settings=dict(culture='dwarf',ground='highland',roadSurface='stone'))
        self.assertEqual(m['population'],pop)
        m=self.act(m,'locationMapEdit',op='remove',kind='feature',target=fid)
        self.assertEqual(len(m['population']['residents']),len(pop['residents']))
        self.assertTrue(all(h['homeFeatureId']!=fid for h in m['population']['households']))
        self.assertTrue(all(r['workplaceFeatureId']!=fid for r in m['population']['residents']))
        m=self.act(m,'locationMapUndo')
        self.assertEqual(m['population'],pop)
        self.assertTrue(any(f['id']==fid for f in m['features']))
        m=self.act(m,'locationMapGenerate',replace=True,title='Новый план',settings=dict(kind='settlement',seed='other'))
        self.assertEqual([r['id'] for r in m['population']['residents']],[r['id'] for r in pop['residents']])
        self.assertTrue(all(not h['homeFeatureId'] for h in m['population']['households']))
        self.assertTrue(all(not r['workplaceFeatureId'] for r in m['population']['residents']))
        m=self.act(m,'locationMapPopulationAssign')
        self.assertTrue(all(h['homeFeatureId'] for h in m['population']['households']))
        assigned=copy.deepcopy(m['population'])
        m=self.act(m,'locationMapPopulationAssign')
        self.assertEqual(m['population'],assigned)

    def test_generation_and_delete_can_be_undone(self):
        m=self.create();m=self.act(m,'locationMapPopulationGenerate',count=5,seed='undo')
        original=copy.deepcopy(m['population']);rid=original['residents'][0]['id']
        m=self.act(m,'locationMapResidentDelete',resident=rid,confirmed=True)
        self.assertEqual(len(m['population']['residents']),4)
        m=self.act(m,'locationMapUndo');self.assertEqual(m['population'],original)
        m=self.act(m,'locationMapUndo');self.assertFalse(m.get('population'))
        self.assertEqual(self.game.view(self.ps)['locationMaps'],[])

    def test_player_state_only_contains_revealed_people_and_visible_homes_workplaces(self):
        m=self.populated();self.assertEqual(self.game.view(self.ps)['locationMaps'],[])
        m=self.act(m,'locationMapReveal',revealed=True)
        self.assertEqual(self.game.view(self.ps)['locationMaps'][0]['population']['residents'],[])
        m=self.act(m,'locationMapPopulationReveal',revealed=True)
        public=self.game.view(self.ps)['locationMaps'][0]['population']
        self.assertEqual(len(public['residents']),24)
        self.assertNotIn('gmNote',json.dumps(public));self.assertNotIn('seed',public)
        r=m['population']['residents'][0];h=next(h for h in m['population']['households'] if h['id']==r['householdId'])
        hidden_home=h['homeFeatureId'];f=next(f for f in m['features'] if f['id']==hidden_home)
        m=self.act(m,'locationMapFeature',feature=f['id'],label=f['label'],note=f['note'],gmNote='SECRET-HOME',secret=True)
        public=self.game.view(self.ps)['locationMaps'][0]['population']
        self.assertNotIn(r['id'],[r['id'] for r in public['residents']])
        self.assertNotIn(hidden_home,[h.get('homeFeatureId') for h in public['households']])
        self.assertNotIn(hidden_home,[r.get('workplaceFeatureId') for r in public['residents']])
        self.assertTrue(all('revealed' not in r for r in public['residents']))
        m=self.act(m,'locationMapPopulationReveal',revealed=False)
        self.assertEqual(self.game.view(self.ps)['locationMaps'][0]['population']['households'],[])


if __name__=='__main__':unittest.main()
