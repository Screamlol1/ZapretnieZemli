// Sound follows the already-authorized player projection; it never requests GM data.
const terrainNames={plain:'plains',road:'plains',forest:'forest',darkforest:'forest',hills:'mountain',mountain:'mountain',highmountain:'mountain',marsh:'marsh',rough:'plains',water:'water',ruin:'ruins'};
const locationNames={settlement:'settlement',camp:'camp',fortress:'settlement',ruins:'ruin',dungeon:'dungeon',cave:'cave'};
const directorTypes=new Set(['metal','footstep','monster','wolf','break','thunder','bell','blacksmith','snow-step','dice','magic']);
const ambientModes=new Set(['auto','silent','battle','wind','forest','cave','river','marsh','fire','city','tavern','rain','night']);
// The server expires these short-lived public cues. Do not compare wall clocks:
// players may have a different system time from the campaign host.
const directorCues=s=>(s.audioDirector?.cues||[]).filter(e=>typeof e.id==='string'&&e.id.length<=120&&directorTypes.has(e.type));
const visibleRolls=s=>(s.diceRolls||[]).filter(e=>typeof e.id==='string'&&(!e.private||s.me?.role==='gm'));
const scopeFor=s=>[s.id,s.me?.owner||'',s.me?.role||'player'].join(':');
function walkingCue(context,terrain=context.terrain){
 if(context.locationType||!terrain||terrain==='water')return '';
 if(context.season==='winter'&&context.terrain&&context.terrain!=='water')return 'snow-step';
 return terrain==='forest'?'footstep':'';
}
function actorVisible(s,id){const c=(s.characters||[]).find(c=>c.id===id);return !!c&&(s.me?.role==='gm'||!c.hidden);}
function publicCombatEvent(s){const e=s.combat?.event;if(!e?.id||!actorVisible(s,e.actor))return null;return s.me?.role==='gm'||e.private===false?e:null;}
function eventIds(s){const rolls=visibleRolls(s).flatMap(e=>['dice:'+e.id,'magic:'+e.id]),director=directorCues(s).map(e=>'director:'+e.id),e=publicCombatEvent(s);return e?[...rolls,...director,...['hit','magic','footstep','wolf','monster'].map(type=>'combat:'+e.id+':'+type)]:[...rolls,...director];}
export function audioContextFor(s,view='scene'){
 const p=s.journey?.position,key=p?`${p.x},${p.y}`:'',hidden=(s.mapFog?.world||[]).includes(key)&&s.me?.role!=='gm',cell=hidden?null:s.maps?.world?.[key];
 const locationId=s.scene?.map||cell?.locationMapId,location=(s.locationMaps||[]).find(m=>m.id===locationId&&(m.revealed||s.me?.role==='gm'));
 return {scope:scopeFor(s),view,terrain:hidden?'':terrainNames[cell?.terrain||'plain']||'',season:s.journey?.season||'',locationType:locationNames[location?.kind]||'',inCombat:s.combat?.phase==='combat',ambientOverride:ambientModes.has(s.audioDirector?.ambient)?s.audioDirector.ambient:'auto',eventIds:eventIds(s)};
}
export function projectedAudioFeed(){
 let scope='',revision=-1,seen=new Set(),previousPosition='';
 return (s,view='scene')=>{
  const context=audioContextFor(s,view),position=s.journey?.position?`${s.journey.position.x},${s.journey.position.y}`:'';
  if(scope!==context.scope||Number(s.revision)<revision){scope=context.scope;revision=Number(s.revision);seen=new Set(context.eventIds);previousPosition=position;return {context,events:[]};}
  const events=[],role=s.me?.role||'player',push=(id,type,privateEvent=false)=>{if(seen.has(id))return;seen.add(id);events.push({scope,id,type,private:privateEvent,role});};
  for(const cue of directorCues(s))push('director:'+cue.id,cue.type);
  const casts=new Set((s.magicCastings||[]).filter(c=>!c.private||role==='gm').map(c=>c.event)),rolls=visibleRolls(s);
  let freshMagic=false;
  for(const roll of rolls){
   const magical=casts.has(roll.id)||(roll.groups||[]).some(g=>g.kind==='magic');
   const id=(magical?'magic:':'dice:')+roll.id;
   if(!seen.has(id)){if(magical)freshMagic=true;if(magical||(roll.groups||[]).some(g=>g.values?.length))push(id,magical?'magic':'dice',!!roll.private);else seen.add(id);}
  }
  const event=publicCombatEvent(s);
  if(event){
   if(event.kind==='cast'&&event.action==='cast'&&!freshMagic)push('combat:'+event.id+':magic','magic',!!event.private);
   else if(event.kind==='cast')seen.add('combat:'+event.id+':magic');
   if((event.hitIds||[]).some(id=>actorVisible(s,id))){
    if(['slash','stab'].includes(event.action))push('combat:'+event.id+':hit','hit',!!event.private);
    else if(event.action==='monsterAttack'){
     const creature=(s.characters||[]).find(c=>c.id===event.actor&&c.kind==='monster'),name=creature?.name||'';
     const type=/(?:^|[^\p{L}])(?:wolf|wolves|волк(?:и|ов|а|у|ом|е)?)(?=$|[^\p{L}])/iu.test(name)?'wolf':/(?:^|[^\p{L}])(?:dragons?|дракон(?:ы|ов|а|у|ом|е)?)(?=$|[^\p{L}])/iu.test(name)?'monster':'';
     if(type)push('combat:'+event.id+':'+type,type,!!event.private);
    }
   }
   const actor=(s.combat?.units||[]).find(u=>u.id===event.actor);
   if(event.kind==='move'&&actor&&event.origin&&(actor.q!==event.origin.q||actor.r!==event.origin.r)){
    const cue=walkingCue(context,s.combat?.terrain?.[`${actor.q},${actor.r}`]||'plain');
    if(cue)push('combat:'+event.id+':footstep',cue,!!event.private);
   }
  }
  if(previousPosition&&position&&position!==previousPosition&&!s.journey?.mounted&&!s.journey?.vessel){const cue=walkingCue(context);if(cue)push('travel:'+s.revision+':'+position,cue);}
  previousPosition=position;revision=Number(s.revision);
  // Context changes cannot turn an old silent event into a new sound.
  for(const id of context.eventIds)seen.add(id);
  if(seen.size>1500)seen=new Set([...seen].slice(-1000));
  return {context,events};
 };
}
