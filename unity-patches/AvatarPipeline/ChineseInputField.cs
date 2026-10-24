using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Networking;
using UnityEngine.UI;
namespace LocalHuman.AvatarPipeline
{
    // Local composition and candidates stay inside the avatar's settings drawer.
    public sealed class ChineseInputField : InputField
    {
        [Serializable] sealed class Candidates {public string[] candidates;}
        [Serializable] sealed class TextPayload {public string text;}
        public string Gateway;
        public string Composition {get;private set;}="";
        public string[] Choices {get;private set;}=new string[0];
        public int Page {get;private set;}
        public string Error {get;private set;}="";
        int revision;Coroutine query,normalization;
        public override void OnSelect(BaseEventData e){base.OnSelect(e);UnityEngine.Input.imeCompositionMode=IMECompositionMode.Off;}
        public override void OnDeselect(BaseEventData e){base.OnDeselect(e);UnityEngine.Input.imeCompositionMode=IMECompositionMode.On;}
        protected override void OnEnable(){base.OnEnable();onValueChanged.AddListener(Normalize);}
        protected override void OnDisable(){onValueChanged.RemoveListener(Normalize);ClearComposition();base.OnDisable();}
        void Normalize(string value)
        {
            if(normalization!=null)StopCoroutine(normalization);
            normalization=StartCoroutine(NormalizeText(value));
        }
        IEnumerator NormalizeText(string original)
        {
            yield return new WaitForSecondsRealtime(.15f);
            if(string.IsNullOrEmpty(original))yield break;
            using(var r=new UnityWebRequest(Gateway+"/api/input/simplified","POST")) {
                r.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new TextPayload{text=original})));
                r.downloadHandler=new DownloadHandlerBuffer();r.SetRequestHeader("Content-Type","application/json");r.timeout=5;
                yield return r.SendWebRequest();
                if(r.result==UnityWebRequest.Result.Success&&text==original) {
                    string converted=JsonUtility.FromJson<TextPayload>(r.downloadHandler.text).text;
                    if(converted!=original){int cursor=caretPosition;text=converted;caretPosition=cursor;}
                }
            }
        }
        void Changed()
        {
            revision++;Page=0;Choices=new string[0];Error="";
            if(query!=null)StopCoroutine(query);
            if(Composition.Length>0)query=StartCoroutine(Fetch(revision,Composition));
        }
        IEnumerator Fetch(int version,string value)
        {
            yield return new WaitForSecondsRealtime(.08f);
            using(var r=UnityWebRequest.Get(Gateway+"/api/input/pinyin?text="+UnityWebRequest.EscapeURL(value))) {
                r.timeout=5;yield return r.SendWebRequest();
                if(version!=revision)yield break;
                if(r.result==UnityWebRequest.Result.Success)Choices=JsonUtility.FromJson<Candidates>(r.downloadHandler.text).candidates??new string[0];
                else Error="中文输入暂未连接，请稍后重试";
            }
        }
        public void ClearComposition(){Composition="";Changed();}
        public void TurnPage(int delta){Page=Mathf.Clamp(Page+delta,0,Mathf.Max(0,(Choices.Length-1)/3));}
        public void Choose(int slot)
        {
            int index=Page*3+slot;if(index<0||index>=Choices.Length)return;
            string value=Choices[index];ClearComposition();InsertValue(value);
        }
        public void InsertValue(string value)
        {
            int start=Mathf.Min(selectionAnchorPosition,selectionFocusPosition),end=Mathf.Max(selectionAnchorPosition,selectionFocusPosition);
            text=text.Remove(start,end-start).Insert(start,value);caretPosition=start+value.Length;
            ActivateInputField();
        }
        public override void OnUpdateSelected(BaseEventData eventData)
        {
            if(!isFocused)return;
            UnityEngine.Input.imeCompositionMode=IMECompositionMode.Off;
            var e=new Event();
            while(Event.PopEvent(e)) {
                if(e.rawType!=EventType.KeyDown)continue;
                bool shortcut=e.control||e.command;
                if(shortcut&&e.keyCode==KeyCode.V){InsertValue(GUIUtility.systemCopyBuffer);continue;}
                if(!shortcut&&((e.character>='a'&&e.character<='z')||(e.character>='A'&&e.character<='Z')||e.character=='\'')) {
                    if(Composition.Length<64){Composition+=char.ToLowerInvariant(e.character);Changed();}continue;
                }
                if(Composition.Length>0) {
                    if(e.keyCode==KeyCode.Backspace){Composition=Composition.Substring(0,Composition.Length-1);Changed();continue;}
                    if(e.keyCode==KeyCode.Escape){ClearComposition();continue;}
                    if(e.keyCode==KeyCode.Space||e.keyCode==KeyCode.Return||e.keyCode==KeyCode.KeypadEnter){Choose(0);continue;}
                    if(e.character>='1'&&e.character<='3'){Choose(e.character-'1');continue;}
                    if(e.keyCode==KeyCode.PageDown||e.keyCode==KeyCode.Equals){TurnPage(1);continue;}
                    if(e.keyCode==KeyCode.PageUp||e.keyCode==KeyCode.Minus){TurnPage(-1);continue;}
                    // Keep composition intact until a candidate is explicitly chosen.
                    continue;
                }
                if(e.keyCode==KeyCode.Return||e.keyCode==KeyCode.KeypadEnter) {
                    GetComponentInParent<LocalHumanDemo>().SubmitQuestion();continue;
                }
                if(!shortcut&&e.character!=0) {
                    string chars=",.?!;:";string chinese="，。？！；：";int at=chars.IndexOf(e.character);
                    if(at>=0){InsertValue(chinese[at].ToString());continue;}
                }
                KeyPressed(e);
            }
            UpdateLabel();eventData.Use();
        }
    }
}
