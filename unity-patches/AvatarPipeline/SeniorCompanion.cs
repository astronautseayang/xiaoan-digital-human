using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
namespace LocalHuman
{
    public sealed class SeniorCompanion : MonoBehaviour
    {
        [Serializable] sealed class Profile {public string salutation;}
        public string Salutation {get;private set;}="您";
        public bool Saving {get;private set;}
        public string Error {get;private set;}="";
        bool loaded;
        string Url => GetComponent<LocalHumanDemo>().gateway+"/api/companion/profile";
        public string Address(string text) => Salutation=="您"?text:Salutation+"，"+text;
        IEnumerator Start()
        {
            using(var request=UnityWebRequest.Get(Url)) {
                request.timeout=10;yield return request.SendWebRequest();
                if(request.result==UnityWebRequest.Result.Success) {
                    Profile profile=null;try{profile=JsonUtility.FromJson<Profile>(request.downloadHandler.text);}catch(Exception){}
                    if(profile!=null&&(profile.salutation=="您"||profile.salutation=="爷爷"||profile.salutation=="奶奶"))Salutation=profile.salutation;
                    loaded=true;
                }
            }
            if(!loaded)Error="称呼加载失败，点击重试";
        }
        public void Cycle()
        {
            if(Saving)return;
            if(!loaded){StartCoroutine(Start());return;}
            string next=Salutation=="您"?"爷爷":Salutation=="爷爷"?"奶奶":"您";
            StartCoroutine(Save(next));
        }
        IEnumerator Save(string next)
        {
            Saving=true;Error="";
            using(var request=new UnityWebRequest(Url,"PUT")) {
                request.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new Profile{salutation=next})));
                request.downloadHandler=new DownloadHandlerBuffer();request.SetRequestHeader("Content-Type","application/json");request.timeout=10;
                yield return request.SendWebRequest();
                if(request.result==UnityWebRequest.Result.Success)Salutation=next;
                else Error="称呼保存失败，点击重试";
            }
            Saving=false;
        }
    }
}
