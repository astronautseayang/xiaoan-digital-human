using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
namespace LocalHuman
{
    // Explicit integration test only; normal startup does not create test alarms.
    public sealed class SeniorCareValidation : MonoBehaviour
    {
        [Serializable] sealed class Report {public bool passed,preempted,audioPlayed,acknowledged,gainSwitch,cardFits,clockFits;public int subtitleFont;public float deliverySeconds;public string error;}
        Report report=new Report();string folder="/home/yyy/digital-human/artifacts/validation/senior-care";
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-senior-care-self-test")>=0)new GameObject("SeniorCareValidation").AddComponent<SeniorCareValidation>();}
        IEnumerator Post(string url,string text)
        {
            using(var r=new UnityWebRequest(url,"POST")) {
                r.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes("{\"text\":\""+text+"\"}"));r.downloadHandler=new DownloadHandlerBuffer();r.SetRequestHeader("Content-Type","application/json");r.timeout=15;
                yield return r.SendWebRequest();if(r.result!=UnityWebRequest.Result.Success)report.error=r.error+" "+r.downloadHandler.text;
            }
        }
        void Awake(){Application.logMessageReceived+=OnLog;}
        void OnLog(string message,string stack,LogType type){if(type==LogType.Exception||type==LogType.Error)report.error=message;}
        IEnumerator Start()
        {
            Directory.CreateDirectory(folder);float deadline=Time.realtimeSinceStartup+60;
            while(!LocalHumanStartup.Ready&&Time.realtimeSinceStartup<deadline)yield return null;
            var demo=FindObjectOfType<LocalHumanDemo>();var care=demo?demo.GetComponent<SeniorCareClient>():null;
            if(!care){Finish("关怀组件未加载");yield break;}
            yield return new WaitForSecondsRealtime(1);
            var texts=care.GetComponentsInChildren<Text>(true);
            foreach(var t in texts) {
                if(t.transform.parent.name=="LargeSubtitles")report.subtitleFont=t.fontSize;
                if(t.transform.parent.name=="Clock"&&t.fontSize==72)report.clockFits=!string.IsNullOrEmpty(t.text)&&t.preferredHeight<=t.rectTransform.rect.height;
            }
            ScreenCapture.CaptureScreenshot(folder+"/standby.png");yield return new WaitForEndOfFrame();
            var source=demo.GetComponent<AudioSource>();
            var normal=AudioClip.Create("validation-regular",32000*30,1,32000,false);
            source.clip=normal;demo.StartCoroutine(demo.ReplayAudio());yield return new WaitForSecondsRealtime(.3f);
            float began=Time.realtimeSinceStartup;
            yield return Post(demo.gateway+"/api/care/command","救命，我跌倒了");
            deadline=Time.realtimeSinceStartup+8;
            while(!care.Active&&Time.realtimeSinceStartup<deadline)yield return null;
            report.deliverySeconds=Time.realtimeSinceStartup-began;
            report.preempted=care.Active&&source.clip!=normal;
            if(!care.Active){Finish("提醒未送达");yield break;}
            yield return new WaitForEndOfFrame();
            foreach(var t in texts)if(t.transform.parent.name=="CareCard"&&t.fontSize==40)report.cardFits=t.preferredHeight<=t.rectTransform.rect.height;
            var gain=demo.GetComponent<LocalHuman.AvatarPipeline.LocalHumanPanel>().VolumeToggle;
            var limiter=demo.GetComponent<SeniorAudioLimiter>();bool initial=limiter.LoudGain;gain.onClick.Invoke();report.gainSwitch=limiter.LoudGain!=initial;gain.onClick.Invoke();
            ScreenCapture.CaptureScreenshot(folder+"/emergency.png");
            deadline=Time.realtimeSinceStartup+100;
            while(Time.realtimeSinceStartup<deadline) {
                if(source.isPlaying&&source.clip&&source.clip.length>2&&source.clip!=normal){report.audioPlayed=true;break;}
                yield return null;
            }
            yield return Post(demo.gateway+"/api/care/command","知道了");
            deadline=Time.realtimeSinceStartup+5;
            while(care.Active&&Time.realtimeSinceStartup<deadline)yield return null;
            report.acknowledged=!care.Active&&!source.isPlaying;
            report.passed=string.IsNullOrEmpty(report.error)&&report.preempted&&report.audioPlayed&&report.acknowledged&&report.gainSwitch&&report.cardFits&&report.clockFits&&report.subtitleFont>=40&&report.deliverySeconds<3;
            Finish(report.passed?null:"运行时验收未通过，请查看报告");
        }
        void Finish(string error)
        {
            if(error!=null){report.error=error;report.passed=false;}
            File.WriteAllText(folder+"/runtime.json",JsonUtility.ToJson(report,true));Debug.Log("SENIOR_CARE "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);
        }
    }
}
