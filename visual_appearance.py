"""Bounded cosmetic appearance schema, shared by campaigns and adventure packs."""
import re

BASE={'body','cloak','cloth','skin','hair','monster'}
CHOICES={
    'style':('painted','miniature'),
    'body':('slim','broad'), 'monster':('spider','reptile','beast','horned'),
    'hairStyle':('short','long','braid','shaved','crest'),
    'beard':('none','short','full','braided'),
    'outfit':('leather','robe','mail'), 'headwear':('none','hood','helmet'),
    'mainHand':('auto','none','sword','axe','spear','bow','crossbow','staff','dagger','mace'),
    'offHand':('auto','none','shield','torch'), 'direction':('right','left'),
}


def validate_visual(value):
    """Accept legacy six-field saves and optional new layers; reject extra keys."""
    if not isinstance(value,dict) or not BASE.issubset(value) or set(value)-BASE-set(CHOICES):
        raise ValueError('Некорректная внешность.')
    for key,allowed in CHOICES.items():
        if key in value and (not isinstance(value[key],str) or value[key] not in allowed):
            raise ValueError('Неизвестный элемент внешности.')
    for key in ('cloak','cloth','skin','hair'):
        if not isinstance(value[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value[key]):
            raise ValueError('Некорректный цвет.')
    return value.copy()
