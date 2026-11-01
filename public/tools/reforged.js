// Reforged Power Player's Booklet 3.3, pp. 10, 14–16. Optional modules only.
export const REFORGED_DEFAULT={version:'3.3',ageWorth:true,flatCost:true,requiresSkills:false,willpowerThreshold:true};
export function reforgedConfig(raw){if(!raw||raw.version!=='3.3'||Object.keys(raw).some(k=>!Object.hasOwn(REFORGED_DEFAULT,k))||Object.keys(REFORGED_DEFAULT).some(k=>k!=='version'&&typeof raw[k]!=='boolean'))throw Error('Некорректные модули Reforged.');return {...raw};}
export function skillPointCost(s,n){return s.reforged?.flatCost&&n===3?4:n;}
export function creationAge(s,ages){const a={...ages[s.age]};if(s.reforged?.ageWorth)a.skills={young:8,adult:12,old:16}[s.age];if(s.reforged?.flatCost)a.skills+={young:2,adult:3,old:4}[s.age];return a;}
export function startingWillpower(s){return s.reforged?.willpowerThreshold?Math.min(10,(s.attrs.emp+1+s.pathRank)/2):0;}
export const TALENT_SKILLS={
 ambidextrous:['melee'],axe:['melee'],berserker:['endure'],bowyer:['craft'],brawler:['might','melee'],builder:['craft'],chef:['heal'],coldblood:['melee'],defender:['might'],dragon:['animal'],executioner:['move','insight'],fastfoot:['move'],fastshoot:['shoot'],fearless:['insight'],firmgrip:['melee'],fisher:['survive'],hammer:['melee'],herbalist:['survive','heal'],horsefight:['animal'],incorruptible:['insight'],knife:['melee','stealth'],lightning:['move'],lockpick:['sleight'],lucky:['endure'],masterhunt:['survive'],charge:['might','move'],packrat:['might','endure'],pain:['endure'],pathfinder:['survive'],poisoner:['craft','heal'],quartermaster:['survive'],quickdraw:['melee','sleight'],sailor:['survive'],sharp:['shoot'],tongue:['influence','perform'],shieldfight:['might','melee'],sixthsense:['scout'],smith:['craft'],spear:['melee'],steady:['move'],sword:['melee'],tailor:['craft'],tanner:['craft'],threat:['might','influence'],throw:['shoot'],wanderer:['endure']
};
export function talentAllowed(s,id,n=1){return !s.reforged?.requiresSkills||(TALENT_SKILLS[id]||[]).some(k=>s.skills[k]>=n);}
