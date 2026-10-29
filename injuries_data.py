"""Compact mechanics, paraphrased from PHB pp. 196–200; not book prose."""

def row(lo, hi, name, days=0, *, mods=None, attrs=None, run=False, hands=False,
        pain=(), effect='', lethal='', penalty=0, instant=False, permanent=False,
        unconscious=False, special=''):
    return dict(lo=lo, hi=hi, name=name, days=days, modifiers=mods or {},
                attributeModifiers=attrs or {}, runSlow=run, noTwoHand=hands,
                damageSkills=list(pain), effect=effect, lethal=lethal,
                healingPenalty=penalty, instant=instant, permanent=permanent,
                incapacitated=unconscious, special=special)


TABLES = {
 'slash': [
  row(11,12,'Рассечённый лоб'), row(13,14,'Травма носа',1,mods={'influence':-1}),
  row(15,16,'Утрачен палец руки',1,hands=True), row(21,22,'Утрачен палец ноги',2,run=True),
  row(23,24,'Рана бедра',1,run=True), row(25,26,'Рана рта',1,mods={'influence':-2}),
  row(31,32,'Перерезанное сухожилие',2,run=True), row(33,34,'Рассечённое плечо',2,hands=True),
  row(35,36,'Травма уха',1,mods={'scout':-1}), row(41,42,'Травма глаза',2,mods={'shoot':-2,'scout':-2}),
  row(43,44,'Рана лёгкого',1,mods={'endure':-2,'move':-2},lethal='days'),
  row(45,46,'Утрачена ступня',run=True,permanent=True,lethal='days'),
  row(51,52,'Кровоточащая рана живота',1,pain=('might','move','melee'),lethal='hours'),
  row(53,54,'Рана кишечника',2,lethal='hours',special='disease',effect='Болезнь, заразность 6: Мастер разрешает проверки болезни.'),
  row(55,56,'Утрачена рука',hands=True,permanent=True,lethal='hours',penalty=-1),
  row(61,62,'Утрачена нога',run=True,permanent=True,lethal='hours',penalty=-1),
  row(63,64,'Рана горла',1,mods={'endure':-2},lethal='turns',penalty=-1),
  row(65,65,'Смертельная травма головы',instant=True), row(66,66,'Обезглавливание',instant=True)],
 'blunt': [
  row(11,12,'Оглушение'), row(13,14,'Сбитое дыхание'), row(15,16,'Сотрясение',1,mods={'scout':-2}),
  row(21,22,'Сломанный нос',1,mods={'influence':-1}), row(23,24,'Сломанные пальцы руки',1,hands=True),
  row(25,26,'Сломанные пальцы ноги',1,run=True), row(31,33,'Выбитые зубы',1,mods={'influence':-1}),
  row(34,36,'Удар в пах',1,pain=('move','melee')), row(41,43,'Сломанные рёбра',2,mods={'move':-2,'melee':-2}),
  row(44,45,'Перелом руки',2,hands=True), row(46,51,'Перелом ноги',2,run=True),
  row(52,53,'Травма глаза',2,mods={'shoot':-2,'scout':-2}),
  row(54,55,'Раздробленная ступня',3,run=True,lethal='days'),
  row(56,61,'Раздробленный локоть',hands=True,permanent=True,lethal='days'),
  row(62,63,'Раздробленное колено',run=True,permanent=True,lethal='days'),
  row(64,64,'Перелом шеи',3,unconscious=True,special='neck',effect='Паралич. Без успешного лечения в срок останется постоянным.'),
  row(65,66,'Раздробленный череп',instant=True)],
 'stab': [
  row(11,13,'Проколотое ухо'), row(14,16,'Проколотая ступня',1,run=True),
  row(21,23,'Рана кисти',1,hands=True), row(24,26,'Рана щеки',1,mods={'influence':-1}),
  row(31,33,'Проколотое бедро',2,run=True), row(34,34,'Разорванное сухожилие',3,run=True),
  row(35,41,'Проколотое плечо',2,hands=True), row(42,43,'Травма глаза',2,mods={'shoot':-2,'scout':-2}),
  row(44,45,'Рана паха',2,pain=('move','melee')), row(46,51,'Проколотое лёгкое',1,mods={'endure':-2,'move':-2},lethal='days'),
  row(52,54,'Внутреннее кровотечение',1,pain=('might','move','melee'),lethal='hours'),
  row(55,56,'Рана кишечника',2,lethal='hours',special='disease',effect='Болезнь, заразность 6: Мастер разрешает проверки болезни.'),
  row(61,61,'Артерия руки повреждена',1,hands=True,lethal='minutes',penalty=-1),
  row(62,62,'Артерия ноги повреждена',1,run=True,lethal='minutes',penalty=-1),
  row(63,63,'Проникающая рана шеи',2,mods={'endure':-2},lethal='turns',penalty=-1),
  row(64,64,'Проникающая рана черепа',instant=True), row(65,66,'Рана сердца',instant=True)],
 'horror': [
  row(11,16,'Дрожь',1,attrs={'agi':-1}), row(21,21,'Седина',permanent=True),
  row(22,24,'Тревога',1,attrs={'wit':-1}), row(25,31,'Подавленность',1,attrs={'emp':-1}),
  row(32,35,'Кошмары',1,special='nightmares',effect='Перед сном нужна успешная Проницательность, иначе сон не восстанавливает.'),
  row(36,41,'Ночной ритм',2,special='daySleep',effect='Засыпает только в светлое время суток.'),
  row(42,43,'Фобия',2,special='phobia',effect='Источник страха определяет Мастер: вблизи него Разум −1 каждый раунд.'),
  row(44,45,'Зависимость от выпивки',3,special='drink',effect='День без вина или мёда: Ловкость −1.'),
  row(46,51,'Клаустрофобия',2,special='claustrophobia',effect='В тесном замкнутом месте Разум −1 каждые 15 минут.'),
  row(52,52,'Навязчивая ложь',2,effect='Разыгрывайте постоянное искажение правды.'),
  row(53,54,'Мания преследования',2,effect='Разыгрывайте подозрения и страх преследования.'),
  row(55,55,'Стойкое заблуждение',3,effect='Обсудите с Мастером ложное убеждение персонажа.'),
  row(56,56,'Галлюцинации',3,special='hallucinations',effect='Каждую четверть суток нужна Проницательность; неудача вызывает видение по решению Мастера.'),
  row(61,62,'Изменённая личность',permanent=True,effect='Согласуйте новую черту личности с Мастером.'),
  row(63,63,'Потеря памяти',1,effect='Не помнит себя и знакомых; разыгрывайте восстановление памяти.'),
  row(64,65,'Кататония',1,unconscious=True), row(66,66,'Смертельный испуг',instant=True)],
 'other': [row(11,66,'Нетипичное повреждение',lethal='days',unconscious=True)]
}
LABELS={'slash':'Рубящая рана','stab':'Колотая рана','blunt':'Дробящая травма','horror':'Ужас','other':'Нетипичное повреждение'}

def lookup(table, result):
    if not isinstance(table,str) or table not in TABLES or type(result) is not int or result//10 not in range(1,7) or result%10 not in range(1,7):
        raise ValueError('Выберите таблицу и допустимый результат D66 (две кости D6).')
    return next(r for r in TABLES[table] if r['lo']<=result<=r['hi'])
