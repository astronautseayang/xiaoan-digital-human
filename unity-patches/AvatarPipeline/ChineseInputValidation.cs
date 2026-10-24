using System;
using System.Collections;
using System.IO;
using UnityEngine;
using LocalHuman.AvatarPipeline;
namespace LocalHuman
{
    public sealed class ChineseInputValidation:MonoBehaviour
    {
        const string Folder="/home/yyy/digital-human/artifacts/validation/chinese-input";
        string runtimeError;
        void Awake(){Application.logMessageReceived+=OnLog;}
        void OnDestroy(){Application.logMessageReceived-=OnLog;}
        void OnLog(string value,string stack,LogType type){if(type==LogType.Exception||type==LogType.Error)runtimeError=value;}
        [Serializable] sealed class Report {public string stage,text,error;public bool passed,insideWindow,noPrematureSubmit,simplifiedPaste;}
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-chinese-input-self-test")>=0)new GameObject("ChineseInputValidation").AddComponent<ChineseInputValidation>();}
        IEnumerator Start()
        {
            Directory.CreateDirectory(Folder);var report=new Report();
            float deadline=Time.realtimeSinceStartup+60;
            while(!LocalHumanStartup.Ready&&Time.realtimeSinceStartup<deadline)yield return null;
            var demo=FindObjectOfType<LocalHumanDemo>();var panel=demo.GetComponent<LocalHumanPanel>();
            panel.FocusInput();yield return new WaitForSecondsRealtime(.3f);
            var field=(ChineseInputField)panel.Input;field.text="";
            report.stage="awaiting_keyboard";Save(report);
            deadline=Time.realtimeSinceStartup+60;
            while(field.text!="你好爷爷今天天气很好。"&&Time.realtimeSinceStartup<deadline)yield return null;
            report.text=field.text;report.simplifiedPaste=field.text=="你好爷爷今天天气很好。";
            report.insideWindow=panel.IsVisible&&field.isFocused;
            report.noPrematureSubmit=!demo.IsProcessing&&!demo.IsSpeaking&&demo.Question==field.text;
            report.passed=report.simplifiedPaste&&report.insideWindow&&report.noPrematureSubmit&&string.IsNullOrEmpty(runtimeError);
            report.error=report.passed?"":runtimeError??"检查输入结果、焦点或提交状态";report.stage="done";
            yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Folder+"/input.png");yield return new WaitForSecondsRealtime(.3f);
            Save(report);Application.Quit(report.passed?0:2);
        }
        void Save(Report r){File.WriteAllText(Folder+"/runtime.json",JsonUtility.ToJson(r,true));}
    }
}
