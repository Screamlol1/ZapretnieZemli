const {contextBridge,ipcRenderer}=require('electron');
const call=(name,...args)=>ipcRenderer.invoke('desktop:'+name,...args);
contextBridge.exposeInMainWorld('desktop',Object.freeze({
 getState:()=>call('state'),startLocal:()=>call('start'),connect:url=>call('connect',url),
 openLocal:()=>call('open'),openBrowser:()=>call('browser'),startSharing:()=>call('share'),stopSharing:()=>call('unshare'),
 copy:text=>call('copy',text),openData:()=>call('folder'),backup:()=>call('backup'),
 navigate:action=>call('navigate',action),windowControl:action=>call('window',action),
 openSettings:()=>call('settings-open'),closeSettings:()=>call('settings-close'),applySettings:patch=>call('settings-apply',patch),confirmDisplay:()=>call('display-confirm'),revertDisplay:()=>call('display-revert'),
 onState:callback=>{const listener=(_event,value)=>callback(value);ipcRenderer.on('desktop:state',listener);return ()=>ipcRenderer.removeListener('desktop:state',listener);}
}));
