export function artifactFields(values={}){
 return `<div class="artifact-counts">${[8,10,12].map(s=>`<label>D${s} · количество<input name="artifact${s}" type="number" min="0" max="10" step="1" value="${Math.max(0,Math.min(10,Number(values['artifact'+s])||0))}" required></label>`).join('')}</div>`;
}
export function readArtifacts(form){
 const values=new FormData(form),pool=[];
 for(const sides of [8,10,12]){const n=Number(values.get('artifact'+sides)||0);if(!Number.isInteger(n)||n<0||n>10)throw Error('Количество артефактных костей: целое число от 0 до 10.');pool.push(...Array(n).fill(sides));}
 if(pool.length>10)throw Error('Не более 10 артефактных костей суммарно.');return pool;
}
