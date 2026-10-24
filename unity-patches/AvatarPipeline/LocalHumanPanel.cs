using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
namespace LocalHuman.AvatarPipeline
{
    // UGUI only; no bitmap icon/font dependency for transport controls.
    public sealed class LocalHumanPanel : MonoBehaviour
    {
        ScrollRect answerScroll;
        public ScrollRect AnswerScroll => answerScroll;
        LocalHumanDemo demo;Canvas canvas;Text response,status;InputField field;
        Button fullView,portraitView,salutation,speakerEnroll,speakerOnly;
        Button send,record,replay,native,paste,refresh,enroll,resetVoice,volumeToggle,listenToggle;
        bool open;
        RectTransform candidates;Text composition;Button[] choices=new Button[3];
        public void FocusInput(){open=true;StartCoroutine(FocusWhenVisible());}
        System.Collections.IEnumerator FocusWhenVisible(){yield return null;Canvas.ForceUpdateCanvases();field.Select();field.ActivateInputField();}
        public void ToggleDrawer(){if(open)CloseDrawer();else open=true;}
        public void CloseDrawer(){open=false;if(field){field.DeactivateInputField();((ChineseInputField)field).ClearComposition();}UnityEngine.Input.imeCompositionMode=IMECompositionMode.On;}Text identity,credit,voiceState;VrmAvatarLoader loader;StudioIcon recordIcon;
        static readonly Color Ink=new Color32(29,53,52,255);
        static readonly Color Surface=new Color32(225,236,232,255);
        public bool IsVisible => canvas && canvas.enabled;
        public InputField Input => field;
        public Button Send => send;
        public Button Paste => paste;
        public Button Record => record;
        public Button Replay => replay;
        public Button Refresh => refresh;
        public Button Enroll => enroll;
        public Button ResetVoice => resetVoice;
        public Button VolumeToggle => volumeToggle;
        void Start()
        {
            demo=GetComponent<LocalHumanDemo>();loader=GetComponent<VrmAvatarLoader>();
            var go=new GameObject("InteractionCanvas",typeof(RectTransform),typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));
            go.transform.SetParent(transform,false);canvas=go.GetComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceOverlay;canvas.sortingOrder=80;
            var scaler=go.GetComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;scaler.referenceResolution=new Vector2(1600,900);scaler.screenMatchMode=CanvasScaler.ScreenMatchMode.Expand;
            if(!FindObjectOfType<EventSystem>())new GameObject("UIEventSystem",typeof(EventSystem),typeof(StandaloneInputModule));
            var backdrop=Box("SettingsBackdrop",go.transform,Vector2.zero,new Vector2(1600,900),new Color(.03f,.09f,.09f,.3f),0);
            backdrop.anchorMin=Vector2.zero;backdrop.anchorMax=Vector2.one;backdrop.offsetMin=backdrop.offsetMax=Vector2.zero;
            backdrop.gameObject.AddComponent<Button>().onClick.AddListener(CloseDrawer);
            var card=Box("GlassCard",go.transform,new Vector2(24,-24),new Vector2(440,868),new Color32(242,247,246,255),24);
            card.anchorMin=card.anchorMax=card.pivot=new Vector2(1,1);card.anchoredPosition=new Vector2(-24,-16);
            Box("Accent",card,new Vector2(24,-26),new Vector2(5,58),new Color32(28,103,95,255),2);
            Label("Title",card,"设置与更多",new Vector2(44,-22),new Vector2(290,48),32,FontStyle.Bold);
            Label("Subtitle",card,"音量、形象与文字输入",new Vector2(24,-78),new Vector2(392,32),20);
            Action(card,"关闭",338,26,78,CloseDrawer);
            refresh=Action(card,"刷新形象",24,126,392,()=>loader.ReloadProfile());
            identity=Label("AvatarState",card,"加载角色…",new Vector2(24,-182),new Vector2(392,30),18);
            var viewport=Box("AnswerViewport",card,new Vector2(24,-222),new Vector2(392,72),Color.white,12);
            viewport.gameObject.AddComponent<RectMask2D>();var scroll=viewport.gameObject.AddComponent<ScrollRect>();answerScroll=scroll;scroll.horizontal=false;scroll.movementType=ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=30;
            response=Label("Answer",viewport,demo.Answer,new Vector2(14,-10),new Vector2(364,52),20);
            response.alignment=TextAnchor.UpperLeft;response.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            scroll.viewport=viewport;scroll.content=response.rectTransform;
            var input=Box("QuestionInput",card,new Vector2(24,-308),new Vector2(392,64),Color.white,14);
            var chinese=input.gameObject.AddComponent<ChineseInputField>();chinese.Gateway=demo.gateway;
            field=chinese;field.targetGraphic=input.GetComponent<RoundedCard>();field.characterLimit=1000;
            var text=Label("InputText",input,"",new Vector2(14,-12),new Vector2(364,42),24);text.supportRichText=false;text.alignment=TextAnchor.MiddleLeft;
            field.textComponent=text;field.text=demo.Question;field.onValueChanged.AddListener(v=>demo.Question=v);
            var placeholder=Label("Placeholder",input,"直接输入拼音或中文",new Vector2(14,-12),new Vector2(364,42),22);placeholder.color=new Color32(112,130,126,255);field.placeholder=placeholder;
            candidates=Box("ChineseCandidates",card,new Vector2(24,-202),new Vector2(392,100),Color.white,12);
            composition=Label("Pinyin",candidates,"",new Vector2(10,-4),new Vector2(372,32),20);
            for(int i=0;i<3;i++){int slot=i;choices[i]=Action(candidates,"",8+i*104,42,100,()=>chinese.Choose(slot));}
            Action(candidates,"‹",322,42,30,()=>chinese.TurnPage(-1));Action(candidates,"›",356,42,30,()=>chinese.TurnPage(1));
            native=Action(card,"文字输入",24,386,116,FocusInput);
            paste=Action(card,"粘贴",150,386,68,()=>chinese.InsertValue(GUIUtility.systemCopyBuffer));
            replay=IconButton(card,"Replay",228,386,StudioIcon.Kind.Replay,()=>demo.ReplayLast());
            record=IconButton(card,"Microphone",294,386,StudioIcon.Kind.Microphone,()=>GetComponent<OfflineWakeClient>().ListenNow());recordIcon=record.GetComponentInChildren<StudioIcon>();
            send=IconButton(card,"Send",360,386,StudioIcon.Kind.Send,()=>demo.SubmitQuestion());
            send.GetComponent<RoundedCard>().color=new Color32(198,228,218,255);
            status=Label("Status",card,"就绪",new Vector2(24,-446),new Vector2(392,30),20);status.color=new Color32(28,103,95,255);
            enroll=Action(card,"录入我的音色",24,490,190,()=>demo.ToggleVoiceEnrollment());
            resetVoice=Action(card,"恢复默认音色",226,490,190,()=>demo.ResetVoice());
            voiceState=Label("VoiceState",card,"",new Vector2(24,-548),new Vector2(392,30),18);
            fullView=Action(card,"全身",24,578,190,()=>GetComponent<AvatarViewMode>().SetFullBody(true));
            portraitView=Action(card,"当前近景",226,578,190,()=>GetComponent<AvatarViewMode>().SetFullBody(false));
            volumeToggle=Action(card,"大音量：关闭",24,638,190,()=>GetComponent<SeniorCareClient>().ToggleLoudGain());
            listenToggle=Action(card,"唤醒监听：开启",226,638,190,()=>GetComponent<SeniorCareClient>().ToggleListening());
            salutation=Action(card,"对您的称呼：您（点击切换）",24,704,392,()=>GetComponent<SeniorCompanion>().Cycle());
            speakerEnroll=Action(card,"录入识别声音",24,764,190,()=>demo.ToggleSpeakerEnrollment());
            speakerOnly=Action(card,"只听我：未录入",226,764,190,()=>GetComponent<SpeakerInputClient>().Toggle());
            credit=Label("Attribution",card,"",new Vector2(24,-830),new Vector2(392,30),12);

        }
        RectTransform Box(string name,Transform parent,Vector2 pos,Vector2 size,Color color,float radius)
        {
            var go=new GameObject(name,typeof(RectTransform),typeof(RoundedCard));var rt=go.GetComponent<RectTransform>();rt.SetParent(parent,false);rt.anchorMin=rt.anchorMax=rt.pivot=new Vector2(0,1);rt.anchoredPosition=pos;rt.sizeDelta=size;
            var g=go.GetComponent<RoundedCard>();g.color=color;g.radius=radius;return rt;
        }
        Text Label(string name,Transform parent,string value,Vector2 pos,Vector2 size,int fontSize,FontStyle style=FontStyle.Normal)
        {
            var go=new GameObject(name,typeof(RectTransform),typeof(Text));var rt=go.GetComponent<RectTransform>();rt.SetParent(parent,false);rt.anchorMin=rt.anchorMax=rt.pivot=new Vector2(0,1);rt.anchoredPosition=pos;rt.sizeDelta=size;
            var t=go.GetComponent<Text>();t.font=demo.chineseFont;t.fontSize=fontSize;t.fontStyle=style;t.color=Ink;t.text=value;t.raycastTarget=false;t.horizontalOverflow=HorizontalWrapMode.Wrap;t.verticalOverflow=VerticalWrapMode.Truncate;return t;
        }
        Button Action(Transform parent,string text,float x,float y,float width,UnityEngine.Events.UnityAction click)
        {
            var rt=Box(text,parent,new Vector2(x,-y),new Vector2(width,50),Surface,12);
            var b=rt.gameObject.AddComponent<Button>();b.targetGraphic=rt.GetComponent<RoundedCard>();var c=b.colors;c.normalColor=Color.white;c.highlightedColor=new Color(237f/247,242f/250,247f/252);c.pressedColor=new Color(226f/247,232f/250,240f/252);c.selectedColor=c.highlightedColor;c.fadeDuration=.12f;b.colors=c;b.onClick.AddListener(click);
            if(!string.IsNullOrEmpty(text)){var t=Label("Label",rt,text,Vector2.zero,new Vector2(width,50),20);t.alignment=TextAnchor.MiddleCenter;}
            return b;
        }
        Button IconButton(Transform parent,string name,float x,float y,StudioIcon.Kind kind,UnityEngine.Events.UnityAction click)
        {
            var b=Action(parent,"",x,y,56,click);b.name=name;
            var go=new GameObject(name+"Icon",typeof(RectTransform),typeof(StudioIcon));var rt=go.GetComponent<RectTransform>();rt.SetParent(b.transform,false);rt.anchorMin=rt.anchorMax=rt.pivot=new Vector2(.5f,.5f);rt.sizeDelta=new Vector2(27,27);var icon=go.GetComponent<StudioIcon>();icon.kind=kind;icon.color=Ink;icon.raycastTarget=false;
            return b;
        }
        void Update()
        {
            if(!canvas)return;canvas.enabled=demo.enabled&&open&&!GetComponent<SeniorCareClient>().Active;
            // Render beneath the startup loading overlay so fonts and glass warm before readiness.
            canvas.GetComponent<GraphicRaycaster>().enabled=LocalHumanStartup.Ready;
            var senior=GetComponent<SeniorCareClient>();
            volumeToggle.GetComponentInChildren<Text>().text="大音量："+(GetComponent<SeniorAudioLimiter>().LoudGain?"开启":"关闭");
            listenToggle.GetComponentInChildren<Text>().text="唤醒监听："+(senior.Listening?"开启":"关闭");
            var companion=GetComponent<SeniorCompanion>();
            salutation.interactable=!companion.Saving;
            salutation.GetComponentInChildren<Text>().text=companion.Saving?"正在保存称呼…":!string.IsNullOrEmpty(companion.Error)?companion.Error:"对您的称呼："+companion.Salutation+"（点击切换）";
            bool full=GetComponent<AvatarViewMode>().FullBody;
            fullView.GetComponent<RoundedCard>().color=full?new Color32(198,228,218,255):Surface;
            portraitView.GetComponent<RoundedCard>().color=!full?new Color32(198,228,218,255):Surface;
            refresh.interactable=loader&&loader.Ready&&!loader.IsSwitching;
            identity.text=loader.IsSwitching?"正在加载角色…":!string.IsNullOrEmpty(loader.Error)?"切换失败："+loader.Error:"当前陪伴：小安";
            credit.text=loader.Attribution;
            string answerText=demo.Answer=="本地数字人：输入文字或按录音按钮开始。"?"点击麦克风说话，或在下方输入问题。":demo.Answer;
            if(response.text!=answerText){response.text=answerText;LayoutRebuilder.ForceRebuildLayoutImmediate(response.rectTransform);answerScroll.verticalNormalizedPosition=0;}
            if(field.text!=demo.Question)field.SetTextWithoutNotify(demo.Question);
            var chinese=(ChineseInputField)field;
            candidates.gameObject.SetActive(!string.IsNullOrEmpty(chinese.Composition));
            composition.text=string.IsNullOrEmpty(chinese.Error)?chinese.Composition+"  · 空格选字":chinese.Error;
            for(int i=0;i<3;i++){
                int index=chinese.Page*3+i;var button=choices[i];
                button.interactable=index<chinese.Choices.Length;
                var label=button.GetComponentInChildren<Text>();
                if(!label)label=Label("Label",button.transform,"",Vector2.zero,new Vector2(100,50),18);
                label.alignment=TextAnchor.MiddleCenter;label.resizeTextForBestFit=true;label.resizeTextMinSize=12;label.resizeTextMaxSize=20;
                label.text=index<chinese.Choices.Length?(i+1)+" "+chinese.Choices[index]:"";
            }
            field.interactable=send.interactable=native.interactable=paste.interactable=!demo.IsBusy&&!demo.IsRecording;
            enroll.interactable=!demo.IsBusy&&(!demo.IsRecording||(demo.IsEnrolling&&!demo.IsSpeakerEnrolling));
            enroll.GetComponentInChildren<Text>().text=(demo.IsEnrolling&&!demo.IsSpeakerEnrolling)?"停止并分析音色":"录入我的音色";
            resetVoice.interactable=!demo.IsBusy&&!demo.IsRecording;
            var speaker=GetComponent<SpeakerInputClient>();
            speakerEnroll.interactable=!demo.IsBusy&&!speaker.Saving&&(!demo.IsRecording||demo.IsSpeakerEnrolling);
            speakerEnroll.GetComponentInChildren<Text>().text=demo.IsSpeakerEnrolling?"停止并保存声音":"录入识别声音";
            speakerOnly.interactable=!demo.IsBusy&&!demo.IsRecording&&!speaker.Saving&&speaker.Enrolled;
            speakerOnly.GetComponentInChildren<Text>().text=speaker.Saving?"正在保存…":!string.IsNullOrEmpty(speaker.Error)?speaker.Error:!speaker.Enrolled?"只听我：先录入":"只听我："+(speaker.Enabled?"开启":"关闭");
            voiceState.text="音色："+demo.VoiceName;
            record.interactable=!demo.IsBusy&&!demo.IsEnrolling;replay.interactable=!demo.IsBusy&&!demo.IsRecording&&demo.HasReplay;
            recordIcon.color=demo.IsRecording?new Color(.85f,.22f,.28f):Ink;
            recordIcon.SetRecording(demo.IsRecording);status.text=demo.Status;
        }
    }
    public sealed class RoundedCard : MaskableGraphic
    {
        public float radius=16;public bool outline;
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();var r=rectTransform.rect;float rad=Mathf.Min(radius,Mathf.Min(r.width,r.height)*.5f);const int steps=10;
            if(!outline)vh.AddVert(r.center,color,Vector2.zero);
            for(int corner=0;corner<4;corner++)for(int i=0;i<=steps;i++)
            {
                float a=(corner*90+i*90f/steps)*Mathf.Deg2Rad;
                var center=new Vector2(corner==0||corner==3?r.xMax-rad:r.xMin+rad,corner<2?r.yMax-rad:r.yMin+rad);
                var dir=new Vector2(Mathf.Cos(a),Mathf.Sin(a));vh.AddVert(center+dir*rad,color,Vector2.zero);
                if(outline)vh.AddVert(center+dir*Mathf.Max(0,rad-1),color,Vector2.zero);
            }
            int n=4*(steps+1);
            for(int i=0;i<n;i++){int j=(i+1)%n;if(outline){vh.AddTriangle(i*2,j*2,i*2+1);vh.AddTriangle(j*2,j*2+1,i*2+1);}else vh.AddTriangle(0,1+i,1+j);}
        }
    }
    public sealed class StudioIcon : MaskableGraphic
    {
        public enum Kind {Microphone,Send,Replay}public Kind kind;bool recording;
        public void SetRecording(bool value){if(recording==value)return;recording=value;SetVerticesDirty();}
        void Line(VertexHelper vh,Vector2 a,Vector2 b)
        {a=(a-new Vector2(.5f,.5f))*rectTransform.rect.size;b=(b-new Vector2(.5f,.5f))*rectTransform.rect.size;var n=new Vector2(-(b-a).y,(b-a).x).normalized*.85f;int i=vh.currentVertCount;vh.AddVert(a+n,color,Vector2.zero);vh.AddVert(b+n,color,Vector2.zero);vh.AddVert(b-n,color,Vector2.zero);vh.AddVert(a-n,color,Vector2.zero);vh.AddTriangle(i,i+1,i+2);vh.AddTriangle(i,i+2,i+3);}
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if(kind==Kind.Send){Line(vh,new Vector2(.12f,.82f),new Vector2(.9f,.5f));Line(vh,new Vector2(.9f,.5f),new Vector2(.12f,.18f));Line(vh,new Vector2(.12f,.18f),new Vector2(.28f,.5f));Line(vh,new Vector2(.28f,.5f),new Vector2(.12f,.82f));Line(vh,new Vector2(.28f,.5f),new Vector2(.9f,.5f));}
            else if(kind==Kind.Replay){for(int i=0;i<25;i++){float a=Mathf.Lerp(40,340,i/25f)*Mathf.Deg2Rad,b=Mathf.Lerp(40,340,(i+1)/25f)*Mathf.Deg2Rad;Line(vh,new Vector2(.5f,.5f)+new Vector2(Mathf.Cos(a),Mathf.Sin(a))*.33f,new Vector2(.5f,.5f)+new Vector2(Mathf.Cos(b),Mathf.Sin(b))*.33f);}Line(vh,new Vector2(.77f,.72f),new Vector2(.56f,.74f));Line(vh,new Vector2(.77f,.72f),new Vector2(.78f,.93f));}
            else if(recording){Line(vh,new Vector2(.25f,.25f),new Vector2(.75f,.25f));Line(vh,new Vector2(.75f,.25f),new Vector2(.75f,.75f));Line(vh,new Vector2(.75f,.75f),new Vector2(.25f,.75f));Line(vh,new Vector2(.25f,.75f),new Vector2(.25f,.25f));}
            else{for(int i=0;i<32;i++){float a=i*Mathf.PI*2/32,b=(i+1)*Mathf.PI*2/32;Line(vh,new Vector2(.5f,.65f)+new Vector2(Mathf.Cos(a)*.15f,Mathf.Sin(a)*.28f),new Vector2(.5f,.65f)+new Vector2(Mathf.Cos(b)*.15f,Mathf.Sin(b)*.28f));}for(int i=0;i<16;i++){float a=Mathf.PI+i*Mathf.PI/16,b=Mathf.PI+(i+1)*Mathf.PI/16;Line(vh,new Vector2(.5f,.55f)+new Vector2(Mathf.Cos(a),Mathf.Sin(a))*.3f,new Vector2(.5f,.55f)+new Vector2(Mathf.Cos(b),Mathf.Sin(b))*.3f);}Line(vh,new Vector2(.5f,.25f),new Vector2(.5f,.08f));Line(vh,new Vector2(.32f,.08f),new Vector2(.68f,.08f));}
        }
    }
}
