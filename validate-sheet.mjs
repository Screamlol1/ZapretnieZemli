import {validateImport} from './public/tools/rules.js';
let text='';for await (const chunk of process.stdin) text+=chunk;
try {const sheet=validateImport(JSON.parse(text));
 if(sheet.reforged&&Object.entries(sheet.reforged).some(([k,v])=>k!=='version'&&v===true))throw Error('Reforged для кампании пока не согласован.');
 process.stdout.write(JSON.stringify(sheet));
}catch(e){process.stderr.write(e.message);process.exitCode=1;}
