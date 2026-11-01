// Keep the exact command until the server acknowledges it. Never retry automatically.
export function commandTracker({storage,key,send,status,newId=()=>crypto.randomUUID()}){
 let active=false;
 const read=()=>{const raw=storage.getItem(key);return raw?JSON.parse(raw):null;};
 const write=value=>storage.setItem(key,JSON.stringify(value));
 const clear=record=>{if(read()?.command.requestId===record.command.requestId)storage.removeItem(key);};
 async function transmit(record,first){
  if(active)throw Error('Дождитесь проверки предыдущего действия.');
  active=true;
  try{const state=await send(record.command);clear(record);return state;}
  catch(e){
   // On a retry authentication/rate-limit failures cannot disprove an earlier success.
   if((first&&e.status>=400&&e.status<500&&![408,429].includes(e.status))||[400,409].includes(e.status))clear(record);
   throw e;
  }finally{active=false;}
 }
 return {
  get pending(){return read();},get active(){return active;},
  async perform(data){
   if(read())throw Error('Сначала проверьте результат предыдущего действия в панели связи.');
   const record={command:JSON.parse(JSON.stringify({...data,requestId:newId()})),created:Date.now()};
   write(record);return transmit(record,true);
  },
  async retry(){const record=read();if(!record)throw Error('Нет действия для повторной отправки.');return transmit(record,false);},
  async reconcile(){
   const record=read();if(!record||active)return null;
   active=true;
   try{const result=await status(record.command.requestId);if(result.status==='applied')clear(record);return result;}
   finally{active=false;}
  }
 };
}
