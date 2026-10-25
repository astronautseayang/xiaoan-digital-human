// Execute the actual page script with controlled browser APIs and async timing.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync('gateway/static/index.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const deferred = () => { let resolve,reject; const promise = new Promise((r,j) => { resolve = r;reject=j; }); return {promise, resolve,reject}; };
function page({constructFails = false, startFails = false, pendingPermission = false, stopFails = false, pendingReady = false} = {}) {
  const elements = Object.fromEntries(['send','record','replay','status','text','messages','player'].map(id => [id, {disabled: false, value: '', textContent: '', paused: true, src: '', addEventListener() {}, async play() { this.played = true; }}]));
  let stopped = 0, mediaCalls = 0;
  const stream = {getTracks: () => [{stop() { stopped++; }}]};
  const permission = deferred(), recognition = deferred(), readiness = deferred(), chat = deferred();
  const nextPermission=deferred(),timers=new Map();let timerId=0;
  const recorders = [], uploads = [], chats = [];
  class Recorder {
    constructor() { if (constructFails) throw Error('unsupported'); this.state = 'inactive'; this.mimeType = 'audio/webm'; recorders.push(this); }
    start() { if (startFails) throw Error('cannot start'); this.state = 'recording'; }
    stop() { if (stopFails) throw Error('cannot stop'); this.state = 'inactive'; this.ondataavailable({data: new Blob(['session audio'])}); this.finished = this.onstop(); }
  }
  vm.runInNewContext(code, {document: {getElementById: id => elements[id]}, navigator: {mediaDevices: {getUserMedia() { mediaCalls++; return pendingPermission ? (mediaCalls===1?permission.promise:nextPermission.promise) : Promise.resolve(stream); }}}, MediaRecorder: Recorder, Blob, FormData, console, AbortController,
    setTimeout(callback,delay){const id=++timerId;timers.set(id,{callback,delay});return id;}, clearTimeout(id){timers.delete(id);},
    async fetch(url, options) {
      if (url === '/ready') return pendingReady ? readiness.promise : {ok: true, json: async () => ({ready: true})};
      if (url === '/api/chat') {chats.push(JSON.parse(options.body));return chat.promise;}
      assert.equal(url, '/api/asr?execute_commands=false'); uploads.push(options.body);
      return recognition.promise;
    }});
  return {elements, stream, permission, nextPermission, timers, recognition, readiness, chat, chats, recorders, uploads, stopped: () => stopped, mediaCalls: () => mediaCalls,
    expirePermission(){const entry=[...timers].find(([,t])=>t.delay===30000);assert.ok(entry,'Missing microphone permission deadline');timers.delete(entry[0]);entry[1].callback();}};
}
async function main() {
  const failures = [];
  async function check(name, test) { try { await test(); console.log('PASS:', name); } catch (error) { failures.push(name); console.error('FAIL:', name, error.message); } }
  await check('constructor/start failure releases microphone and permits retry', async () => {
    for (const options of [{constructFails: true}, {startFails: true}]) {
      const p = page(options); await p.elements.record.onclick();
      assert.equal(p.stopped(), 1); assert.equal(p.elements.record.disabled, false);
      assert.match(p.elements.status.textContent, /无法使用麦克风/);
      await p.elements.record.onclick();
      assert.equal(p.mediaCalls(), 2); assert.equal(p.stopped(), 2);
    }
  });
  await check('pending permission prevents overlapping acquisition', async () => {
    const p = page({pendingPermission: true});
    const first = p.elements.record.onclick();
    assert.equal(p.elements.record.disabled, true); assert.equal(p.elements.send.disabled, true);
    await p.elements.record.onclick(); assert.equal(p.mediaCalls(), 1);
    p.permission.resolve(p.stream); await first;
    assert.equal(p.elements.record.disabled, false); assert.equal(p.elements.send.disabled, true);
  });
  await check('recognition locks controls and playback, then recovers on success/failure', async () => {
    for (const ok of [true, false]) {
      const p = page(); p.elements.player.src = '/audio/existing.wav';
      await p.elements.record.onclick();
      assert.equal(p.elements.replay.disabled, true);
      await p.elements.replay.onclick(); assert.equal(p.elements.player.played, undefined);
      await p.elements.record.onclick();
      assert.equal(p.stopped(), 1); assert.equal(p.uploads.length, 1);
      assert.equal(p.elements.record.disabled, true); assert.equal(p.elements.send.disabled, true);
      await p.elements.record.onclick(); assert.equal(p.mediaCalls(), 1);
      p.recognition.resolve({ok, json: async () => ok ? {text: '测试录音'} : {detail: '识别失败'}});
      await p.recorders[0].finished;
      assert.equal(p.elements.record.disabled, false); assert.equal(p.elements.send.disabled, false);
      assert.equal(p.elements.replay.disabled, false);
      assert.equal(p.elements.status.textContent, ok ? '识别完成，点击发送' : '识别失败');
      if (ok) assert.equal(p.elements.text.value, '测试录音');
      assert.equal(await p.uploads[0].get('file').text(), 'session audio');
    }
  });
  await check('recorder error releases microphone, rejects partial data and permits retry', async () => {
    const p = page(); p.elements.text.value = '保留输入';
    await p.elements.record.onclick();
    const old = p.recorders[0];
    old.state = 'inactive';
    if (old.onerror) old.onerror({error: Error('device disconnected')});
    assert.equal(p.stopped(), 1);
    assert.equal(p.elements.record.disabled, false); assert.equal(p.elements.send.disabled, false);
    assert.match(p.elements.status.textContent, /录音失败.*device disconnected/);
    await p.elements.record.onclick();
    assert.equal(p.mediaCalls(), 2);
    // Browsers send a final dataavailable/stop after error. It must not upload
    // partial data or reset controls belonging to the newer recording.
    old.ondataavailable({data: new Blob(['partial'])});
    await old.onstop();
    assert.equal(p.uploads.length, 0);
    assert.equal(p.elements.send.disabled, true);
    assert.equal(p.elements.record.textContent, '结束录音');
    assert.equal(p.elements.text.value, '保留输入');
  });
  await check('synchronous stop failure releases microphone and ignores late events after retry', async () => {
    const p = page({stopFails: true}); p.elements.text.value = '保留输入';
    await new Promise(resolve => setImmediate(resolve));
    await p.elements.record.onclick();
    const old = p.recorders[0];
    await p.elements.record.onclick();
    assert.equal(p.stopped(), 1);
    assert.equal(p.elements.send.disabled, false);
    assert.equal(p.elements.record.disabled, false);
    assert.match(p.elements.status.textContent, /录音失败.*cannot stop/);
    await p.elements.record.onclick();
    assert.equal(p.mediaCalls(), 2);
    old.ondataavailable({data: new Blob(['partial'])});
    await old.onstop();
    old.onerror({error: Error('late failure')});
    assert.equal(p.stopped(), 1);
    assert.equal(p.uploads.length, 0);
    assert.equal(p.elements.send.disabled, true);
    assert.equal(p.elements.record.textContent, '结束录音');
    assert.equal(p.elements.text.value, '保留输入');
  });
  await check('late readiness success/failure preserves recording and recognition status', async () => {
    for (const stage of ['permission', 'recording', 'recognizing', 'recognized', 'error']) {
      for (const ok of [true, false]) {
        const p = page({pendingReady: true, pendingPermission: stage === 'permission'});
        const starting = p.elements.record.onclick();
        if (stage !== 'permission') await starting;
        if (stage === 'error') p.recorders[0].onerror({error: Error('device lost')});
        if (stage === 'recognizing' || stage === 'recognized') await p.elements.record.onclick();
        if (stage === 'recognized') {
          p.recognition.resolve({ok:true,json:async()=>({text:'测试识别'})});
          await p.recorders[0].finished;
        }
        const status = p.elements.status.textContent;
        p.readiness.resolve({ok,json:async()=>ok?{ready:true}:{detail:'就绪检查失败'}});
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(p.elements.status.textContent, status, stage);
        if (stage === 'permission') {p.permission.resolve(p.stream);await starting;}
      }
    }
  });
  await check('readiness still updates when no interaction has started', async () => {
    const p = page({pendingReady: true});
    p.readiness.resolve({ok:true,json:async()=>({ready:true})});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(p.elements.status.textContent, '服务已就绪');
  });
  await check('late readiness preserves chat progress and completed playback status', async () => {
    for (const completed of [true, false]) {
      const p = page({pendingReady:true});p.elements.text.value='你好';
      const sending = p.elements.send.onclick();
      if (completed) {
        p.chat.resolve({ok:true,json:async()=>({text:'您好',audio_url:'/audio/test.wav'})});
        await sending;
      }
      const status=p.elements.status.textContent;
      p.readiness.resolve({ok:true,json:async()=>({ready:true})});
      await new Promise(resolve=>setImmediate(resolve));
      assert.equal(p.elements.status.textContent,status);
      if (!completed) {
        p.chat.resolve({ok:true,json:async()=>({text:'您好',audio_url:'/audio/test.wav'})});
        await sending;
      }
    }
  });
  await check('chat preserves newer drafts including edits reverted to original text', async () => {
    for (const revert of [false, true]) {
      const p=page();p.elements.text.value='  原问题  ';
      const sending=p.elements.send.onclick();
      p.elements.text.value='下一句话';p.elements.text.oninput?.();
      if(revert){p.elements.text.value='  原问题  ';p.elements.text.oninput?.();}
      const draft=p.elements.text.value;
      p.chat.resolve({ok:true,json:async()=>({text:'回答',audio_url:'/audio/test.wav'})});
      await sending;
      assert.equal(p.elements.text.value,draft);
      assert.match(p.elements.messages.textContent,/你：原问题/);
    }
  });
  await check('ASR preserves edits during permission, recording and upload and displays transcript', async () => {
    for (const stage of ['permission','recording','upload','reverted']) {
      const p=page({pendingPermission:stage==='permission'});p.elements.text.value='原草稿';
      const starting=p.elements.record.onclick();
      if(stage!=='permission')await starting;
      if(stage==='upload'||stage==='reverted')await p.elements.record.onclick();
      p.elements.text.value='新草稿';p.elements.text.oninput?.();
      if(stage==='reverted'){p.elements.text.value='原草稿';p.elements.text.oninput?.();}
      const draft=p.elements.text.value;
      if(stage==='permission'){p.permission.resolve(p.stream);await starting;}
      if(stage==='permission'||stage==='recording')await p.elements.record.onclick();
      p.recognition.resolve({ok:true,json:async()=>({text:'<测试转写>'})});
      await p.recorders[0].finished;
      assert.equal(p.elements.text.value,draft,stage);
      assert.ok(p.elements.messages.textContent.includes('<测试转写>'));
      assert.match(p.elements.status.textContent,/保留.*输入/);
      assert.equal(p.elements.send.disabled,false);
    }
  });
  await check('oversized transcription remains editable and is blocked before chat, then recovers', async () => {
    const p=page();await new Promise(resolve=>setImmediate(resolve));
    const transcript='长'.repeat(2001);
    await p.elements.record.onclick();await p.elements.record.onclick();
    p.recognition.resolve({ok:true,json:async()=>({text:transcript})});
    await p.recorders[0].finished;
    assert.equal(p.elements.text.value,transcript);
    assert.match(p.elements.status.textContent,/2000.*缩短/);
    // Resolve any accidental chat request to make failure deterministic.
    p.chat.resolve({ok:true,json:async()=>({text:'回答',audio_url:'/audio/test.wav'})});
    await p.elements.send.onclick();
    assert.equal(p.chats.length,0);
    assert.equal(p.elements.text.value,transcript);
    assert.match(p.elements.status.textContent,/2000.*缩短/);
    assert.equal(p.elements.send.disabled,false);assert.equal(p.elements.record.disabled,false);
    p.elements.text.value='缩短后的问题';p.elements.text.oninput();
    await p.elements.send.onclick();
    assert.equal(p.chats.length,1);assert.equal(p.chats[0].text,'缩短后的问题');
    assert.equal(p.elements.text.value,'');
  });
  await check('send length boundary counts Unicode characters and trims surrounding spaces', async () => {
    for(const size of [2000,2001]){
      const p=page();await new Promise(resolve=>setImmediate(resolve));
      const text='🌸'.repeat(size);p.elements.text.value='  '+text+'  ';
      p.chat.resolve({ok:true,json:async()=>({text:'回答',audio_url:'/audio/test.wav'})});
      await p.elements.send.onclick();
      assert.equal(p.chats.length,size===2000?1:0);
      if(size===2000)assert.equal(p.chats[0].text,text);
      else assert.equal(p.elements.text.value,'  '+text+'  ');
    }
  });
  await check('permission timeout unlocks page and late grant cannot disturb retry',async()=>{
    const p=page({pendingPermission:true});await new Promise(resolve=>setImmediate(resolve));
    p.elements.text.value='保留草稿';const first=p.elements.record.onclick();
    p.expirePermission();await first;
    assert.equal(p.elements.send.disabled,false);assert.equal(p.elements.record.disabled,false);
    assert.match(p.elements.status.textContent,/权限.*超时/);assert.equal(p.elements.text.value,'保留草稿');
    const second=p.elements.record.onclick();
    let newStopped=0;
    p.nextPermission.resolve({getTracks:()=>[{stop(){newStopped++;}}]});await second;
    const status=p.elements.status.textContent;
    p.permission.resolve(p.stream);await new Promise(resolve=>setImmediate(resolve));
    assert.equal(p.stopped(),1);assert.equal(newStopped,0);
    assert.equal(p.recorders.length,1);assert.equal(p.uploads.length,0);
    assert.equal(p.elements.status.textContent,status);assert.equal(p.elements.send.disabled,true);
    assert.equal(p.timers.size,0);
  });
  await check('late permission rejection is handled without changing recovered page',async()=>{
    const p=page({pendingPermission:true});await new Promise(resolve=>setImmediate(resolve));
    const starting=p.elements.record.onclick();p.expirePermission();await starting;
    const status=p.elements.status.textContent;
    p.permission.reject(Error('denied late'));await new Promise(resolve=>setImmediate(resolve));
    assert.equal(p.elements.status.textContent,status);assert.equal(p.elements.send.disabled,false);
    assert.equal(p.recorders.length,0);assert.equal(p.timers.size,0);
  });
  await check('ordinary permission grant/rejection clears acquisition deadline',async()=>{
    for(const granted of [true,false]){
      const p=page({pendingPermission:true});await new Promise(resolve=>setImmediate(resolve));
      const starting=p.elements.record.onclick();
      if(granted)p.permission.resolve(p.stream);else p.permission.reject(Error('permission denied'));
      await starting;
      assert.equal(p.timers.size,0);assert.equal(p.elements.record.disabled,false);
      assert.equal(p.recorders.length,granted?1:0);
      if(!granted){assert.match(p.elements.status.textContent,/permission denied/);assert.equal(p.elements.send.disabled,false);}
    }
  });
  assert.deepEqual(failures, []);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
