using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
namespace LocalHuman
{
    public sealed class SeniorCareClient : MonoBehaviour
    {
        [Serializable] public sealed class CareEvent {public string id,kind,title,text,audio_url,audio_state,push_state;public int priority;}
        [Serializable] sealed class Events {public CareEvent[] events;public int version;}
        [Serializable] sealed class Ack {public string id;}
        [Serializable] sealed class Speech {public string text,care_command,event_id;}
        LocalHumanDemo demo;AudioSource source;SeniorAudioLimiter limiter;
        Text clock,date,subtitle,body,delivery,micLabel,cardTitle,cardSymbol;GameObject card,shade;CareEvent current;
        LocalHuman.AvatarPipeline.RoundedCard cardAccent;
        static readonly Color Ink=new Color32(29,53,52,255), Teal=new Color32(28,103,95,255);
        readonly HashSet<string> played=new HashSet<string>();
        Coroutine playback;AudioClip mic;int position;bool uploading,listen=true;float silence;
        readonly List<float> samples=new List<float>();string utteranceEventId="";
        public bool Active => current!=null;
        public string CurrentEventId => current==null?"":current.id;
        public bool Listening => listen;
        public void ToggleLoudGain(){limiter.LoudGain=!limiter.LoudGain;PlayerPrefs.SetInt("SeniorLoudGain",limiter.LoudGain?1:0);PlayerPrefs.Save();}
        public void ToggleListening(){listen=!listen;PlayerPrefs.SetInt("SeniorCareListen",listen?1:0);PlayerPrefs.Save();}
        GameObject interruptButton;Text interactionState,wakeHint;RectTransform halo;VoiceActivityGraphic activity;
        readonly float[] outputSamples=new float[64];
        void Start()
        {
            demo=GetComponent<LocalHumanDemo>();source=GetComponent<AudioSource>();
            limiter=GetComponent<SeniorAudioLimiter>();if(!limiter)limiter=gameObject.AddComponent<SeniorAudioLimiter>();
            limiter.LoudGain=PlayerPrefs.GetInt("SeniorLoudGain",0)==1;
            listen=PlayerPrefs.GetInt("SeniorCareListen",1)==1;
            BuildUI();StartCoroutine(Poll());StartCoroutine(Listen());
        }
        IEnumerator Poll()
        {
            bool wait=false;int version=-1;
            while(true) {
                using(var r=UnityWebRequest.Get(demo.gateway+"/api/care/events?wait="+(wait?"true":"false")+"&after="+version)) {
                    r.timeout=25;yield return r.SendWebRequest();
                    if(r.result==UnityWebRequest.Result.Success) {
                        Events result=null;
                        try{result=JsonUtility.FromJson<Events>(r.downloadHandler.text);}catch(Exception e){Debug.LogWarning(e.Message);}
                        var next=result!=null&&result.events!=null&&result.events.Length>0?result.events[0]:null;
                        Apply(next);if(result!=null)version=result.version;wait=true;
                    }else{delivery.text="关怀服务连接中，请留意身边情况";wait=false;yield return new WaitForSecondsRealtime(2);}
                }
            }
        }
        void Apply(CareEvent next)
        {
            if(next==null){if(current!=null)Close();return;}
            if(current==null||current.id!=next.id) {
                if(playback!=null)StopCoroutine(playback);
                demo.InterruptForCare();current=next;limiter.Emergency=next.kind=="emergency";card.SetActive(true);shade.SetActive(true);
                // Immediate audible local feedback works even while TTS is unavailable.
                if(next.kind=="emergency") {
                    int rate=24000;var pcm=new float[rate];
                    for(int i=0;i<pcm.Length;i++)pcm[i]=.65f*Mathf.Sin(2*Mathf.PI*880*i/rate)*Mathf.Min(1,i/240f)*Mathf.Min(1,(pcm.Length-i)/240f);
                    var beep=AudioClip.Create("求助确认",pcm.Length,1,rate,false);beep.SetData(pcm,0);source.clip=beep;source.Play();
                }
            }
            current=next;
            bool emergency=next.kind=="emergency";
            cardTitle.text=next.title;cardSymbol.text=emergency?"!":"✓";
            cardAccent.color=emergency?new Color32(168,54,43,255):Teal;
            cardTitle.color=emergency?new Color32(150,42,34,255):Ink;
            body.text=next.text;
            string push=next.push_state=="sent"?"求助已推送至照护端":next.push_state=="local_only"?"本地告警 · 尚未配置照护端":next.push_state=="retry"?"照护端推送失败，正在重试":"正在推送至照护端";
            delivery.text=(next.kind=="emergency"?push+"\n":"")+(next.audio_state=="failed"?"语音暂不可用，请查看文字提醒":"可说“知道了”或点击按钮确认");
            if(next.audio_state=="ready"&&!played.Contains(next.id)) {
                played.Add(next.id);playback=StartCoroutine(Play(next));
            }
        }
        IEnumerator Play(CareEvent item)
        {
            using(var r=UnityWebRequestMultimedia.GetAudioClip(demo.gateway+item.audio_url,AudioType.WAV)) {
                r.timeout=30;yield return r.SendWebRequest();
                if(current==null||current.id!=item.id)yield break;
                if(r.result!=UnityWebRequest.Result.Success){played.Remove(item.id);delivery.text="语音下载失败，请查看文字提醒";yield break;}
                while(source.isPlaying)yield return null;
                if(current==null||current.id!=item.id)yield break;
                if(source.clip)Destroy(source.clip);source.clip=DownloadHandlerAudioClip.GetContent(r);
                source.volume=1;source.mute=false;source.pitch=1;
                GetComponent<AvatarInteractiveMotion>()?.BeginUtterance();GetComponent<AvatarInteractiveMotion>()?.PrepareSpeech(item.text);
                source.Play();
            }
        }
        public void Acknowledge(){if(current!=null)StartCoroutine(AckEvent(current.id));}
        IEnumerator AckEvent(string id)
        {
            using(var r=JsonPost("/api/care/ack",JsonUtility.ToJson(new Ack{id=id}))) {
                yield return r.SendWebRequest();
                if(r.result==UnityWebRequest.Result.Success&&current!=null&&current.id==id)Close();
                else if(r.result!=UnityWebRequest.Result.Success)delivery.text="确认未送达，请重试";
            }
        }
        void Close(){limiter.Emergency=false;current=null;card.SetActive(false);shade.SetActive(false);if(playback!=null)StopCoroutine(playback);source.Stop();}
        UnityWebRequest JsonPost(string path,string json)
        {
            var r=new UnityWebRequest(demo.gateway+path,"POST");r.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));r.downloadHandler=new DownloadHandlerBuffer();r.SetRequestHeader("Content-Type","application/json");r.timeout=15;return r;
        }
        public void SuspendMicrophone()
        {
            if(mic){Microphone.End(null);Destroy(mic);mic=null;}samples.Clear();silence=0;
        }
        IEnumerator Listen()
        {
            yield return Application.RequestUserAuthorization(UserAuthorization.Microphone);
            var wait=new WaitForSecondsRealtime(.1f);
            while(true) {
                yield return wait;
                if((GetComponent<OfflineWakeClient>()&&GetComponent<OfflineWakeClient>().Ready)||!listen||demo.IsRecording||demo.IsEnrolling){SuspendMicrophone();continue;}
                if(!Application.HasUserAuthorization(UserAuthorization.Microphone)||Microphone.devices.Length==0){micLabel.text="麦克风不可用 · 可点击确认";continue;}
                if(!mic||!Microphone.IsRecording(null)) {
                    SuspendMicrophone();mic=Microphone.Start(null,true,10,16000);position=0;continue;
                }
                int end=Microphone.GetPosition(null);if(end<0)continue;
                int count=(end-position+mic.samples)%mic.samples;if(count==0)continue;
                var data=new float[count*mic.channels];mic.GetData(data,position);position=end;
                if(uploading){samples.Clear();continue;}
                double energy=0;var mono=new float[count];
                for(int i=0;i<count;i++){for(int c=0;c<mic.channels;c++)mono[i]+=data[i*mic.channels+c]/mic.channels;energy+=mono[i]*mono[i];}
                bool voiced=Math.Sqrt(energy/count)>.012;
                if(samples.Count==0&&voiced)utteranceEventId=CurrentEventId;
                if(voiced||samples.Count>0){samples.AddRange(mono);silence=voiced?0:silence+count/(float)mic.frequency;}
                if(samples.Count>0&&(silence>.5f||samples.Count>=mic.frequency*4)) {
                    if(samples.Count>=mic.frequency*.3f)StartCoroutine(Recognize(ToWav(samples,mic.frequency),utteranceEventId));
                    samples.Clear();silence=0;
                }
            }
        }
        IEnumerator Recognize(byte[] wav,string eventId)
        {
            uploading=true;
            try {
                var form=new List<IMultipartFormSection>{new MultipartFormFileSection("file",wav,"care.wav","audio/wav")};
                using(var r=UnityWebRequest.Post(demo.gateway+"/api/asr?care_event_id="+UnityWebRequest.EscapeURL(eventId),form)) {
                    r.timeout=30;yield return r.SendWebRequest();
                    if(r.result==UnityWebRequest.Result.Success) {
                        Speech result=null;try{result=JsonUtility.FromJson<Speech>(r.downloadHandler.text);}catch(Exception e){Debug.LogWarning(e.Message);}
                        if(result!=null&&result.care_command=="ack"&&current!=null&&current.id==result.event_id)Close();
                        micLabel.text="语音关怀监听：开启";
                    }else micLabel.text="语音识别暂不可用 · 可点击确认";
                }
            }finally{uploading=false;}
        }
        static byte[] ToWav(List<float> values,int rate)
        {
            using(var stream=new MemoryStream())using(var w=new BinaryWriter(stream)) {
                w.Write(Encoding.ASCII.GetBytes("RIFF"));w.Write(36+values.Count*2);w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));w.Write(16);w.Write((short)1);w.Write((short)1);w.Write(rate);w.Write(rate*2);w.Write((short)2);w.Write((short)16);w.Write(Encoding.ASCII.GetBytes("data"));w.Write(values.Count*2);
                foreach(float v in values)w.Write((short)(Mathf.Clamp(v,-1,1)*32767));return stream.ToArray();
            }
        }
        Text Label(Transform parent,string value,int size,Vector2 pos,Vector2 dimensions)
        {
            var g=new GameObject("CareText",typeof(RectTransform),typeof(Text));g.transform.SetParent(parent,false);
            var rt=g.GetComponent<RectTransform>();rt.anchorMin=rt.anchorMax=rt.pivot=new Vector2(.5f,.5f);rt.anchoredPosition=pos;rt.sizeDelta=dimensions;
            var t=g.GetComponent<Text>();t.font=demo.chineseFont;t.fontSize=size;t.text=value;t.color=Color.white;t.alignment=TextAnchor.MiddleCenter;t.raycastTarget=false;t.supportRichText=false;return t;
        }
        GameObject Box(Transform parent,string name,Vector2 pos,Vector2 size,Color color)
        {
            var g=new GameObject(name,typeof(RectTransform),typeof(LocalHuman.AvatarPipeline.RoundedCard));g.transform.SetParent(parent,false);var rt=g.GetComponent<RectTransform>();rt.anchorMin=rt.anchorMax=rt.pivot=new Vector2(.5f,.5f);rt.anchoredPosition=pos;rt.sizeDelta=size;var graphic=g.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>();graphic.color=color;graphic.radius=22;return g;
        }
        void Button(Transform parent,string text,Vector2 pos,Vector2 size,UnityEngine.Events.UnityAction click)
        {
            var g=Box(parent,text,pos,size,Teal);var button=g.AddComponent<Button>();button.targetGraphic=g.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>();var colors=button.colors;colors.highlightedColor=new Color(.88f,.96f,.93f);colors.pressedColor=new Color(.7f,.85f,.8f);button.colors=colors;button.onClick.AddListener(click);Label(g.transform,text,28,Vector2.zero,size);
        }
        void BuildUI()
        {
            var g=new GameObject("SeniorCareCanvas",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));g.transform.SetParent(transform,false);var canvas=g.GetComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceOverlay;canvas.sortingOrder=50;
            var scaler=g.GetComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;scaler.referenceResolution=new Vector2(1600,900);scaler.screenMatchMode=CanvasScaler.ScreenMatchMode.Expand;
            Button(g.transform,"设置",new Vector2(608,410),new Vector2(174,54),()=>GetComponent<LocalHuman.AvatarPipeline.LocalHumanPanel>().ToggleDrawer());
            var timeBox=Box(g.transform,"Clock",new Vector2(475,270),new Vector2(440,190),new Color32(24,62,59,255));
            Label(timeBox.transform,"今天 · 与您相伴",22,new Vector2(0,64),new Vector2(400,35)).color=new Color32(191,222,209,255);
            clock=Label(timeBox.transform,"",72,new Vector2(0,1),new Vector2(420,115));
            date=Label(timeBox.transform,"",28,new Vector2(0,-62),new Vector2(420,44));
            var aura=new GameObject("VoiceActivity",typeof(RectTransform),typeof(VoiceActivityGraphic));aura.transform.SetParent(g.transform,false);
            halo=aura.GetComponent<RectTransform>();halo.anchorMin=halo.anchorMax=new Vector2(.5f,.5f);halo.anchoredPosition=new Vector2(-520,30);halo.sizeDelta=new Vector2(230,230);
            activity=aura.GetComponent<VoiceActivityGraphic>();activity.raycastTarget=false;
            aura.AddComponent<Button>().onClick.AddListener(()=>GetComponent<OfflineWakeClient>().ListenNow());activity.raycastTarget=true;
            interactionState=Label(g.transform,"待机",38,new Vector2(-520,-118),new Vector2(450,64));interactionState.color=Ink;
            wakeHint=Label(g.transform,"叫一声“小安”，我就在",26,new Vector2(-520,-172),new Vector2(450,64));wakeHint.color=Teal;micLabel=wakeHint;
            Button(g.transform,"结束对话",new Vector2(-520,-244),new Vector2(220,54),()=>GetComponent<OfflineWakeClient>().ListenNow());
            interruptButton=g.transform.Find("结束对话").gameObject;interruptButton.SetActive(false);
            var strip=Box(g.transform,"LargeSubtitles",new Vector2(0,-350),new Vector2(1552,148),new Color32(24,44,46,255));
            strip.AddComponent<RectMask2D>();var scroll=strip.AddComponent<ScrollRect>();scroll.horizontal=false;scroll.movementType=ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=45;
            subtitle=Label(strip.transform,"",44,Vector2.zero,new Vector2(1472,142));subtitle.lineSpacing=1.15f;subtitle.alignment=TextAnchor.UpperLeft;subtitle.rectTransform.anchorMin=subtitle.rectTransform.anchorMax=subtitle.rectTransform.pivot=new Vector2(.5f,1);subtitle.rectTransform.anchoredPosition=new Vector2(0,-16);subtitle.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;var viewport=Box(strip.transform,"SubtitleViewport",Vector2.zero,new Vector2(1472,116),Color.clear);
            viewport.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>().raycastTarget=false;
            viewport.AddComponent<RectMask2D>();subtitle.rectTransform.SetParent(viewport.transform,false);
            subtitle.rectTransform.anchoredPosition=Vector2.zero;
            scroll.viewport=viewport.GetComponent<RectTransform>();scroll.content=subtitle.rectTransform;
            shade=Box(g.transform,"ReminderBackdrop",Vector2.zero,new Vector2(4000,4000),new Color(0.04f,.10f,.10f,.42f));
            card=Box(g.transform,"CareCard",new Vector2(0,-132),new Vector2(1100,610),new Color32(250,252,248,255));
            var icon=Box(card.transform,"ReminderSymbol",new Vector2(-455,214),new Vector2(90,90),Teal);cardAccent=icon.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>();
            cardSymbol=Label(icon.transform,"✓",54,Vector2.zero,new Vector2(80,80));
            cardTitle=Label(card.transform,"关怀提醒",44,new Vector2(55,214),new Vector2(850,86));cardTitle.alignment=TextAnchor.MiddleLeft;cardTitle.fontStyle=FontStyle.Bold;cardTitle.color=Ink;
            Box(card.transform,"Divider",new Vector2(0,146),new Vector2(988,2),new Color32(216,229,221,255));
            body=Label(card.transform,"",40,new Vector2(0,24),new Vector2(988,220));body.alignment=TextAnchor.MiddleLeft;body.lineSpacing=1.22f;body.color=Ink;
            delivery=Label(card.transform,"",26,new Vector2(0,-136),new Vector2(988,84));delivery.color=Teal;
            Button(card.transform,"知道了",new Vector2(0,-239),new Vector2(530,80),Acknowledge);card.SetActive(false);shade.SetActive(false);

        }
        void Update()
        {
            if(!clock)return;
            clock.text=DateTime.Now.ToString("HH:mm");date.text=DateTime.Now.ToString("MM月dd日 dddd",System.Globalization.CultureInfo.GetCultureInfo("zh-CN"));
            subtitle.transform.parent.parent.gameObject.SetActive(current==null);
            var wake=GetComponent<OfflineWakeClient>();
            bool hearing=demo.IsRecording||(wake&&wake.State=="listening");
            bool speaking=demo.IsSpeaking;
            bool thinking=!speaking&&(demo.IsProcessing||(wake&&wake.State=="thinking"));
            string state=hearing?"在听":speaking?"在说话":thinking?"在想":"待机";
            interactionState.text=state;
            interruptButton.SetActive(current==null&&(hearing||speaking||thinking));
            interruptButton.GetComponentInChildren<Text>().text=hearing?"结束收音并发送":"结束对话";
            wakeHint.text=!listen?"监听已关闭 · 可在设置中开启":wake?wake.Hint:"正在连接本地唤醒";
            activity.Mode=hearing?1:speaking?3:thinking?2:0;
            activity.Level=wake?wake.Level:0;
            if(speaking){source.GetOutputData(outputSamples,0);float energy=0;foreach(float value in outputSamples)energy+=value*value;activity.Level=Mathf.Clamp01(Mathf.Sqrt(energy/outputSamples.Length)*5);}
            halo.gameObject.SetActive(current==null);interactionState.gameObject.SetActive(current==null);wakeHint.gameObject.SetActive(current==null);
            subtitle.color=hearing?new Color32(131,255,224,255):Color.white;
            var captions=GetComponent<SpeechSubtitleTrack>();
            string spoken=captions.Caption(subtitle);
            string text=hearing?GetComponent<SeniorCompanion>().Address("我在听，说完稍等，会自动发送"):!string.IsNullOrEmpty(spoken)?spoken:thinking?"听到了，让我想一想。":current!=null?current.text:demo.Answer;
            if(text=="本地数字人：输入文字或按录音按钮开始。")text=GetComponent<SeniorCompanion>().Address("您好，我在这里陪您。叫一声“小安”，就可以和我聊天。");
            if(subtitle.text!=text){subtitle.text=text;LayoutRebuilder.ForceRebuildLayoutImmediate(subtitle.rectTransform);subtitle.transform.parent.parent.GetComponent<ScrollRect>().verticalNormalizedPosition=1;}
        }
        void OnDestroy(){SuspendMicrophone();}
    }
}
