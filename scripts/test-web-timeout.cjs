// Exercise actual page requests with a fake clock, including stalled body reads.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync('gateway/static/index.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const flush = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
function page(phase, stallReady=false) {
  const timers = new Map(), requests = [];
  let next = 0;
  const elements = Object.fromEntries(['send','record','replay','status','text','messages','player'].map(id => [id, {disabled:false,value:'',textContent:'',paused:true,src:'',addEventListener(){},async play(){}}]));
  const recorders = [];
  class Recorder {
    constructor(){this.state='inactive';this.mimeType='audio/webm';recorders.push(this);}
    start(){this.state='recording';}
    stop(){this.state='inactive';this.ondataavailable({data:new Blob(['audio'])});this.finished=this.onstop();}
  }
  const context = vm.createContext({document:{getElementById:id=>elements[id]}, navigator:{mediaDevices:{async getUserMedia(){return {getTracks:()=>[{stop(){}}]};}}}, MediaRecorder:Recorder, Blob,FormData,AbortController,console,
    setTimeout(callback, delay){const id=++next;timers.set(id,{callback,delay});return id;},
    clearTimeout(id){timers.delete(id);},
    async fetch(url,options={}) {
      if(url==='/ready'&&!stallReady) return {ok:true,json:async()=>({ready:true})};
      requests.push({url,signal:options.signal});
      if(typeof phase==='function')return phase();
      if(phase==='success') return {ok:true,json:async()=>({text:'正常回答',audio_url:'/audio/test.wav'})};
      if(phase==='network') throw Error('connection lost');
      const stall=()=>new Promise((resolve,reject)=>options.signal?.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{name:'AbortError'})),{once:true}));
      if(phase==='body') return {ok:true,json:stall};
      return stall();
    }});
  vm.runInContext(code,context);
  return {context,elements,timers,requests,recorders,expire(expected){assert.equal(timers.size,1,'Missing bounded request deadline');const [id,timer]=[...timers][0];assert.equal(timer.delay,expected);timers.delete(id);timer.callback();}};
}
async function main(){
  const failures=[];
  async function check(name,test){try{await test();console.log('PASS:',name);}catch(error){failures.push(name);console.error('FAIL:',name,error.message);}}
  await check('initial readiness check ends after its own deadline',async()=>{
    const p=page('fetch',true);await flush();p.expire(10000);await flush();
    assert.equal(p.requests[0].signal.aborted,true);
    assert.match(p.elements.status.textContent,/超时/);assert.equal(p.timers.size,0);
  });
  await check('late readiness timeout does not overwrite active recording status',async()=>{
    const p=page('fetch',true);await p.elements.record.onclick();
    const status=p.elements.status.textContent;
    p.expire(10000);await flush();
    assert.equal(p.elements.status.textContent,status);
    assert.equal(p.requests[0].signal.aborted,true);assert.equal(p.timers.size,0);
  });
  await check('chat timeouts release controls and preserve input/history',async()=>{
    for(const phase of ['fetch','body']){
      const p=page(phase);await flush();p.elements.text.value='保留这个问题';
      const sending=p.elements.send.onclick();await flush();
      assert.equal(p.elements.send.disabled,true);
      p.expire(240000);await sending;
      assert.equal(p.requests[0].signal.aborted,true);
      assert.match(p.elements.status.textContent,/超时/);
      assert.equal(p.elements.text.value,'保留这个问题');assert.equal(p.elements.messages.textContent,'');
      assert.equal(p.elements.send.disabled,false);assert.equal(p.elements.record.disabled,false);
      assert.equal(vm.runInContext('history.length',p.context),0);assert.equal(p.timers.size,0);
    }
  });
  await check('ASR timeouts cover connection and body, restore buttons and input',async()=>{
    for(const phase of ['fetch','body']){
      const p=page(phase);await flush();p.elements.text.value='原来的输入';
      await p.elements.record.onclick();await p.elements.record.onclick();await flush();
      p.expire(120000);await p.recorders[0].finished;
      assert.equal(p.requests[0].url,'/api/asr?execute_commands=false');
      assert.equal(p.requests[0].signal.aborted,true);assert.match(p.elements.status.textContent,/超时/);
      assert.equal(p.elements.text.value,'原来的输入');assert.equal(p.elements.record.disabled,false);
      assert.equal(p.elements.send.disabled,false);assert.equal(p.timers.size,0);
    }
  });
  await check('success and ordinary failure clear deadlines without changing errors',async()=>{
    for(const phase of ['success','network']){
      const p=page(phase);await flush();p.elements.text.value='问题';await p.elements.send.onclick();
      assert.equal(p.timers.size,0);
      if(phase==='network')assert.equal(p.elements.status.textContent,'connection lost');
      else{assert.equal(p.elements.text.value,'');assert.match(p.elements.messages.textContent,/正常回答/);}
    }
  });
  const errors=[
    [()=>new Response(JSON.stringify({detail:'语音服务暂不可用'}),{status:503}),/语音服务暂不可用/],
    [()=>new Response(JSON.stringify({detail:[{loc:['body','text'],msg:'too long',input:'private draft'}]}),{status:422}),/校验.*检查/],
    [()=>new Response('<html>upstream down</html>',{status:502}),/HTTP 502/],
    [()=>new Response('',{status:503}),/HTTP 503/],
    [()=>new Response('null',{status:500}),/HTTP 500/],
    [()=>new Response(JSON.stringify({detail:{error:'internal'}}),{status:500}),/HTTP 500/],
    [()=>new Response('<html>wrong route</html>'),/返回格式异常/],
  ];
  await check('chat HTTP and malformed JSON errors preserve draft and permit successful retry',async()=>{
    for(const [response,expected] of errors){
      let failed=true;
      const p=page(()=>failed?response():{ok:true,json:async()=>({text:'重试成功',audio_url:'/audio/test.wav'})});
      await flush();p.elements.text.value='保留问题';await p.elements.send.onclick();
      assert.match(p.elements.status.textContent,expected);
      assert.equal(p.elements.text.value,'保留问题');assert.equal(p.elements.messages.textContent,'');
      assert.equal(vm.runInContext('history.length',p.context),0);
      assert.equal(p.elements.send.disabled,false);assert.equal(p.timers.size,0);
      failed=false;await p.elements.send.onclick();
      assert.match(p.elements.messages.textContent,/重试成功/);assert.equal(p.elements.text.value,'');
    }
  });
  await check('ASR HTTP and malformed JSON errors restore controls and preserve input',async()=>{
    for(const [response,expected] of errors){
      const p=page(response);await flush();p.elements.text.value='保留草稿';
      await p.elements.record.onclick();await p.elements.record.onclick();await p.recorders[0].finished;
      assert.match(p.elements.status.textContent,expected);
      assert.equal(p.elements.text.value,'保留草稿');assert.equal(p.elements.record.disabled,false);
      assert.equal(p.elements.send.disabled,false);assert.equal(p.timers.size,0);
    }
  });
  await check('invalid successful chat payloads cannot mutate transcript, history, draft or audio',async()=>{
    const invalid=[null,[],{}, {text:null,audio_url:'/audio/test.wav'}, {text:123,audio_url:'/audio/test.wav'},
      {text:['回答'],audio_url:'/audio/test.wav'}, {text:'  ',audio_url:'/audio/test.wav'},
      {text:'回答'}, {text:'回答',audio_url:123}, {text:'回答',audio_url:'  '}];
    for(const payload of invalid){
      let failed=true;
      const p=page(()=>({ok:true,json:async()=>failed?payload:{text:'正常回答',audio_url:'/audio/new.wav'}}));await flush();
      p.elements.text.value='保留草稿';p.elements.player.src='/audio/previous.wav';
      p.elements.messages.textContent='原有记录';
      await p.elements.send.onclick();
      assert.match(p.elements.status.textContent,/返回格式异常/);
      assert.equal(p.elements.text.value,'保留草稿');assert.equal(p.elements.messages.textContent,'原有记录');
      assert.equal(p.elements.player.src,'/audio/previous.wav');
      assert.equal(vm.runInContext('history.length',p.context),0);
      assert.equal(p.elements.send.disabled,false);assert.equal(p.timers.size,0);
      failed=false;await p.elements.send.onclick();assert.match(p.elements.messages.textContent,/正常回答/);
    }
  });
  await check('invalid and rejected ASR payloads preserve draft and explain empty result',async()=>{
    for(const [payload,expected] of [[null,/返回格式异常/],[{},/返回格式异常/],[{text:123},/返回格式异常/],
      [{text:[]},/返回格式异常/],[{text:''},/未识别到/],[{text:'  '},/未识别到/],
      [{text:'',input_notice:'未通过声纹验证'},/未通过声纹验证/]]){
      const p=page(()=>({ok:true,json:async()=>payload}));await flush();p.elements.text.value='保留草稿';
      await p.elements.record.onclick();await p.elements.record.onclick();await p.recorders[0].finished;
      assert.match(p.elements.status.textContent,expected);assert.equal(p.elements.text.value,'保留草稿');
      assert.equal(p.elements.record.disabled,false);assert.equal(p.elements.send.disabled,false);
      assert.equal(p.timers.size,0);
    }
  });
  await check('readiness rejects missing or non-boolean state',async()=>{
    for(const payload of [null,[],{}, {ready:'false'},{ready:1}]){
      const p=page(()=>({ok:true,json:async()=>payload}),true);await flush();
      assert.match(p.elements.status.textContent,/返回格式异常/);assert.equal(p.timers.size,0);
    }
  });
  assert.deepEqual(failures,[]);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
