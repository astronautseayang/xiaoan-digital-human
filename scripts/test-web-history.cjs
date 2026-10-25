// Long tool output must not poison later requests or retain unbounded context.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('gateway/static/index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function page(replies){
 const elements=Object.fromEntries(['send','record','replay','status','text','messages','player'].map(id=>[id,{disabled:false,value:'',textContent:'',src:'',paused:true,addEventListener(){},async play(){}}]));
 const requests=[];
 const context=vm.createContext({document:{getElementById:id=>elements[id]},AbortController,console,setTimeout(){return 1;},clearTimeout(){},
  async fetch(url,options){
   if(url==='/ready')return {ok:true,json:async()=>({ready:true})};
   const payload=JSON.parse(options.body);requests.push(payload);
   const valid=payload.history.length<=12&&payload.history.every(m=>Array.from(m.content).length<=4000);
   return valid?{ok:true,json:async()=>({text:replies.shift()||'正常回答',audio_url:'/audio/test.wav'})}:{ok:false,json:async()=>({detail:'history content too long'})};
  }});
 vm.runInContext(code,context);
 return {elements,context,requests,async send(text){elements.text.value=text;await elements.send.onclick();}};
}
(async()=>{
 const failures=[];
 async function check(name,test){try{await test();console.log('PASS:',name);}catch(error){failures.push(name);console.error('FAIL:',name,error.message);}}
 await check('long sessions retain ten recent messages as complete pairs',async()=>{
  const p=page([]);
  for(let i=0;i<30;i++)await p.send('问题'+i);
  const history=JSON.parse(vm.runInContext('JSON.stringify(history)',p.context));
  assert.equal(history.length,10);assert.equal(history[0].content,'问题25');
  assert.equal(p.requests[29].history.length,10);
  for(let i=0;i<history.length;i+=2){assert.equal(history[i].role,'user');assert.equal(history[i+1].role,'assistant');}
 });
 await check('oversized answer remains visible and resets stale operational context',async()=>{
  const long='您已设置的提醒：'+'喝水提醒；'.repeat(900);
  const p=page(['已设置提醒：明天八点，提醒您散步。',long,'正常回答']);
  await p.send('明天八点提醒我散步');await p.send('查看提醒');
  assert.ok(p.elements.messages.textContent.includes(long));
  await p.send('取消这个提醒');
  assert.equal(p.requests[2].history.length,0,'Old reminders must not become the last context');
  assert.equal(p.elements.text.value,'');assert.match(p.elements.messages.textContent,/正常回答$/);
  assert.equal(p.elements.send.disabled,false);
 });
 await check('4000 Unicode characters remain valid without cutting surrogate pairs',async()=>{
  const reply='🌸'.repeat(4000),p=page([reply]);await p.send('看看花');await p.send('继续');
  assert.equal(p.requests[1].history[1].content,reply);assert.equal(p.elements.text.value,'');
 });
 assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exitCode=1;});
