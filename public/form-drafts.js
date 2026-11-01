// Preserve text being entered while another participant changes the campaign.
export function formDrafts(root){
 const key=f=>JSON.stringify(f.dataset),active=document.activeElement;
 const forms=[...root.querySelectorAll('form')].map(f=>({key:key(f),fields:[...f.elements].filter(e=>e.name&&e.type!=='submit').map(e=>({name:e.name,value:e.value,checked:e.checked,focus:e===active,start:e.selectionStart,end:e.selectionEnd}))}));
 const opened=[...root.querySelectorAll('details[open]')].map(e=>e.querySelector('summary')?.textContent),scroll=root.scrollTop;
 return ()=>{for(const f of root.querySelectorAll('form')){const saved=forms.find(x=>x.key===key(f));for(const v of saved?.fields||[]){const e=f.elements.namedItem(v.name);if(!e||!('value'in e))continue;if(e.tagName!=='SELECT'||[...e.options].some(o=>o.value===v.value))e.value=v.value;if(e.type==='checkbox'||e.type==='radio')e.checked=v.checked;if(v.focus){e.focus({preventScroll:true});if(v.start!==null&&typeof e.setSelectionRange==='function')try{e.setSelectionRange(v.start,v.end);}catch{}}}}for(const e of root.querySelectorAll('details'))if(opened.includes(e.querySelector('summary')?.textContent))e.open=true;root.scrollTop=scroll;};
}
