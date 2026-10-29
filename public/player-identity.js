// Stable heraldry identifies an owner across tabs, reconnects and characters.
export const escapeIdentity=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors=['#80b5ac','#dfba75','#a9acd7','#dca48a','#9fbd78','#c69dbd','#91bbd0','#d1ba91','#acae82','#d59b9b'];
const marks=['M12 4l6 8-6 8-6-8Z','M6 7h12l-6 14Zm6-4v4','M4 15l8-10 8 10-8 5Z','M6 18 18 6M6 6l12 12M12 3v18','M5 7q7-6 14 0v8q-7 8-14 0Z','M12 3 5 12h5v9l9-12h-5Z'];
export function identityColor(id){let n=2166136261;for(const c of String(id||'guest'))n=Math.imul(n^c.codePointAt(0),16777619);return {color:colors[(n>>>0)%colors.length],mark:marks[(n>>>0)%marks.length]};}
export function identityMarkup(identity={},options={}){
 const {id='',name='Участник',role='player',characterId=''}=identity,{color,mark}=identityColor(id),initials=name.trim().split(/\s+/).filter(Boolean).slice(0,2).map(w=>Array.from(w)[0]).join('').toUpperCase()||'?';
 const path=role==='gm'?'M3 7l4 3 5-6 5 6 4-3-2 12H5Z':mark;
 return `<span class="player-identity ${options.size==='small'?'identity-small':''} ${options.current?'identity-current':''}" style="--identity-color:${color}" title="${escapeIdentity(name)}${role==='gm'?' · Мастер':''}" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="${path}"/></svg>${characterId?`<img data-sprite="${escapeIdentity(characterId)}" alt="">`:`<b>${escapeIdentity(initials)}</b>`}${role==='gm'?'<i>М</i>':''}</span>`;
}
export function currentMasterIdentity(state){
 const active=(state.members||[]).find(p=>p.role==='gm')||(state.me?.role==='gm'?state.me:null);
 const known=(state.participantDirectory||[]).findLast(p=>p.role==='gm')||(state.owners||[]).findLast(p=>p.role==='gm');
 const master=active||known;
 return {id:master?.owner||'gm',owner:master?.owner||'gm',role:'gm',name:master?.name||'Мастер'};
}
export function controllerIdentity(state,character){
 const directory=[...(state.members||[]),...(state.me?[state.me]:[]),...(state.participantDirectory||[]),...(state.owners||[])];
 const owner=character?.owner,player=directory.find(p=>p.owner===owner);
 if(character?.kind!=='pc'||player?.role==='gm')return {...currentMasterIdentity(state),characterId:character?.id||''};
 const cycle=(state.journey?.cycleParticipants||[]).find(p=>p.owner===owner);
 return {id:owner||character?.id||'guest',owner,role:'player',name:player?.name||cycle?.name||'Владелец героя',characterId:character?.id||''};
}
export function campaignParticipants(state){
 const byOwner=new Map(),characters=(state.characters||[]).filter(c=>c.kind==='pc'&&!c.hidden),master=currentMasterIdentity(state);
 for(const p of state.members||[])if(p.role!=='gm'||p.owner===master.owner)byOwner.set(p.owner,{...p,id:p.owner,online:true});
 if(state.me&&!byOwner.has(state.me.owner)&&(state.me.role!=='gm'||state.me.owner===master.owner))byOwner.set(state.me.owner,{...state.me,id:state.me.owner,online:true});
 if(!byOwner.has(master.owner))byOwner.set(master.owner,{...master,online:false});
 for(const p of state.journey?.cycleParticipants||[]){
  const gm=p.owner==='gm',known=gm?[...byOwner.values()].find(x=>x.role==='gm'):byOwner.get(p.owner);
  if(!known){const person=gm?master:(state.participantDirectory||[]).find(x=>x.owner===p.owner);byOwner.set(person?.owner||p.owner,{...p,...person,id:person?.owner||p.owner,role:gm?'gm':'player',online:false});}
 }
 for(const c of characters){if(!(state.journey?.party||[]).includes(c.id)&&!state.combat?.units?.some(u=>u.id===c.id))continue;const identity=controllerIdentity(state,c),owner=identity.owner||c.owner;if(!byOwner.has(owner))byOwner.set(owner,{id:owner,owner,name:identity.name,role:identity.role,online:false});}
 return [...byOwner.values()].map(p=>({...p,characterId:characters.find(c=>controllerIdentity(state,c).owner===p.owner)?.id||''})).sort((a,b)=>(a.role==='gm'?-1:1)-(b.role==='gm'?-1:1)||a.name.localeCompare(b.name,'ru'));
}
