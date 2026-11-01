// Player's Handbook, pp. 39–40. Creation budgets stay separate from paid advancement.
export const skillXpCost=level=>(level+1)*5;
export const talentXpCost=(level,magic=false,teacher=false)=>(level+1)*3*(magic&&!teacher?3:1);
export const learnedPaths=s=>({...s.paths,[s.path]:s.pathRank});
export function validateProgression(raw,validateBase,ids,catalog){
 const p=raw.progression,fail=()=>{throw Error('Некорректная история развития героя.');};
 const int=(x,min,max)=>Number.isInteger(x)&&x>=min&&x<=max,object=x=>!!x&&typeof x==='object'&&!Array.isArray(x),same=(a,b)=>JSON.stringify(Object.entries(a).sort())===JSON.stringify(Object.entries(b).sort());
 if(!p||![1,2].includes(p.version)||!int(p.revision,1,1000000000)||!int(p.earned,0,1000000)||!int(p.spent,0,1000000)||!object(p.baseSkills)||Object.keys(p.baseSkills).length!==ids.length)fail();
 for(const id of ids)if(!int(p.baseSkills[id],0,5)||!int(raw.skills?.[id],p.baseSkills[id],5))fail();
 if(Object.keys(raw.skills).length!==ids.length)fail();
 const base={...raw,skills:p.baseSkills};delete base.progression;delete base.paths;
 if(p.version===2){
  if(!object(p.baseTalents)||!object(p.basePaths)||Object.keys(p.basePaths).length!==1||!int(p.basePaths[raw.path],1,2))fail();
  base.talents=p.baseTalents;base.pathRank=p.basePaths[raw.path];
 }
 const s=validateBase(base);
 let spent=ids.reduce((sum,id)=>sum+5*(raw.skills[id]*(raw.skills[id]+1)-p.baseSkills[id]*(p.baseSkills[id]+1))/2,0);
 if(!(p.restCycle===null||typeof p.restCycle==='string'&&p.restCycle.length<=200)||!object(p.training))fail();
 for(const [id,t] of Object.entries(p.training))if(!ids.includes(id)||raw.skills[id]!==0||!t||!['success','teacher'].includes(t.method)||!int(t.session,1,1000000))fail();
 const saved={version:p.version,revision:p.revision,baseSkills:{...p.baseSkills},earned:p.earned,spent:p.spent,restCycle:p.restCycle,training:structuredClone(p.training)};
 if(p.version===2){
  if(!object(raw.talents)||!object(raw.paths)||raw.pathRank!==raw.paths[raw.path]||!Array.isArray(p.purchases)||p.purchases.length>200||!object(p.talentTraining)||!(p.practiceCycle===null||typeof p.practiceCycle==='string'&&p.practiceCycle.length<=200))fail();
  const talents={...p.baseTalents},paths={...p.basePaths};
  const entry=(kind,id)=>kind==='talent'?catalog.general.find(t=>t.id===id&&(!t.expansion||t.expansion===raw.expansion)):kind==='path'?catalog.paths(raw).find(t=>t.id===id):null;
  for(const row of p.purchases){
   if(!object(row)||!int(row.rank,1,3)||!int(row.session,1,1000000)||typeof row.cycle!=='string'||row.cycle.length>200)fail();
   const t=entry(row.kind,row.id),pool=row.kind==='talent'?talents:paths;
   if(!t||row.rank!==(pool[row.id]||0)+1||!['teacher','practice','advance'].includes(row.method)||typeof row.teacher!=='boolean'||row.rank===1&&row.method==='advance'||(row.method==='teacher')!==row.teacher||row.cost!==talentXpCost(row.rank-1,!!t.magic,row.teacher))fail();
   pool[row.id]=row.rank;spent+=row.cost;
  }
  if(!same(talents,raw.talents)||!same(paths,raw.paths)||Object.entries(raw.talents).some(([id,n])=>!catalog.allowed(raw,id,n)))fail();
  for(const [key,t] of Object.entries(p.talentTraining)){
   const [kind,id,...extra]=key.split(':'),item=entry(kind,id),level=(kind==='talent'?talents:paths)[id]||0;
   if(extra.length||!item||!object(t)||!int(t.rank,1,3)||t.rank!==level+1||!['teacher','practice'].includes(t.method)||!int(t.session,1,1000000)||typeof t.cycle!=='string'||t.cycle.length>200||item.magic&&t.method==='teacher'&&!int(t.teacherRank,t.rank,3))fail();
  }
  Object.assign(saved,{baseTalents:{...p.baseTalents},basePaths:{...p.basePaths},purchases:structuredClone(p.purchases),talentTraining:structuredClone(p.talentTraining),practiceCycle:p.practiceCycle});
  s.talents={...talents};s.paths={...paths};s.pathRank=raw.pathRank;
 }else if(raw.paths!==undefined)fail();
 if(spent!==p.spent||spent>p.earned)fail();
 s.skills={...raw.skills};s.progression=saved;return s;
}
