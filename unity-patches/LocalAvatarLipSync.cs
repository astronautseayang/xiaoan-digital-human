using UnityEngine;
using UniVRM10;
using UniGLTF.Extensions.VRMC_vrm;
namespace LocalHuman
{
    // Submit independent expression inputs; VRM's native merger sums their mesh bindings once.
    [RequireComponent(typeof(AudioSource),typeof(global::uLipSync.uLipSync))]
    public sealed class LocalAvatarLipSync : MonoBehaviour
    {
        public global::uLipSync.Profile profile;
        public Vrm10Instance avatar;
        global::uLipSync.uLipSync analyzer;
        AudioSource source;
        readonly string[] phonemes={"A","I","U","E","O"};
        readonly ExpressionPreset[] presets={ExpressionPreset.aa,ExpressionPreset.ih,ExpressionPreset.ou,ExpressionPreset.ee,ExpressionPreset.oh};
        readonly float[] weights=new float[5];
        global::uLipSync.LipSyncInfo info;
        float lastAnalysis=-100, nextBlink, blinkStart=-100;
        public int BlinkCount {get;private set;}
        public float LastBlinkStarted {get;private set;}
        public float LastBlinkInterval {get;private set;}
        public float BlinkWeight {get;private set;}
        public void BindAvatar(Vrm10Instance instance)
        {
            if(avatar && avatar!=instance) {
                foreach(var preset in presets)avatar.Runtime.Expression.SetWeight(new ExpressionKey(preset),0);
                avatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.blink),0);
            }
            avatar=instance;
            // Imported clips belong to this runtime instance. Emotions must not block
            // procedural speech/blink when a Stage 3 profile is held at a nonzero weight.
            foreach(var clip in avatar.Vrm.Expression.Clips){
                var key=avatar.Vrm.Expression.CreateKey(clip.Clip);
                if(!key.IsMouth&&!key.IsBlink&&!key.IsLookAt){
                    clip.Clip.OverrideMouth=ExpressionOverrideType.none;
                    clip.Clip.OverrideBlink=ExpressionOverrideType.none;
                }
            }
        }
        void OnEnable(){
            source=GetComponent<AudioSource>();analyzer=GetComponent<global::uLipSync.uLipSync>();
            analyzer.profile=profile;analyzer.onLipSyncUpdate.AddListener(OnLip);
            nextBlink=Time.unscaledTime+Random.Range(2.5f,5f);blinkStart=-100;lastAnalysis=-100;
        }
        void OnLip(global::uLipSync.LipSyncInfo value){info=value;lastAnalysis=Time.unscaledTime;}
        void Update()
        {
            if(!avatar)return;
            bool fresh=source.isPlaying&&Time.unscaledTime-lastAnalysis<.15f;
            for(int n=0;n<5;n++){
                float ratio=0;if(fresh&&info.phonemeRatios!=null)info.phonemeRatios.TryGetValue(phonemes[n],out ratio);
                float target=fresh?Mathf.Clamp01(ratio*info.volume):0;
                weights[n]=Mathf.Lerp(weights[n],target,1-Mathf.Exp(-Time.unscaledDeltaTime*18));
                var face=avatar.GetComponent<FaceMorphController>();
                float photo=n==0&&face?face.PhotoMouthOpen:0;
                // Keep the smile opening at idle; speech owns the mouth while audio is active.
                float speech=0;foreach(float w in weights)speech=Mathf.Max(speech,w);
                avatar.Runtime.Expression.SetWeight(new ExpressionKey(presets[n]),Mathf.Clamp01(weights[n]+photo*(1-speech)));
            }
            float now=Time.unscaledTime;
            if(now>=nextBlink){
                LastBlinkInterval=BlinkCount>0?now-LastBlinkStarted:0;
                LastBlinkStarted=blinkStart=now;BlinkCount++;
                nextBlink=now+Random.Range(2.5f,5f);
            }
            // Fast close (55ms), short full closure (25ms), slower reopen (140ms).
            float elapsed=now-blinkStart;
            BlinkWeight=elapsed<0||elapsed>=.22f?0:elapsed<.055f?
                Mathf.SmoothStep(0,1,elapsed/.055f):elapsed<.08f?1:
                1-Mathf.SmoothStep(0,1,(elapsed-.08f)/.14f);
            avatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.blink),BlinkWeight);
        }
        void OnDisable(){
            if(analyzer)analyzer.onLipSyncUpdate.RemoveListener(OnLip);
            for(int n=0;n<5;n++){weights[n]=0;if(avatar)avatar.Runtime.Expression.SetWeight(new ExpressionKey(presets[n]),0);}
            BlinkWeight=0;if(avatar)avatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.blink),0);
        }
    }
}
