import {blank,KINS,PROFESSIONS,SKILLS,ITEMS} from './public/tools/rules.js';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const integer=(v,a,b)=>Number.isInteger(v)&&v>=a&&v<=b;
try{const d=JSON.parse(raw);if(!['npc','monster'].includes(d.kind)||typeof d.name!=='string'||!d.name.trim()||d.name.length>60)throw Error('Укажите имя ПВ или чудовища.');
 const result={kind:d.kind,name:d.name.trim(),hidden:d.hidden===true};
 if(d.kind==='npc'){
  if(!KINS[d.kin]||!PROFESSIONS[d.profession])throw Error('Неизвестный народ или профессия.');
  const s={...blank(),name:result.name,kin:d.kin,profession:d.profession,notes:typeof d.notes==='string'?d.notes.slice(0,6000):''};
  if(!d.attrs||Object.keys(s.attrs).some(k=>!integer(d.attrs[k],1,10))||!d.skills||SKILLS.some(([k])=>!integer(d.skills[k],0,5)))throw Error('ПВ: характеристики 1–10, навыки 0–5.');
  s.attrs=Object.fromEntries(Object.keys(s.attrs).map(k=>[k,d.attrs[k]]));s.skills=Object.fromEntries(SKILLS.map(([k])=>[k,d.skills[k]]));
  if(!Array.isArray(d.gear)||d.gear.length>30||d.gear.some(k=>!ITEMS[k]))throw Error('Неизвестное снаряжение.');
  s.creation='npc';s.gear=d.gear;s.purchases=[];s.trade=[];s.talents={};s.pathRank=1;
  result.sheet=s;
 }else{
  const m=d.monster;if(!m||!integer(m.strength,1,100)||!integer(m.armor,0,20)||!integer(m.agility,1,10)||!Array.isArray(m.attacks)||m.attacks.length!==6)throw Error('Чудовище: ТЕЛ 1–100, броня 0–20, ЛОВ 1–10 и шесть атак D6.');
  result.monster={strength:m.strength,armor:m.armor,agility:m.agility,notes:String(m.notes||'').slice(0,6000),attacks:m.attacks.map(a=>{
   if(typeof a.name!=='string'||!a.name.trim()||a.name.length>100||!integer(a.dice,1,30)||!integer(a.damage,1,20)||!integer(a.range,1,6)||!['physical','fear','manual'].includes(a.type))throw Error('Некорректная атака чудовища.');
   return {name:a.name,dice:a.dice,damage:a.damage,range:a.range,type:a.type,parry:a.parry===true,dodge:a.dodge!==false,note:String(a.note||'').slice(0,1000)};
  })};
 }
 process.stdout.write(JSON.stringify(result));
}catch(e){process.stderr.write(e.message);process.exitCode=1;}
