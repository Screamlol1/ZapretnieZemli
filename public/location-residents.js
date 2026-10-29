// This allowlist mirrors server redaction. Export and GM's player preview use it
// even when the original map still contains all of the Master's private data.
export function publicPopulation(map){
 const p=map.population;if(!p)return undefined;
 const visible=new Set((map.features||[]).filter(f=>!f.secret).map(f=>f.id));
 const shown=record=>record.revealed===true||p.public===true&&record.revealed!==false;
 const households=new Map((p.households||[]).filter(h=>shown(h)&&(!h.homeFeatureId||visible.has(h.homeFeatureId))).map(h=>[h.id,h]));
 const pick=(record,keys)=>Object.fromEntries(keys.filter(k=>record[k]!==undefined).map(k=>[k,record[k]]));
 const residents=(p.residents||[]).filter(r=>shown(r)&&households.has(r.householdId)&&(!r.workplaceFeatureId||visible.has(r.workplaceFeatureId))).map(r=>pick(r,['id','name','kin','ageGroup','householdId','familyRole','role','occupation','workplaceFeatureId','description']));
 const used=new Set(residents.map(r=>r.householdId));
 return {generatorVersion:1,public:true,households:[...households.values()].filter(h=>used.has(h.id)).map(h=>pick(h,['id','name','homeFeatureId','note'])),residents};
}

export function buildingResidents(map,featureId){
 const households=(map.population?.households||[]).filter(h=>h.homeFeatureId===featureId),ids=new Set(households.map(h=>h.id));
 return {households,residents:(map.population?.residents||[]).filter(r=>ids.has(r.householdId)),workers:(map.population?.residents||[]).filter(r=>r.workplaceFeatureId===featureId)};
}

export function buildingLabel(map,feature,index){
 if(feature.label)return feature.label;
 const {households}=buildingResidents(map,feature.id);
 if(households.length)return households[0].name+(households.length>1?' и ещё '+(households.length-1):'');
 return 'Объект '+((index??map.features.findIndex(f=>f.id===feature.id))+1);
}
