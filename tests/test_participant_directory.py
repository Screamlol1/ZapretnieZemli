import unittest
import test_server as support


class ParticipantDirectoryTests(unittest.TestCase):
    setUp = support.CampaignTests.setUp
    tearDown = support.CampaignTests.tearDown

    def test_disconnected_master_identity_is_public_but_credentials_are_not(self):
        room = self.game.room(self.gs['room'])
        for identity in room['identities'].values():
            identity['account'] = 'private-account-reference'
        self.game.save(room)
        self.game.sessions.pop(self.gm['token'])
        view = self.game.view(self.ps)
        master = next(p for p in view['participantDirectory'] if p['role'] == 'gm')
        self.assertEqual(master['owner'], self.gs['owner'])
        self.assertEqual(master['name'], 'Мастер')
        self.assertFalse(any(p['owner'] == self.gs['owner'] for p in view['members']))
        self.assertEqual(len(view['participantDirectory']), 2)
        for identity in view['participantDirectory']:
            self.assertEqual(set(identity), {'owner', 'name', 'role'})
        self.assertNotIn('identities', view)
        self.assertNotIn('participantDirectory', self.game.room(self.gs['room']))


if __name__ == '__main__':
    unittest.main()
