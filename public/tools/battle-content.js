export const BATTLE_CHARACTERS=[
 {id:'a1',name:'Арна',weapon:'sword',str:4,agi:3,melee:3,shoot:1,move:3,armor:3,shield:1,team:'A'},
 {id:'a2',name:'Тор',weapon:'spear',str:4,agi:3,melee:2,shoot:1,move:2,armor:2,team:'A'},
 {id:'a3',name:'Ильва',weapon:'bow',str:3,agi:4,melee:1,shoot:3,move:3,armor:2,team:'A'},
 {id:'b1',name:'Грим',weapon:'axe',str:5,agi:2,melee:3,shoot:0,move:2,armor:3,team:'B'},
 {id:'b2',name:'Сив',weapon:'crossbow',str:3,agi:3,melee:1,shoot:3,move:2,armor:2,team:'B'},
 {id:'b3',name:'Варг',weapon:'dagger',str:3,agi:4,melee:3,shoot:1,move:3,armor:2,team:'B'},
 {id:'c1',name:'Эйра',weapon:'longbow',str:3,agi:5,melee:1,shoot:3,move:3,armor:2},
 {id:'c2',name:'Рагнар',weapon:'greatsword',str:5,agi:2,melee:3,shoot:0,move:2,armor:4},
 {id:'c3',name:'Брин',weapon:'mace',str:4,agi:3,melee:3,shoot:1,move:2,armor:3,shield:1},
 {id:'c4',name:'Хальд',weapon:'halberd',str:4,agi:3,melee:3,shoot:0,move:3,armor:2},
 {id:'c5',name:'Морвен',weapon:'staff',str:3,agi:3,melee:1,shoot:0,move:2,armor:0,magic:{blood:2,death:2},wp:6}
];
const terrain=entries=>Object.fromEntries(entries.map(([q,r,type])=>[`${q},${r}`,type]));
export const BATTLE_MAPS={
 road:{name:'Старый тракт',description:'Лесная дорога с руинами стены',terrain:terrain([[6,2,'wall'],[6,3,'wall'],[6,4,'wall'],[4,5,'forest'],[5,5,'forest'],[7,6,'forest'],[8,1,'rough'],[8,2,'rough']])},
 ruins:{name:'Разрушенная крепость',description:'Два прохода, каменные стены и осыпавшийся двор',terrain:terrain([...Array.from({length:7},(_,i)=>[5,i+1,'wall']).filter(x=>x[1]!==3),...Array.from({length:6},(_,i)=>[8,i+1,'wall']).filter(x=>x[1]!==5),[6,3,'rough'],[7,3,'rough'],[7,5,'rough'],[6,6,'rough'],[4,7,'forest']])},
 grove:{name:'Лесная засада',description:'Группы деревьев, валуны и сложный грунт',terrain:terrain([[4,1,'forest'],[4,2,'forest'],[5,3,'forest'],[6,4,'forest'],[7,5,'forest'],[8,6,'forest'],[8,7,'forest'],[6,1,'wall'],[6,6,'wall'],[8,2,'wall'],[5,5,'rough'],[7,3,'rough'],[9,4,'rough']])}
};
export const BATTLE_SPELLS={
 immolate:{name:'Воспламенение',discipline:'blood',rank:2,range:2,ingredient:'torch',ingredientName:'Факел / открытый огонь',description:'Урон Телосложению = силе эффекта, без брони; затем 1 урона в начале каждого раунда, пока цель не потушит огонь.'},
 doom:{name:'Рука рока',discipline:'death',rank:2,range:2,ingredient:'hand',ingredientName:'Отсечённая рука',description:'Урон Телосложению = силе эффекта. Дополнительная 1 СВ расширяет дальность до короткой; она не увеличивает силу эффекта.'},
 firewalker:{name:'Огнеход',discipline:'blood',rank:1,range:0,ingredient:'blood',ingredientName:'Капля крови',description:'На четверть суток защищает самого колдуна от огня, жары и холода. В этом бою предотвращает урон от горения.'}
};
export function mishapDescription(n){if(n<=13)return 'Свидетели распространяют слухи: известность +1.';if(n<=15)return 'Возникает голод.';if(n<=21)return 'Возникает жажда.';if(n<=23)return 'Нарушен сон на D6 дней.';if(n<=25)return 'Ловкость −1.';if(n<=31)return 'Телосложение −1.';if(n<=33)return 'Эмпатия −1.';if(n<=35)return 'Разум −1.';if(n<=41)return 'Магическая болезнь; заразность 2D6. Ведущий определяет заражение.';if(n<=45)return 'Заклинание задевает дополнительную непреднамеренную цель. Выберите её ниже.';if(n===46)return 'Внешность навсегда меняется — определяет ведущий.';if(n===51)return 'Ослепление на сутки — ведущий разрешает действия в темноте.';if(n<=55)return 'Критическая психическая травма — бросок по таблице ведущего.';if(n===56)return 'Критическая тупая травма — бросок по таблице ведущего.';if(n===61)return 'В течение четверти суток появляется демон — определяет ведущий.';if(n<=65)return 'Обратный эффект: заклинание поражает колдуна. Применено автоматически.';return 'Колдун унесён в другое измерение и выбывает. Применено автоматически.';}
