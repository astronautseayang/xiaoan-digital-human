using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
namespace LocalHuman
{
    [RequireComponent(typeof(AudioSource))]
    public sealed class LocalHumanDemo : MonoBehaviour
    {
        public string gateway = "http://127.0.0.1:9881";
        string input = "";
        string answer = "本地数字人：输入文字或按录音按钮开始。";
        public Font chineseFont;
        public TextAsset portraitBytes, clothBytes, bodySkinBytes, bodyFabricBytes;
        IEnumerator Start()
        {
            using(var r=UnityWebRequest.Get(gateway+"/api/voice")){yield return r.SendWebRequest();if(r.result==UnityWebRequest.Result.Success)VoiceName=JsonUtility.FromJson<Result>(r.downloadHandler.text).text;}
        }
        void Awake()
        {
            Input.imeCompositionMode=IMECompositionMode.On;
            gameObject.AddComponent<LocalHuman.AvatarPipeline.LocalHumanPanel>();
            gameObject.AddComponent<SeniorCareClient>();
            gameObject.AddComponent<OfflineWakeClient>();
            gameObject.AddComponent<AvatarViewMode>();
            gameObject.AddComponent<SeniorCompanion>();
            gameObject.AddComponent<SpeakerInputClient>();
            gameObject.AddComponent<WeatherClient>();
            gameObject.AddComponent<SpeechSubtitleTrack>();
            // Photo pixels are deliberately absent from the runtime material pipeline.
        }
        bool busy;string activeJob="";
        AudioClip microphone;
        float recordingStarted;
        bool enrolling, speakerEnrolling;
        public string VoiceName { get; private set; } = "默认音色";
        public bool IsEnrolling => (enrolling || speakerEnrolling) && microphone;
        public bool IsSpeakerEnrolling => speakerEnrolling && microphone;
        const string VoicePrompt = "你好，很高兴认识你。今天阳光很好，我想用自己的声音和你聊聊天。";
        string stage = "就绪";
        public bool IsProcessing => busy;
        public bool IsSpeaking => GetComponent<AudioSource>().isPlaying;
        public bool IsBusy => busy || (GetComponent<SeniorCareClient>() && GetComponent<SeniorCareClient>().Active);
        public int PlaybackStarts { get; private set; }
        public string LastPlaybackError { get; private set; }
        public float FirstTextSeconds { get; private set; }
        public float FirstAudioSeconds { get; private set; }
        public IEnumerator ReplayAudio()
        {
            var source = GetComponent<AudioSource>();
            if (!source.clip) yield break;
            busy = true;
            try { GetComponent<AvatarInteractiveMotion>()?.BeginUtterance(); yield return PlayChecked(source.clip,replayText,replayCues); }
            finally { busy = false; }
        }
        string replayText="";
        List<SpeechSubtitleTrack.Cue> replayCues=new List<SpeechSubtitleTrack.Cue>();
        sealed class SpokenClip { public AudioClip audio; public string text; }
        IEnumerator PlayChecked(AudioClip clip,string spokenText=null,List<SpeechSubtitleTrack.Cue> timeline=null)
        {
            LastPlaybackError = "";
            var source = GetComponent<AudioSource>();
            stage = "准备播放…";
            float deadline = Time.realtimeSinceStartup + 5;
            while (clip && clip.loadState == AudioDataLoadState.Loading && Time.realtimeSinceStartup < deadline) yield return null;
            if (!clip || clip.loadState != AudioDataLoadState.Loaded || clip.samples == 0)
            { LastPlaybackError = "音频尚未正确解码，请重试。"; answer += "\n" + LastPlaybackError; yield break; }
            if (microphone && Microphone.IsRecording(null)) Microphone.End(null);
            source.Stop();
            if (source.clip && source.clip != clip) Destroy(source.clip);
            source.clip = clip; source.mute = false; source.volume = 1; source.pitch = 1;
            AudioListener.pause = false; AudioListener.volume = 1;
            replayText=spokenText??"";
            replayCues=timeline!=null?new List<SpeechSubtitleTrack.Cue>(timeline):new List<SpeechSubtitleTrack.Cue>{new SpeechSubtitleTrack.Cue(0,clip.length,replayText)};
            GetComponent<SpeechSubtitleTrack>().Bind(source,replayCues);
            GetComponent<AvatarInteractiveMotion>()?.PrepareSpeech(replayText);
            for (int attempt = 0; attempt < 2; attempt++)
            {
                source.Play();
                yield return new WaitForSecondsRealtime(.12f);
                if (source.isPlaying) break;
                Debug.LogWarning("VOICE playback start retry " + attempt);
            }
            if (!source.isPlaying)
            { LastPlaybackError = "播放设备未开始输出，请检查系统声音后点击重播。"; answer += "\n" + LastPlaybackError; Debug.LogWarning(LastPlaybackError); yield break; }
            PlaybackStarts++;
            Debug.Log("VOICE playback started duration=" + clip.length + " device=" + AudioSettings.driverCapabilities);
            stage = "正在回答…";
            deadline = Time.realtimeSinceStartup + clip.length + 5;
            while (source.isPlaying && Time.realtimeSinceStartup < deadline) yield return null;
            stage = "正在准备后续语音…";
            Debug.Log("VOICE playback completed");
        }
        [Serializable] sealed class Message { public string role; public string content; }
        [Serializable] sealed class Chat { public string text; public List<Message> history; }
        [Serializable] sealed class Result { public string text; public string input_notice; public string care_command; public string audio_url; public string transcript; public string id; public bool done; public bool text_done; public bool truncated; public string error; public Result[] clips; }
        readonly List<Message> history = new List<Message>();
        public Material glassMaterial;
        public string Answer => answer;
        public string Question { get => input; set => input=value; }
        public bool IsRecording => microphone;
        public bool HasReplay => GetComponent<AudioSource>().clip;
        public string Status => IsSpeakerEnrolling ? "识别声音录入中 · 单独说话5–10秒" : IsEnrolling ? "音色录入中 · 5–10秒，再点停止" : microphone ? "正在录音 · 点击停止，最长15秒" : busy ? stage : "就绪 · 随时开始对话";
        public void SubmitQuestion(){if(!IsBusy&&!microphone&&!string.IsNullOrWhiteSpace(input))StartCoroutine(ChatWithAudio(input));}
        public void OpenNativeInput(){if(!IsBusy&&!microphone)GetComponent<LocalHuman.AvatarPipeline.LocalHumanPanel>().FocusInput();}
        public void ReplayLast(){if(!IsBusy&&!microphone&&HasReplay)StartCoroutine(ReplayAudio());}
        public void ToggleRecording(){if(IsBusy)return;if(microphone)StopRecording();else { enrolling=false;speakerEnrolling=false; StartCoroutine(StartRecording()); }}
        public void ToggleVoiceEnrollment()
        {
            if(IsBusy)return;
            if(microphone){if(enrolling)StopRecording();return;}
            speakerEnrolling=false;enrolling=true;answer="请自然朗读（5–10秒）：\n"+VoicePrompt;
            StartCoroutine(StartRecording());
        }
        public void ToggleSpeakerEnrollment()
        {
            if(IsBusy)return;
            if(microphone){if(speakerEnrolling)StopRecording();return;}
            enrolling=false;speakerEnrolling=true;
            answer="请您单独自然说话五到十秒，期间不要让其他人说话。\n例如：小安，我今天感觉很好，请记住我的声音，以后只接收我的语音。";
            StartCoroutine(StartRecording());
        }
        IEnumerator EnrollSpeaker(byte[] wav)
        {
            busy=true;stage="正在核对并保存识别声音…";
            try {
                var form=new List<IMultipartFormSection>{new MultipartFormFileSection("file",wav,"speaker.wav","audio/wav")};
                using(var r=UnityWebRequest.Post(gateway+"/api/speaker/enroll",form)) {
                    r.timeout=90;yield return r.SendWebRequest();
                    if(r.result!=UnityWebRequest.Result.Success){answer="识别声音录入失败："+SpeakerInputClient.ErrorText(r.downloadHandler.text);yield break;}
                    answer="识别声音已录入，已开启只听我的声音。环境较吵或多人同时说话时，请靠近麦克风单独重说。";
                }
                yield return GetComponent<SpeakerInputClient>().Refresh();
            } finally {busy=false;speakerEnrolling=false;}
        }
        public void ResetVoice(){if(!IsBusy&&!microphone)StartCoroutine(ResetVoiceRoutine());}
        IEnumerator ResetVoiceRoutine()
        {
            busy=true;stage="正在恢复默认音色…";
            using(var r=UnityWebRequest.Post(gateway+"/api/voice/reset",new List<IMultipartFormSection>()))
            {yield return r.SendWebRequest();if(r.result==UnityWebRequest.Result.Success)VoiceName=JsonUtility.FromJson<Result>(r.downloadHandler.text).text;else answer="音色恢复失败："+r.error;}
            busy=false;
        }
        public IEnumerator EnrollVoice(byte[] wav)
        {
            busy=true;stage="正在分析音色并生成试听…";
            try {
                var form=new List<IMultipartFormSection>{new MultipartFormFileSection("file",wav,"reference.wav","audio/wav")};
                Result result=null;
                using(var r=UnityWebRequest.Post(gateway+"/api/voice/enroll",form))
                {
                    r.timeout=180;yield return r.SendWebRequest();
                    if(r.result!=UnityWebRequest.Result.Success){answer="音色录入失败："+r.downloadHandler.text;yield break;}
                    result=JsonUtility.FromJson<Result>(r.downloadHandler.text);
                }
                VoiceName=result.text;answer="音色已启用，后续回答将使用此声音。\n识别内容："+result.transcript+"\n若识别有误或试听不清晰，请重新录入。";
                using(var r=UnityWebRequestMultimedia.GetAudioClip(gateway+result.audio_url,AudioType.WAV))
                {yield return r.SendWebRequest();if(r.result==UnityWebRequest.Result.Success)yield return PlayChecked(DownloadHandlerAudioClip.GetContent(r));}
            } finally {busy=false;enrolling=false;}
        }
        void Update()
        {
            if (microphone && Time.realtimeSinceStartup - recordingStarted > .75f && !Microphone.IsRecording(null)) StopRecording();
        }
        IEnumerator StartRecording()
        {
            GetComponent<SpeechSubtitleTrack>().Clear();
            GetComponent<SeniorCareClient>()?.SuspendMicrophone();
            busy = true;
            yield return Application.RequestUserAuthorization(UserAuthorization.Microphone);
            busy = false;
            if (!Application.HasUserAuthorization(UserAuthorization.Microphone) || Microphone.devices.Length == 0)
            { answer = "没有麦克风权限或设备。"; yield break; }
            GetComponent<AudioSource>().Stop();
            recordingStarted = Time.realtimeSinceStartup;
            microphone = Microphone.Start(null, false, (enrolling || speakerEnrolling) ? 10 : 15, 16000);
            Debug.Log("VOICE recording started");
        }
        void StopRecording()
        {
            int count = Microphone.GetPosition(null);
            if (count <= 0 && Time.realtimeSinceStartup - recordingStarted >= ((enrolling || speakerEnrolling) ? 9.5f : 14.5f)) count = microphone.samples;
            Microphone.End(null);
            if (count < microphone.frequency / 4)
            { Destroy(microphone); microphone = null; answer = "录音过短。"; return; }
            var samples = new float[count * microphone.channels];
            microphone.GetData(samples, 0);
            byte[] wav;
            using (var stream = new MemoryStream())
            using (var writer = new BinaryWriter(stream))
            {
                writer.Write(Encoding.ASCII.GetBytes("RIFF")); writer.Write(36 + samples.Length * 2);
                writer.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); writer.Write(16);
                writer.Write((short)1); writer.Write((short)microphone.channels);
                writer.Write(microphone.frequency); writer.Write(microphone.frequency * microphone.channels * 2);
                writer.Write((short)(microphone.channels * 2)); writer.Write((short)16);
                writer.Write(Encoding.ASCII.GetBytes("data")); writer.Write(samples.Length * 2);
                foreach (float s in samples) writer.Write((short)(Mathf.Clamp(s, -1, 1) * 32767));
                wav = stream.ToArray();
            }
            Destroy(microphone); microphone = null;
            if(speakerEnrolling)StartCoroutine(EnrollSpeaker(wav));else if(enrolling)StartCoroutine(EnrollVoice(wav));else StartCoroutine(Recognize(wav));
        }
        public IEnumerator Recognize(byte[] wav)
        {
            busy = true;
            stage = "正在识别录音…";
            string text = null, notice = null;
            var form = new List<IMultipartFormSection> { new MultipartFormFileSection("file", wav, "speech.wav", "audio/wav") };
            using (var request = UnityWebRequest.Post(gateway + "/api/asr", form))
            {
                request.timeout = 120;
                yield return request.SendWebRequest();
                if (request.result == UnityWebRequest.Result.Success)
                {
                    try {
                        var recognized=JsonUtility.FromJson<Result>(request.downloadHandler.text);
                        text=recognized.text;notice=recognized.input_notice;
                        if(!string.IsNullOrEmpty(recognized.care_command))text=null;
                    }
                    catch (Exception e) { answer = "识别响应异常：" + e.Message; }
                }
                else answer = "识别失败：" + request.error;
            }
            busy = false;
            if (string.IsNullOrWhiteSpace(text)) answer=string.IsNullOrEmpty(notice)?"未识别到有效语音，请重新录音。":notice;
            if (!string.IsNullOrWhiteSpace(text)) { input = text; yield return ChatWithAudio(text); }
        }
        public IEnumerator ChatWithAudio(string text)
        {
            if(IsBusy)yield break;
            busy=true;stage="正在思考…";
            GetComponent<SpeechSubtitleTrack>().Clear();
            GetComponent<AvatarInteractiveMotion>()?.BeginUtterance();
            float started=Time.realtimeSinceStartup;FirstTextSeconds=FirstAudioSeconds=-1;int initialPlays=PlaybackStarts;
            var combinedCues=new List<SpeechSubtitleTrack.Cue>();
            var replaySamples=new List<float>();int replayRate=0,replayChannels=0;
            var clips=new Queue<SpokenClip>();bool playback=false;Coroutine player=null;
            try
            {
                Result result=null;
                using(var r=new UnityWebRequest(gateway+"/api/chat/jobs","POST"))
                {
                    r.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new Chat{text=text,history=history})));
                    r.downloadHandler=new DownloadHandlerBuffer();r.SetRequestHeader("Content-Type","application/json");r.timeout=15;
                    yield return r.SendWebRequest();
                    if(r.result!=UnityWebRequest.Result.Success){answer="对话失败："+r.downloadHandler.text;yield break;}
                    result=JsonUtility.FromJson<Result>(r.downloadHandler.text);
                }
                string id=result.id;activeJob=id;int received=0;float deadline=Time.realtimeSinceStartup+240;
                // Download/poll runs alongside playback so subsequent clips are prefetched.
                player=StartCoroutine(PlayQueue(clips,v=>playback=v));
                while(Time.realtimeSinceStartup<deadline)
                {
                    using(var r=UnityWebRequest.Get(gateway+"/api/chat/jobs/"+id))
                    {
                        r.timeout=15;yield return r.SendWebRequest();
                        if(r.result!=UnityWebRequest.Result.Success){answer+="\n连接失败："+r.error;yield break;}
                        result=JsonUtility.FromJson<Result>(r.downloadHandler.text);
                    }
                    if(!string.IsNullOrEmpty(result.text)){
                        answer=result.text;if(FirstTextSeconds<0)FirstTextSeconds=Time.realtimeSinceStartup-started;
                    }
                    if(PlaybackStarts>initialPlays&&FirstAudioSeconds<0)FirstAudioSeconds=Time.realtimeSinceStartup-started;
                    if(!IsSpeaking)stage=result.text_done?"文字已生成 · 正在合成后续语音…":"正在生成文字…";
                    if(result.clips!=null)while(received<result.clips.Length)
                    {
                        using(var r=UnityWebRequestMultimedia.GetAudioClip(gateway+result.clips[received].audio_url,AudioType.WAV))
                        {
                            r.timeout=60;yield return r.SendWebRequest();
                            if(r.result!=UnityWebRequest.Result.Success){answer+="\n音频下载失败："+r.error;yield break;}
                            var clip=DownloadHandlerAudioClip.GetContent(r);
                            if(replayRate==0){replayRate=clip.frequency;replayChannels=clip.channels;}
                            if(clip.frequency==replayRate&&clip.channels==replayChannels){
                                float cueStart=replaySamples.Count/(float)(replayRate*replayChannels);
                                combinedCues.Add(new SpeechSubtitleTrack.Cue(cueStart,cueStart+clip.samples/(float)clip.frequency,result.clips[received].text));
                                var pcm=new float[clip.samples*clip.channels];clip.GetData(pcm,0);replaySamples.AddRange(pcm);
                            }
                            clips.Enqueue(new SpokenClip{audio=clip,text=result.clips[received].text});received++;
                        }
                    }
                    if(result.done)break;
                    yield return new WaitForSecondsRealtime(.15f);
                }
                if(result.truncated)answer+="\n（已达到单次回答长度上限，可发送“继续”接着回答。）";
                if(!result.done){answer+="\n回答等待超时，请重试。";yield break;}
                if(!string.IsNullOrEmpty(result.error)){answer+="\n"+result.error;yield break;}
                history.Add(new Message{role="user",content=text});history.Add(new Message{role="assistant",content=result.text});
                while(history.Count>12)history.RemoveRange(0,2);
                while(clips.Count>0||playback){
                    if(PlaybackStarts>initialPlays&&FirstAudioSeconds<0)FirstAudioSeconds=Time.realtimeSinceStartup-started;
                    yield return null;
                }
                if(replaySamples.Count>0){
                    var source=GetComponent<AudioSource>();var full=AudioClip.Create("完整回答",replaySamples.Count/replayChannels,replayChannels,replayRate,false);
                    replayText=result.text;replayCues=combinedCues;full.SetData(replaySamples.ToArray(),0);if(source.clip)Destroy(source.clip);source.clip=full;
                }
                Debug.Log("CHAT firstText="+FirstTextSeconds+" firstAudio="+FirstAudioSeconds);
            }
            finally
            {
                if(player!=null)StopCoroutine(player);
                while(clips.Count>0)Destroy(clips.Dequeue().audio);
                busy=false;
            }
        }
        IEnumerator PlayQueue(Queue<SpokenClip> clips,Action<bool> setPlaying)
        {
            while(true)
            {
                if(clips.Count==0){yield return null;continue;}
                var next=clips.Dequeue();setPlaying(true);yield return PlayChecked(next.audio,next.text);setPlaying(false);
            }
        }
        public void ShowInterrupted(){GetComponent<SpeechSubtitleTrack>().Clear();answer="已结束本次对话。想说话时，再叫一声“小安”。";stage="已结束对话";}
        IEnumerator CancelJob(string id)
        {
            using(var r=UnityWebRequest.Delete(gateway+"/api/chat/jobs/"+id)){r.timeout=10;yield return r.SendWebRequest();}
        }
        public void InterruptForCare()
        {
            string cancelledJob=activeJob;activeJob="";
            StopAllCoroutines();busy=false;enrolling=false;speakerEnrolling=false;
            if(!string.IsNullOrEmpty(cancelledJob))StartCoroutine(CancelJob(cancelledJob));
            if(microphone){Microphone.End(null);Destroy(microphone);microphone=null;}
            GetComponent<AudioSource>().Stop();
            GetComponent<SpeechSubtitleTrack>().Clear();
        }
        void OnDestroy()
        {
            if (microphone) { Microphone.End(null); Destroy(microphone); }
            var source = GetComponent<AudioSource>();
            if (source && source.clip) Destroy(source.clip);
        }
    }
}
