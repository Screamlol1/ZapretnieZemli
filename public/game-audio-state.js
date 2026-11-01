// Sound follows the already-authorized player projection; it never requests GM data.
const terrainNames={plain:'plains',road:'plains',forest:'forest',darkforest:'forest',hills:'mountain',mountain:'mountain',highmountain:'mountain',marsh:'marsh',rough:'marsh',water:'water',ruin:'ruins'};
const locationNames={settlement:'settlement',camp:'camp',fortress:'settlement',ruins:'ruin',dungeon:'dungeon',cave:'cave'};
const visibleRolls=s=>(s.diceRolls||[]).filter(e=>typeof e.id==='string'&&(!e.private||s.me?.role==='gm'));
const scopeFor=s=>[s.id,s.me?.owner||'',s.me?.role||'player'].join(':');
function actorVisible(s,id){const c=(s.characters||[]).find(c=>c.id===id);return !!c&&(s.me?.role==='gm'||!c.hidden);}
function publicCombatEvent(s){const e=s.combat?.event;if(!e?.id||!actorVisible(s,e.actor))return null;return s.me?.role==='gm'||e.private===false?e:null;}
function eventIds(s){const rolls=visibleRolls(s).flatMap(e=>['dice:'+e.id,'magic:'+e.id]),e=publicCombatEvent(s);return e?[...rolls,...['hit','magic','footstep','wolf','monster'].map(type=>'combat:'+e.id+':'+type)]:rolls;}
export function audioContextFor(s,view='scene'){
 const p=s.journey?.position,key=p?`${p.x},${p.y}`:'',hidden=(s.mapFog?.world||[]).includes(key)&&s.me?.role!=='gm',cell=hidden?null:s.maps?.world?.[key];
 const locationId=s.scene?.map||cell?.locationMapId,location=(s.locationMaps||[]).find(m=>m.id===locationId&&(m.revealed||s.me?.role==='gm'));
 return {scope:scopeFor(s),view,terrain:hidden?'':terrainNames[cell?.terrain||'plain']||'',season:s.journey?.season||'',locationType:locationNames[location?.kind]||'',inCombat:s.combat?.phase==='combat',eventIds:eventIds(s)};
}
export function projectedAudioFeed(){
 let scope='',revision=-1,seen=new Set(),previousPosition='';
 return (s,view='scene')=>{
  const context=audioContextFor(s,view),position=s.journey?.position?`${s.journey.position.x},${s.journey.position.y}`:'';
  if(scope!==context.scope||Number(s.revision)<revision){scope=context.scope;revision=Number(s.revision);seen=new Set(context.eventIds);previousPosition=position;return {context,events:[]};}
  const events=[],role=s.me?.role||'player',push=(id,type,privateEvent=false)=>{if(seen.has(id))return;seen.add(id);events.push({scope,id,type,private:privateEvent,role});};
  const casts=new Set((s.magicCastings||[]).filter(c=>!c.private||role==='gm').map(c=>c.event)),rolls=visibleRolls(s);
  let freshMagic=false;
  for(const roll of rolls){
   const magical=casts.has(roll.id)||(roll.groups||[]).some(g=>g.kind==='magic');
   const id=(magical?'magic:':'dice:')+roll.id;
   if(!seen.has(id)){if(magical)freshMagic=true;if(magical||(roll.groups||[]).some(g=>g.values?.length))push(id,magical?'magic':'dice',!!roll.private);else seen.add(id);}
  }
  const event=publicCombatEvent(s);
  if(event){
   if(event.kind==='cast'&&!freshMagic)push('combat:'+event.id+':magic','magic',!!event.private);
   else if(event.kind==='cast')seen.add('combat:'+event.id+':magic');
   if((event.hitIds||[]).some(id=>actorVisible(s,id))){
    if(['slash','stab'].includes(event.action))push('combat:'+event.id+':hit','hit',!!event.private);
    else if(event.action==='monsterAttack'){
     const creature=(s.characters||[]).find(c=>c.id===event.actor&&c.kind==='monster'),name=creature?.name||'';
     const type=/wolf|волк/i.test(name)?'wolf':/dragon|дракон/i.test(name)?'monster':'';
     if(type)push('combat:'+event.id+':'+type,type,!!event.private);
    }
   }
   const actor=(s.combat?.units||[]).find(u=>u.id===event.actor);
   if(event.kind==='move'&&actor&&event.origin&&(actor.q!==event.origin.q||actor.r!==event.origin.r))push('combat:'+event.id+':footstep',context.season==='winter'&&!context.locationType&&context.terrain&&context.terrain!=='water'?'snow-step':'footstep',!!event.private);
  }
  if(previousPosition&&position&&position!==previousPosition&&context.terrain)push('travel:'+s.revision+':'+position,context.season==='winter'&&context.terrain!=='water'?'snow-step':'footstep');
  previousPosition=position;revision=Number(s.revision);
  if(seen.size>1500)seen=new Set([...seen].slice(-1000));
  return {context,events};
 };
}
