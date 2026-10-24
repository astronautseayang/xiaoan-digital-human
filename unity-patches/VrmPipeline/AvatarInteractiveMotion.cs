using UnityEngine;
using UniVRM10;

namespace LocalHuman
{
    // One speech source drives the currently visible cached avatar. No bone writes,
    // root motion, mouth, blink or jaw curves: Animator + native VRM retain ownership.
    [DisallowMultipleComponent, RequireComponent(typeof(AudioSource))]
    public sealed class AvatarInteractiveMotion : MonoBehaviour
    {
        public const float CrossFadeSeconds=.25f;
        public const float GreetingSeconds=2.8f;
        static readonly string[] TalkActions={"Emphasize","Explain","Listen","Nod"};
        Animator animator;FaceMorphController face;AudioSource source;
        int layer=-1,lastAction=-1;
        bool pending,greetingPending,greeted,wasPlaying;
        string text="";float lastAudio,nextGesture,actionEnds,smileUntil,browUntil,focusUntil,weight;
        int punctuationCursor;
        Transform gazeTarget;
        Vrm10Instance avatar;
        Transform originalGaze;VRM10ObjectLookAt.LookAtTargetTypes originalGazeType;
        public string CurrentAction {get;private set;}="Rest";
        public int GreetingCount {get;private set;}
        public int GestureCount {get;private set;}
        public float LastGestureInterval {get;private set;}
        public float LayerWeight => weight;
        public float SmileWeight => face?face.InteractionSmile:0;
        public float BrowWeight => face?face.InteractionBrow:0;
        public float FocusWeight {get;private set;}
        public float NextGestureAt => nextGesture;
        float lastGesture;
        float nextIdleSmile,eyeSmileUntil,nextSpeechSmile,seriousUntil;
        public float EyeSmileWeight => face?face.InteractionEyeSmile:0;
        public int EyeSmileCount {get;private set;}
        static readonly string[] Cheerful={"你好","您好","欢迎","早上好","晚上好","哈哈","呵呵","开心","高兴","快乐","太好了","真棒","做得好","真好","谢谢","不客气","好主意","喜欢","没问题","陪您","陪你","慢慢来"};
        static readonly string[] Serious={"不开心","不高兴","不快乐","不喜欢","难过","伤心","孤独","孤单","担心","焦虑","害怕","疼","痛","不舒服","生病","摔","跌","救命","急救","去世","离世","住院","危险","难受","别笑","不要笑"};
        static readonly string[] Greetings={"你好","您好","嗨","欢迎","早上好","上午好","中午好","下午好","晚上好","早安","晚安","hello","good morning"};
        public static bool IsGreeting(string value)
        {
            value=(value??"").ToLowerInvariant();
            foreach(var word in Serious)if(value.Contains(word))return false;
            foreach(var word in Greetings)if(value.Contains(word))return true;
            return false;
        }
        public static bool ShouldSmileAt(string sentence)
        {
            foreach(var word in Serious)if(sentence.Contains(word))return false;
            foreach(var word in Cheerful)if(sentence.Contains(word))return true;
            return false;
        }
        static string SentenceAt(string value,float progress)
        {
            if(string.IsNullOrEmpty(value))return "";
            int position=Mathf.Min(value.Length-1,Mathf.FloorToInt(value.Length*progress)),start=position,end=position;
            const string stops="。！？!?；;\n";
            while(start>0&&stops.IndexOf(value[start-1])<0)start--;
            while(end<value.Length&&stops.IndexOf(value[end])<0)end++;
            return value.Substring(start,end-start);
        }
        void Awake(){source=GetComponent<AudioSource>();}
        float wakeUntil;
        public void AcknowledgeWake()
        {
            if(!animator||layer<0)return;
            wakeUntil=Time.unscaledTime+GreetingSeconds;smileUntil=wakeUntil;focusUntil=wakeUntil;
            eyeSmileUntil=Time.unscaledTime+1.8f;
            Trigger("Wave",GreetingSeconds);
        }
        public void BeginUtterance(){greeted=false;}
        public void BindAvatar(Vrm10Instance value)
        {
            ResetAvatar();avatar=value;originalGaze=value.LookAtTarget;originalGazeType=value.LookAtTargetType;animator=value.GetComponent<Animator>();face=value.GetComponent<FaceMorphController>();
            layer=animator.GetLayerIndex("Interaction");weight=0;CurrentAction="Rest";wasPlaying=false;lastAudio=-100;
            if(layer<0)Debug.LogError("INTERACTION missing UpperBody Animator layer");
            if(source&&source.isPlaying){pending=true;greetingPending=false;}
        }
        public void PrepareSpeech(string spokenText)
        {
            text=spokenText??"";punctuationCursor=0;pending=true;
            greetingPending=!greeted&&IsGreeting(SentenceAt(text,0));
        }
        void Trigger(string action,float seconds)
        {
            CurrentAction=action;actionEnds=Time.unscaledTime+seconds;
            animator.CrossFadeInFixedTime("Interaction."+action,CrossFadeSeconds,layer,0);
            Debug.Log("INTERACTION action="+action+" text="+text);
        }
        void Update()
        {
            if(!animator||!animator.gameObject.activeInHierarchy||layer<0)return;
            float now=Time.unscaledTime,dt=Time.unscaledDeltaTime;
            bool playing=source&&source.isPlaying&&!source.mute&&source.volume>.001f&&!AudioListener.pause&&AudioListener.volume>.001f;
            if(playing) {
                if((!wasPlaying&&now-lastAudio>.4f)||nextGesture<=0){nextGesture=now+Random.Range(3f,6f);lastGesture=now;}
                lastAudio=now;
                if(pending) {
                    pending=false;
                    if(greetingPending) {
                        greeted=true;GreetingCount++;smileUntil=now+2.8f;
                        Trigger("Wave",GreetingSeconds);
                        nextGesture=now+Random.Range(3f,6f);lastGesture=now;
                    }
                    greetingPending=false;
                }
                // Approximate punctuation position within this exact spoken clip. No
                // forced aligner available; elapsed audio, rather than text arrival, drives it.
                int position=source.clip?Mathf.CeilToInt(text.Length*Mathf.Clamp01(source.time/Mathf.Max(.01f,source.clip.length))):0;
                while(punctuationCursor<position&&punctuationCursor<text.Length) {
                    char c=text[punctuationCursor++];
                    if(c=='？'||c=='?'||c=='！'||c=='!'){browUntil=now+.7f;focusUntil=now+.9f;}
                    else if(c=='，'||c==','||c=='：'||c==':'){browUntil=now+.4f;focusUntil=now+.5f;}
                    else if(c=='。'||c=='.')focusUntil=now+.5f;
                }
                if(now>=nextGesture&&now>=actionEnds) {
                    int choice=Random.Range(0,lastAction<0?TalkActions.Length:TalkActions.Length-1);if(lastAction>=0&&choice>=lastAction)choice++;
                    lastAction=choice;GestureCount++;LastGestureInterval=now-lastGesture;lastGesture=now;
                    Trigger(TalkActions[choice],2.8f);nextGesture=now+Random.Range(3f,6f);
                }
                if(now>=actionEnds&&CurrentAction!="Rest")Trigger("Rest",0);
            }
            bool holding=playing||now-lastAudio<.15f||now<wakeUntil;
            weight=Mathf.MoveTowards(weight,holding?1:0,dt/(holding?.25f:.4f));animator.SetLayerWeight(layer,weight);
            if(!holding&&CurrentAction!="Rest")Trigger("Rest",0);
            float smileTarget=now<wakeUntil?.38f:playing?(now<smileUntil?.8f:.22f):.08f;
            float browTarget=playing&&now<browUntil?.45f:0;
            if(face){face.InteractionSmile=Mathf.MoveTowards(face.InteractionSmile,smileTarget,dt*3);face.InteractionBrow=Mathf.MoveTowards(face.InteractionBrow,browTarget,dt*3);}
            UpdateEyeSmile(playing,now,dt);
            FocusWeight=Mathf.MoveTowards(FocusWeight,now<wakeUntil?1:playing?(now<focusUntil?1:.65f):0,dt*3);
            UpdateGaze();wasPlaying=playing;
        }
        void UpdateEyeSmile(bool playing,float now,float dt)
        {
            if(!face)return;
            var demo=GetComponent<LocalHumanDemo>();var wake=GetComponent<OfflineWakeClient>();var care=GetComponent<SeniorCareClient>();
            bool blocked=(care&&care.Active)||(demo&&(demo.IsRecording||demo.IsEnrolling))||
                (!playing&&((demo&&demo.IsProcessing)||(wake&&(wake.State=="listening"||wake.State=="thinking"))));
            string sentence="";
            if(playing) {
                string spoken=text;float progress=source.clip?source.time/Mathf.Max(.1f,source.clip.length):0;
                var subtitles=GetComponent<SpeechSubtitleTrack>();
                if(subtitles&&subtitles.CurrentSpeech(out var cueText,out var cueProgress)){spoken=cueText;progress=cueProgress;}
                sentence=SentenceAt(spoken,progress);
                foreach(var word in Serious)if(sentence.Contains(word)){blocked=true;seriousUntil=now+12;break;}
            }
            if(blocked){eyeSmileUntil=0;face.InteractionSmile=Mathf.MoveTowards(face.InteractionSmile,0,dt*6);}
            else if(playing) {
                if(ShouldSmileAt(sentence)&&now>=nextSpeechSmile) {
                    eyeSmileUntil=now+1.9f;nextSpeechSmile=now+5.5f;EyeSmileCount++;
                }
            } else if(now>=nextIdleSmile&&now>=seriousUntil&&now-lastAudio>3) {
                eyeSmileUntil=now+1.8f;nextIdleSmile=now+Random.Range(9f,15f);EyeSmileCount++;
            }
            // Smooth onset/release; after speech only a fresh idle pulse can smile.
            if(!playing&&wasPlaying){eyeSmileUntil=0;nextIdleSmile=now+Random.Range(7f,12f);}
            float target=!blocked&&now<eyeSmileUntil?1f:0;
            face.InteractionEyeSmile=Mathf.MoveTowards(face.InteractionEyeSmile,target,dt*(target>0?2.6f:3.6f));
        }
        void UpdateGaze()
        {
            if(!avatar||!Camera.main)return;
            if(FocusWeight<=0){avatar.LookAtTarget=originalGaze;avatar.LookAtTargetType=originalGazeType;return;}
            if(!gazeTarget){gazeTarget=new GameObject("ConversationGaze").transform;gazeTarget.SetParent(transform,false);}
            var head=animator.GetBoneTransform(HumanBodyBones.Head);if(!head)return;
            // Blend a neutral forward target toward the viewer, without moving the camera.
            gazeTarget.position=Vector3.Lerp(head.position+avatar.transform.forward*2,Camera.main.transform.position,FocusWeight*.65f);
            avatar.LookAtTargetType=VRM10ObjectLookAt.LookAtTargetTypes.SpecifiedTransform;
            avatar.LookAtTarget=gazeTarget;
        }
        public void CancelInteraction()
        {
            wakeUntil=0;lastAudio=-100;pending=greetingPending=wasPlaying=false;CurrentAction="Rest";ResetAvatar();
        }
        void ResetAvatar()
        {
            if(animator&&layer>=0){animator.SetLayerWeight(layer,0);animator.Play("Interaction.Rest",layer,0);}
            if(face){face.InteractionSmile=0;face.InteractionBrow=0;face.InteractionEyeSmile=0;}
            if(avatar&&avatar.LookAtTarget==gazeTarget){avatar.LookAtTarget=originalGaze;avatar.LookAtTargetType=originalGazeType;}
            weight=0;FocusWeight=0;smileUntil=browUntil=focusUntil=0;
            eyeSmileUntil=nextSpeechSmile=0;nextIdleSmile=Time.unscaledTime+Random.Range(7f,12f);
        }
        void OnDisable(){ResetAvatar();pending=greetingPending=wasPlaying=false;}
        void OnDestroy(){if(gazeTarget)Destroy(gazeTarget.gameObject);}
    }
}
