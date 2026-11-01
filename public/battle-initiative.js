// Ten physical cards, independent of the number of figures on the field.
export const MAX_COMBATANTS=40;
export const npcSignature=u=>JSON.stringify([u.team,u.kind,u.maxStr,u.maxAgi,u.maxWits,u.maxEmp,u.melee,u.shoot,u.move,u.weapon,u.weaponStats,u.maxArmor,u.armor,u.gear,u.shield,u.shieldMaximum,u.talents,u.path,u.pathRank,u.paths]);
export function initiativeSlots(b){
 const slots=[],groups=new Map();
 for(const u of b.units){
  const group=u.initiativeGroup??'',count=u.activations??1;
  if(typeof group!=='string'||group.length>40||!Number.isInteger(count)||count<1||count>3||count>1&&!u.monster)throw Error('Группа: до 40 символов; чудовище получает 1–3 активации.');
  if(group&&u.monster)throw Error('Чудовище получает отдельные карты, его нельзя объединить в группу.');
  if(group){
   const key=u.team+':'+group,prior=groups.get(key);
   if(prior){
    const leader=b.units.find(v=>v.id===prior.members[0]);
    if((leader.kind==='pc')!==(u.kind==='pc'))throw Error('Герои и ПВ объединяются в разные группы.');
    if(u.kind==='pc'&&!b.settings.sharedHeroInitiative)throw Error('Общая карта героев — дополнительное правило; включите его явно.');
    if(b.phase==='setup'&&u.kind!=='pc'&&npcSignature(leader)!==npcSignature(u))throw Error('Общая карта ПВ доступна только бойцам одного отряда с одинаковыми параметрами и снаряжением.');
    prior.members.push(u.id);continue;
   }
   const slot={key:'group:'+key,group,members:[u.id],activation:1};groups.set(key,slot);slots.push(slot);
  }else for(let i=1;i<=count;i++)slots.push({key:u.id+':'+i,group:'',members:[u.id],activation:i});
 }
 return slots;
}
export function sortInitiative(b){
 if(!b.initiativeSlots){b.order=[...b.units].sort((a,z)=>a.initiative-z.initiative).map(u=>u.id);return;}
 b.activationOrder=[...b.initiativeSlots].sort((a,z)=>a.card-z.card).flatMap(slot=>slot.members.map(unit=>({unit,card:slot.card,group:slot.group,activation:slot.activation,key:slot.key})));
 b.order=b.activationOrder.map(a=>a.unit);
 for(const u of b.units){u.initiativeCards=b.initiativeSlots.filter(s=>s.members.includes(u.id)).map(s=>s.card).sort((a,z)=>a-z);u.initiative=u.initiativeCards[0];}
}
export function assignInitiativeCard(b,slot,card){slot.card=card;for(const id of slot.members){const u=b.units.find(u=>u.id===id);u.initiative=Math.min(u.initiative||11,card);}}
export function validateInitiative(b){
 initiativeSlots(b);
 if(b.initiativeSlots){
  const expected=initiativeSlots(b),slots=b.initiativeSlots;
  if(!Array.isArray(slots)||slots.length!==expected.length||slots.some(s=>{const e=expected.find(e=>e.key===s.key);return !e||JSON.stringify([...s.members].sort())!==JSON.stringify([...e.members].sort())||s.activation!==e.activation||s.group!==e.group||s.card!==undefined&&(!Number.isInteger(s.card)||s.card<1||s.card>10);})||new Set(slots.filter(s=>s.card).map(s=>s.card)).size!==slots.filter(s=>s.card).length)throw Error('Некорректные карты инициативы.');
  if(b.phase!=='setup'){
   const order=[...slots].sort((a,z)=>a.card-z.card).flatMap(s=>s.members.map(unit=>({unit,card:s.card,group:s.group,activation:s.activation,key:s.key})));
   if(slots.some(s=>!s.card)||JSON.stringify(order)!==JSON.stringify(b.activationOrder)||JSON.stringify(order.map(a=>a.unit))!==JSON.stringify(b.order))throw Error('Очередь не соответствует картам инициативы.');
  }
 }
}
