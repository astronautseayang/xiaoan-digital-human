using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
namespace LocalHuman
{
    public sealed class SpeakerInputClient : MonoBehaviour
    {
        [Serializable] sealed class Profile { public bool enabled; public bool enrolled; public string detail; }
        [Serializable] sealed class Setting { public bool enabled; }
        public bool Enabled { get; private set; }
        public bool Enrolled { get; private set; }
        public bool Saving { get; private set; }
        public string Error { get; private set; } = "";
        string Gateway => GetComponent<LocalHumanDemo>().gateway;
        IEnumerator Start(){yield return Refresh();}
        public static string ErrorText(string body){try {var p=JsonUtility.FromJson<Profile>(body);return string.IsNullOrEmpty(p.detail)?"请重试":p.detail;}catch{return "服务连接失败，请重试";}}
        public IEnumerator Refresh()
        {
            using(var r=UnityWebRequest.Get(Gateway+"/api/speaker/profile")) {
                r.timeout=10;yield return r.SendWebRequest();
                if(r.result==UnityWebRequest.Result.Success){var p=JsonUtility.FromJson<Profile>(r.downloadHandler.text);Enabled=p.enabled;Enrolled=p.enrolled;Error="";}
                else Error="声音设置未连接";
            }
        }
        public void Toggle(){if(!Saving&&Enrolled)StartCoroutine(Save());}
        IEnumerator Save()
        {
            Saving=true;
            try {
                using(var r=new UnityWebRequest(Gateway+"/api/speaker/profile","PUT")) {
                    r.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new Setting{enabled=!Enabled})));
                    r.downloadHandler=new DownloadHandlerBuffer();r.SetRequestHeader("Content-Type","application/json");r.timeout=15;
                    yield return r.SendWebRequest();
                    if(r.result!=UnityWebRequest.Result.Success){Error="声音设置保存失败";yield break;}
                }
                yield return Refresh();
            }finally{Saving=false;}
        }
    }
}
