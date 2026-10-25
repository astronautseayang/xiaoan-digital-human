using System;
using System.Collections;
using System.IO;
using UnityEngine;
using LocalHuman.AvatarPipeline;
namespace LocalHuman
{
    // Runs only with the explicit flag. Feed real microphone audio externally;
    // this validator never fabricates a WebSocket wake event.
    public sealed class OfflineWakeValidation : MonoBehaviour
    {
        [Serializable] sealed class Report {
            public bool passed,connected,drawerHidden,drawerOpens,woke,nodded,highlighted,chime,transcript,speaking,silenceReturned;
            public bool cancelListening,cancelSpeaking,wakeAgain,twoLines,fullBody,portraitRestored,manualFinish,automaticFinish,salutationSettings;public float silenceSeconds;public string stage,error;
        }
        Report report=new Report();string folder="/home/yyy/digital-human/artifacts/validation/offline-wake";
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-offline-wake-self-test")>=0)new GameObject("OfflineWakeValidation").AddComponent<OfflineWakeValidation>();}
        void Save(string stage){report.stage=stage;File.WriteAllText(folder+"/unity-runtime.json",JsonUtility.ToJson(report,true));}
        void Awake(){Application.logMessageReceived+=OnLog;}
        void OnLog(string message,string stack,LogType type){if(type==LogType.Error||type==LogType.Exception)report.error=message;}
        IEnumerator Start()
        {
            Directory.CreateDirectory(folder);float end=Time.realtimeSinceStartup+60;
            while(!LocalHumanStartup.Ready&&Time.realtimeSinceStartup<end)yield return null;
            var demo=FindObjectOfType<LocalHumanDemo>();var wake=demo?demo.GetComponent<OfflineWakeClient>():null;
            if(!wake){Finish("唤醒组件未加载");yield break;}
            while(!wake.Ready&&Time.realtimeSinceStartup<end)yield return null;
            report.connected=wake.Ready;
            var panel=demo.GetComponent<LocalHumanPanel>();report.drawerHidden=!panel.IsVisible;
            panel.ToggleDrawer();yield return null;report.drawerOpens=panel.IsVisible;
            var companion=demo.GetComponent<SeniorCompanion>();string originalAddress=companion.Salutation;
            for(int i=0;i<3;i++) {
                companion.Cycle();float saveEnd=Time.realtimeSinceStartup+12;
                while(companion.Saving&&Time.realtimeSinceStartup<saveEnd)yield return null;
                if(!string.IsNullOrEmpty(companion.Error)){Finish(companion.Error);yield break;}
            }
            report.salutationSettings=companion.Salutation==originalAddress;
            ScreenCapture.CaptureScreenshot(folder+"/settings.png");yield return new WaitForEndOfFrame();
            panel.CloseDrawer();yield return new WaitForSecondsRealtime(.5f);
            var view=demo.GetComponent<AvatarViewMode>();bool originalFull=view.FullBody;
            view.SetFullBody(false);var portraitPosition=Camera.main.transform.position;
            panel.FullView.onClick.Invoke();
            yield return new WaitForSecondsRealtime(.5f);
            report.fullBody=view.FullBody&&Camera.main.transform.position.z>2;
            ScreenCapture.CaptureScreenshot(folder+"/full-body.png");yield return new WaitForEndOfFrame();
            panel.PortraitView.onClick.Invoke();yield return null;
            report.portraitRestored=!view.FullBody&&Vector3.Distance(Camera.main.transform.position,portraitPosition)<.001f;
            view.SetFullBody(originalFull);
            ScreenCapture.CaptureScreenshot(folder+"/standby.png");Save("awaiting_real_audio");
            end=Time.realtimeSinceStartup+45;
            while(wake.State!="listening"&&Time.realtimeSinceStartup<end)yield return null;
            if(wake.State!="listening"){Finish("真实音频未唤醒");yield break;}
            report.woke=true;
            var ding=demo.transform.Find("GentleWakeChime");report.chime=ding&&ding.GetComponent<AudioSource>().isPlaying;
            yield return new WaitForSecondsRealtime(.25f);
            report.nodded=demo.GetComponent<AvatarInteractiveMotion>().FocusWeight>.2f;
            report.highlighted=wake.Hint.Contains("您慢慢说");
            ScreenCapture.CaptureScreenshot(folder+"/listening.png");Save("listening");
            yield return new WaitForSecondsRealtime(.8f);
            bool automatic=Array.IndexOf(Environment.GetCommandLineArgs(),"-automatic-capture-test")>=0;
            if(automatic) {
                end=Time.realtimeSinceStartup+20;
                while(wake.State=="listening"&&Time.realtimeSinceStartup<end)yield return null;
                report.automaticFinish=wake.State=="thinking"||demo.IsProcessing||demo.IsSpeaking;
            } else {wake.FinishListening();report.manualFinish=wake.State=="thinking";}
            end=Time.realtimeSinceStartup+120;
            while(!demo.IsSpeaking&&Time.realtimeSinceStartup<end){if(wake.State=="thinking")report.transcript=true;yield return null;}
            report.speaking=demo.IsSpeaking;report.transcript=report.transcript&&!string.IsNullOrWhiteSpace(demo.Question);
            if(report.speaking)ScreenCapture.CaptureScreenshot(folder+"/speaking.png");Save("response");
            while((demo.IsProcessing||demo.IsSpeaking)&&Time.realtimeSinceStartup<end)yield return null;
            yield return new WaitForSecondsRealtime(1);
            wake.ListenNow();end=Time.realtimeSinceStartup+3;
            while(wake.State!="listening"&&Time.realtimeSinceStartup<end)yield return null;
            float began=Time.realtimeSinceStartup;bool listening=wake.State=="listening";end=began+8;
            while(wake.State=="listening"&&Time.realtimeSinceStartup<end)yield return null;
            report.silenceSeconds=Time.realtimeSinceStartup-began;
            report.silenceReturned=listening&&wake.State=="idle"&&report.silenceSeconds>=5&&report.silenceSeconds<7;
            yield return new WaitForSecondsRealtime(.6f);ScreenCapture.CaptureScreenshot(folder+"/returned-idle.png");
            wake.ListenNow();end=Time.realtimeSinceStartup+4;
            while(wake.State!="listening"&&Time.realtimeSinceStartup<end)yield return null;
            wake.Interrupt();yield return new WaitForSecondsRealtime(.8f);
            report.cancelListening=wake.State=="idle"&&!demo.IsProcessing&&!demo.IsSpeaking;
            wake.ListenNow();end=Time.realtimeSinceStartup+4;
            while(wake.State!="listening"&&Time.realtimeSinceStartup<end)yield return null;
            report.wakeAgain=wake.State=="listening";
            wake.Interrupt();yield return new WaitForSecondsRealtime(.8f);
            demo.Question="你好，请介绍一下你自己。";demo.SubmitQuestion();end=Time.realtimeSinceStartup+60;
            while(!demo.IsSpeaking&&Time.realtimeSinceStartup<end)yield return null;
            bool played=demo.IsSpeaking;wake.Interrupt();yield return new WaitForSecondsRealtime(1);
            report.cancelSpeaking=played&&!demo.IsProcessing&&!demo.IsSpeaking&&wake.State=="idle";
            var viewport=GameObject.Find("SubtitleViewport").GetComponent<RectTransform>();
            var subtitle=viewport.GetComponentInChildren<UnityEngine.UI.Text>();
            var settings=GameObject.Find("设置").GetComponent<RectTransform>();
            report.twoLines=viewport.rect.height==116&&subtitle.fontSize==44&&settings.anchoredPosition.x==608;
            ScreenCapture.CaptureScreenshot(folder+"/manual-interrupted.png");yield return new WaitForEndOfFrame();
            report.passed=report.fullBody&&report.portraitRestored&&report.salutationSettings&&(report.manualFinish||report.automaticFinish)&&report.cancelListening&&report.cancelSpeaking&&report.wakeAgain&&report.twoLines&&report.connected&&report.drawerHidden&&report.drawerOpens&&report.woke&&report.nodded&&report.highlighted&&report.chime&&report.transcript&&report.speaking&&report.silenceReturned&&string.IsNullOrEmpty(report.error);
            Finish(report.passed?null:"请检查运行报告");
        }
        void Finish(string error){if(error!=null){report.error=error;report.passed=false;}Save("finished");Debug.Log("OFFLINE_WAKE "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);}
    }
}
