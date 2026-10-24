using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
namespace LocalHuman
{
    public sealed class SpeechSubtitleValidation : MonoBehaviour
    {
        const string Folder="/home/yyy/digital-human/artifacts/validation/speech-subtitles";
        [Serializable] sealed class Report {
            public bool passed,firstPage,advancedPage,twoLines,nextSegment,replayTimeline,heldAfterCompletion,interrupted;
            public string first,middle,next,replay,error;
        }
        Report report=new Report();
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-subtitle-sync-self-test")>=0)new GameObject("SpeechSubtitleValidation").AddComponent<SpeechSubtitleValidation>();}
        void Awake(){Application.logMessageReceived+=OnLog;}
        void OnLog(string text,string stack,LogType type){if(type==LogType.Error||type==LogType.Exception)report.error=text;}
        IEnumerator Start()
        {
            float deadline=Time.realtimeSinceStartup+60;
            while(!LocalHumanStartup.Ready&&Time.realtimeSinceStartup<deadline)yield return null;
            var demo=FindObjectOfType<LocalHumanDemo>();if(!demo){Finish("数字人未加载");yield break;}
            var care=demo.GetComponent<SeniorCareClient>();
            if(care.Active){Finish("关怀提醒正在显示，请完成提醒后再验证");yield break;}
            var track=demo.GetComponent<SpeechSubtitleTrack>();var source=demo.GetComponent<AudioSource>();
            var subtitle=GameObject.Find("SubtitleViewport").GetComponentInChildren<Text>();
            string[] texts=File.ReadAllLines(Folder+"/texts.txt");var audio=new List<AudioClip>();
            foreach(string name in new[]{"first","second"}) {
                using(var request=UnityWebRequestMultimedia.GetAudioClip(new Uri(Folder+"/"+name+".wav").AbsoluteUri,AudioType.WAV)) {
                    yield return request.SendWebRequest();if(request.result!=UnityWebRequest.Result.Success){Finish(request.error);yield break;}
                    audio.Add(DownloadHandlerAudioClip.GetContent(request));
                }
            }
            // The generated answer is already complete; captions must follow audio instead.
            typeof(LocalHumanDemo).GetField("answer",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(demo,texts[0]+texts[1]);
            var play=typeof(LocalHumanDemo).GetMethod("PlayChecked",BindingFlags.Instance|BindingFlags.NonPublic);
            var playing=demo.StartCoroutine((IEnumerator)play.Invoke(demo,new object[]{audio[0],texts[0],null}));
            yield return new WaitForSecondsRealtime(.4f);report.first=subtitle.text;
            report.firstPage=texts[0].StartsWith(report.first)&&!string.IsNullOrEmpty(report.first)&&report.first.Length<texts[0].Length&&!report.first.Contains(texts[1].Substring(0,6));
            report.twoLines=Fits(subtitle);ScreenCapture.CaptureScreenshot(Folder+"/first-page.png");yield return new WaitForEndOfFrame();
            source.timeSamples=(int)(audio[0].samples*.65f);yield return new WaitForSecondsRealtime(.12f);
            report.middle=subtitle.text;report.advancedPage=report.middle!=report.first&&texts[0].Contains(report.middle);
            report.twoLines&=Fits(subtitle);ScreenCapture.CaptureScreenshot(Folder+"/later-page.png");yield return new WaitForEndOfFrame();
            demo.StopCoroutine(playing);source.Stop();
            playing=demo.StartCoroutine((IEnumerator)play.Invoke(demo,new object[]{audio[1],texts[1],null}));
            yield return new WaitForSecondsRealtime(.4f);report.next=subtitle.text;
            report.nextSegment=texts[1].StartsWith(report.next)&&report.next!=report.middle&&Fits(subtitle);
            demo.StopCoroutine(playing);source.Stop();
            // Replaying the concatenated answer must retain the exact clip boundaries.
            // PlayChecked disposes the previous source clip, so reload the first WAV.
            using(var request=UnityWebRequestMultimedia.GetAudioClip(new Uri(Folder+"/first.wav").AbsoluteUri,AudioType.WAV)) {
                yield return request.SendWebRequest();audio[0]=DownloadHandlerAudioClip.GetContent(request);
            }
            int rate=audio[0].frequency,channels=audio[0].channels,firstCount=audio[0].samples;
            var pcm=new float[(audio[0].samples+audio[1].samples)*channels];var tail=new float[audio[1].samples*channels];
            var head=new float[firstCount*channels];audio[0].GetData(head,0);Array.Copy(head,pcm,head.Length);audio[1].GetData(tail,0);Array.Copy(tail,0,pcm,firstCount*channels,tail.Length);
            var full=AudioClip.Create("字幕验证完整回答",pcm.Length/channels,channels,rate,false);full.SetData(pcm,0);
            var cues=new List<SpeechSubtitleTrack.Cue>{new SpeechSubtitleTrack.Cue(0,audio[0].length,texts[0]),new SpeechSubtitleTrack.Cue(audio[0].length,full.length,texts[1])};
            playing=demo.StartCoroutine((IEnumerator)play.Invoke(demo,new object[]{full,texts[0]+texts[1],cues}));
            yield return new WaitForSecondsRealtime(.3f);bool replayFirst=subtitle.text==report.first;
            source.timeSamples=firstCount+(int)(tail.Length/(float)channels*.02f);yield return new WaitForSecondsRealtime(.12f);
            report.replay=subtitle.text;report.replayTimeline=replayFirst&&report.replay==report.next;
            source.timeSamples=full.samples-rate/2;yield return new WaitForSecondsRealtime(.15f);
            string last=subtitle.text;yield return new WaitForSecondsRealtime(.6f);
            report.heldAfterCompletion=!source.isPlaying&&subtitle.text==last&&last.Length>0&&texts[1].EndsWith(last)&&Fits(subtitle);
            demo.GetComponent<OfflineWakeClient>().Interrupt();yield return new WaitForSecondsRealtime(.6f);
            report.interrupted=!track.HasCaption&&subtitle.text.Contains("已结束");
            report.passed=report.firstPage&&report.advancedPage&&report.twoLines&&report.nextSegment&&report.replayTimeline&&report.heldAfterCompletion&&report.interrupted&&string.IsNullOrEmpty(report.error);
            Finish(report.passed?null:"请检查字幕验证报告");
        }
        bool Fits(Text text){return text.cachedTextGenerator.lineCount<=2;}
        void Finish(string error){if(error!=null){report.error=error;report.passed=false;}File.WriteAllText(Folder+"/runtime.json",JsonUtility.ToJson(report,true));Debug.Log("SPEECH_SUBTITLES "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);}
    }
}
