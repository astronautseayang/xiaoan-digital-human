using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
namespace LocalHuman
{
    public sealed class OfflineWakeClient : MonoBehaviour
    {
        [Serializable] sealed class Event {public string type,state,keyword,text,care_command,error,reason;public bool ready;public float level;}
        readonly ConcurrentQueue<string> incoming=new ConcurrentQueue<string>();
        readonly ConcurrentQueue<string> outgoing=new ConcurrentQueue<string>();
        CancellationTokenSource lifetime;ClientWebSocket socket;LocalHumanDemo demo;SeniorCareClient care;
        public bool Ready {get;private set;}
        public string State {get;private set;}="connecting";
        public string Keyword {get;private set;}="小安";
        public string Hint {get;private set;}="正在连接本地唤醒";
        public float Level {get;private set;}
        float nextControl,lastEvent;bool wasBusy,cancelling;AudioSource chime;AudioClip ding;
        void Start()
        {
            demo=GetComponent<LocalHumanDemo>();care=GetComponent<SeniorCareClient>();
            var g=new GameObject("GentleWakeChime");g.transform.SetParent(transform,false);chime=g.AddComponent<AudioSource>();chime.playOnAwake=false;chime.spatialBlend=0;chime.volume=.55f;
            int rate=24000;var pcm=new float[rate/3];
            for(int i=0;i<pcm.Length;i++){float t=i/(float)rate;pcm[i]=(.55f*Mathf.Sin(2*Mathf.PI*1046.5f*t)+.16f*Mathf.Sin(2*Mathf.PI*1568*t))*Mathf.Exp(-t*13)*Mathf.Min(1,t*160);}
            ding=AudioClip.Create("柔和唤醒提示",pcm.Length,1,rate,false);ding.SetData(pcm,0);chime.clip=ding;
            lifetime=new CancellationTokenSource();Connect(lifetime.Token);
        }
        async void Connect(CancellationToken token)
        {
            while(!token.IsCancellationRequested) {
                try {
                    using(var ws=new ClientWebSocket()) {
                        socket=ws;
                        await ws.ConnectAsync(new Uri(demo.gateway.Replace("http://","ws://").Replace("https://","wss://")+"/ws/wake"),token);
                        using(var linked=CancellationTokenSource.CreateLinkedTokenSource(token)) {
                            var sender=SendLoop(ws,linked.Token);
                            try {
                                var buffer=new byte[8192];var text=new StringBuilder();
                                while(ws.State==WebSocketState.Open&&!token.IsCancellationRequested) {
                                    var r=await ws.ReceiveAsync(new ArraySegment<byte>(buffer),token);
                                    if(r.MessageType==WebSocketMessageType.Close)break;
                                    text.Append(Encoding.UTF8.GetString(buffer,0,r.Count));
                                    if(r.EndOfMessage){incoming.Enqueue(text.ToString());text.Length=0;}
                                }
                            }finally{linked.Cancel();try{await sender;}catch(OperationCanceledException){} }
                        }
                    }
                }catch(Exception e){if(!token.IsCancellationRequested)incoming.Enqueue("{\"type\":\"disconnected\"}");Debug.Log("WAKE socket "+e.GetType().Name);}
                if(!token.IsCancellationRequested){incoming.Enqueue("{\"type\":\"disconnected\"}");try{await Task.Delay(2000,token);}catch(OperationCanceledException){} }
            }
        }
        async Task SendLoop(ClientWebSocket ws,CancellationToken token)
        {
            while(!token.IsCancellationRequested&&ws.State==WebSocketState.Open) {
                while(outgoing.TryDequeue(out string text)) {
                    var bytes=Encoding.UTF8.GetBytes(text);await ws.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,token);
                }
                await Task.Delay(80,token);
            }
        }
        public void ListenNow()
        {
            if(care.Active)return;
            if(State=="listening"||demo.IsRecording){FinishListening();return;}
            if(State=="thinking"||demo.IsProcessing||demo.IsSpeaking||demo.IsRecording){Interrupt();return;}
            if(Ready&&!cancelling&&!demo.IsBusy&&!demo.IsRecording)outgoing.Enqueue("{\"type\":\"manual_listen\"}");
            else if(!Ready)demo.ToggleRecording();
        }
        public void FinishListening()
        {
            if(care.Active)return;
            if(demo.IsRecording){demo.ToggleRecording();return;}
            if(!Ready||State!="listening")return;
            chime.Stop();State="thinking";Hint="已结束收音，正在识别";Level=0;
            outgoing.Enqueue("{\"type\":\"finish_listen\"}");
        }
        public void Interrupt()
        {
            if(care.Active)return;
            cancelling=Ready;chime.Stop();demo.InterruptForCare();demo.ShowInterrupted();
            GetComponent<AvatarInteractiveMotion>()?.CancelInteraction();
            State="idle";Hint="已结束对话 · 想说话时再叫我";Level=0;wasBusy=false;
            outgoing.Enqueue("{\"type\":\"cancel_listen\"}");
        }
        void Update()
        {
            while(incoming.TryDequeue(out string text)) {
                Event e=null;try{e=JsonUtility.FromJson<Event>(text);}catch(Exception){continue;}
                if(e==null)continue;
                lastEvent=Time.unscaledTime;
                if(e.type=="disconnected"){cancelling=false;Ready=false;State="connecting";Hint="唤醒连接中 · 可点击麦克风";continue;}
                if(e.type=="status"){cancelling=false;Ready=e.ready;if(!string.IsNullOrEmpty(e.keyword))Keyword=e.keyword;State=e.state;Hint=e.ready?"叫一声“"+Keyword+"”，我就在":"唤醒暂不可用 · 可点击麦克风";}
                if(e.ready)Ready=true;
                if(e.type=="state"&&e.reason=="manual_cancel"){cancelling=false;State="idle";Hint="已结束对话 · 想说话时再叫我";continue;}
                if(cancelling)continue;
                if(e.type=="level"){Level=e.level;continue;}
                if(e.type=="wake") {
                    if(care.Active||demo.IsBusy)continue;
                    GetComponent<SpeechSubtitleTrack>().Clear();
                    State="listening";Hint=GetComponent<SeniorCompanion>().Address("您慢慢说，说完我会自动收好");Level=0;
                    chime.Play();GetComponent<AvatarInteractiveMotion>()?.AcknowledgeWake();
                }
                if(e.type=="state") {
                    State=e.state;
                    if(State=="idle")Hint=e.reason=="empty_recording"?"没有收到语音，请再叫我一次":e.reason=="silence_timeout"?"没关系，想说话时再叫我":"叫一声“"+Keyword+"”，我就在";
                    if(State=="thinking")Hint=e.reason=="speech_finished"?"已自动结束收音，正在识别分析":e.reason=="max_duration"?"已收好这段语音，正在识别分析":"听到了，正在识别分析";
                    if(State=="error")Hint=string.IsNullOrEmpty(e.error)?"没有听清，请再叫我一次":e.error;
                }
                if(e.type=="transcript") {
                    State="thinking";
                    if(!string.IsNullOrEmpty(e.care_command))continue;
                    if(!string.IsNullOrWhiteSpace(e.text)&&!demo.IsBusy){demo.Question=e.text;demo.StartCoroutine(demo.ChatWithAudio(e.text));}
                    else {State="idle";Hint="没有听清，请再叫我一次";}
                }
            }
            if(Time.unscaledTime>=nextControl) {
                nextControl=Time.unscaledTime+.25f;
                if(socket!=null&&socket.State==WebSocketState.Open) {
                    bool busy=demo.IsProcessing||demo.IsRecording||demo.IsSpeaking;
                    outgoing.Enqueue("{\"type\":\"control\",\"enabled\":"+(care.Listening?"true":"false")+",\"suppress\":"+(busy?"true":"false")+"}");
                    if(wasBusy&&!busy){State="idle";Hint="叫一声“"+Keyword+"”，我就在";}
                    wasBusy=busy;
                }
            }
            Level=Mathf.MoveTowards(Level,0,Time.unscaledDeltaTime*.6f);
        }
        void OnDestroy(){lifetime?.Cancel();socket?.Abort();lifetime?.Dispose();if(ding)Destroy(ding);}
    }
}
