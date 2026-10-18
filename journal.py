"""Public journal metadata, added only to entries an action already published."""
import time


def entry_kind(action):
    if action == 'chat': return 'chat'
    if action in ('roll','characterRoll','characterPush'): return 'check'
    if action in ('travelResolve','travelRecover','travelConditions','holdReview','combatManual','itemWear'): return 'decision'
    if action.startswith('hold'): return 'stronghold'
    if action.startswith('travel'): return 'journey'
    if action.startswith(('item','inventory')): return 'inventory'
    if action == 'event': return 'event'
    return 'other'


def stamp_entries(room, previous, action):
    journey=room.get('journey',{})
    for entry in room['log']:
        if id(entry) not in previous:
            entry.setdefault('kind',entry_kind(action))
            entry.setdefault('day',journey.get('day',1))
            entry.setdefault('quarter',journey.get('quarter',0))
            entry.setdefault('time',time.time())
