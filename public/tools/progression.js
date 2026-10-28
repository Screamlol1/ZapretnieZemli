// Player's Handbook, pp. 39–40. Starting budgets and earned skill levels are separate.
export function skillXpCost(level){return (level+1)*5;}
export function validateProgression(raw,validateBase,ids){
 const p=raw.progression,fail=()=>{throw Error('Некорректная история развития героя.');};
 const int=(x,min,max)=>Number.isInteger(x)&&x>=min&&x<=max;
 if(!p||p.version!==1||!int(p.revision,1,1000000000)||!int(p.earned,0,1000000)||!int(p.spent,0,1000000)||typeof p.baseSkills!=='object'||!p.baseSkills||Object.keys(p.baseSkills).length!==ids.length)fail();
 for(const id of ids)if(!int(p.baseSkills[id],0,5)||!int(raw.skills?.[id],p.baseSkills[id],5))fail();
 if(Object.keys(raw.skills).length!==ids.length)fail();
 const base={...raw,skills:p.baseSkills};delete base.progression;
 const s=validateBase(base);
 const spent=ids.reduce((sum,id)=>sum+5*(raw.skills[id]*(raw.skills[id]+1)-p.baseSkills[id]*(p.baseSkills[id]+1))/2,0);
 if(spent!==p.spent||spent>p.earned||!(p.restCycle===null||typeof p.restCycle==='string'&&p.restCycle.length<=200)||!p.training||typeof p.training!=='object'||Array.isArray(p.training))fail();
 for(const [id,t] of Object.entries(p.training))if(!ids.includes(id)||raw.skills[id]!==0||!t||!['success','teacher'].includes(t.method)||!int(t.session,1,1000000))fail();
 s.skills={...raw.skills};s.progression={version:1,revision:p.revision,baseSkills:{...p.baseSkills},earned:p.earned,spent:p.spent,restCycle:p.restCycle,training:structuredClone(p.training)};
 return s;
}
