import cultures from './location-cultures.json' with {type:'json'};
export {cultures};
export const cultureAssets=cultures.flatMap(c=>c.assets.map(a=>({...a,culture:c.id,cultureLabel:c.label})));
export const cultureAtlases={a:'/assets/location-cultures-a-v1.png',b:'/assets/location-cultures-b-v1.png'};
