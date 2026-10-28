import {attrCap,skillCap,budgets,PROFESSIONS} from './rules.js';
import {skillPointCost} from './reforged.js';
export function pipReason(s,pool,id,target){
 if(s.progression)return 'Навыки повышаются за опыт в разделе «Развитие». Стартовые параметры уже зафиксированы.';
 if(s.creation==='lifepath')return 'Значение определено событиями предыстории. После начала игры навыки повышаются за опыт.';
 const cap=pool==='skills'?skillCap(s,id):attrCap(s,id),min=pool==='skills'?0:2;
 if(target<min)return `Минимум при создании: ${min}.`;
 if(target>cap)return pool==='skills'?(PROFESSIONS[s.profession].skills.includes(id)?'Профессиональный навык: при создании максимум 3. Уровни 4–5 доступны за опыт.':'Не профессиональный навык: при создании максимум 1. Дальше можно повысить за опыт.'):`Предел характеристики при создании: ${cap}.`;
 const old=s[pool][id],cost=pool==='skills'?skillPointCost(s,target)-skillPointCost(s,old):target-old;
 if(cost>budgets(s)[pool])return `Недостаточно очков: нужно ${cost}, осталось ${budgets(s)[pool]}. Снизьте другой показатель, чтобы перераспределить очки.`;
 return '';
}
