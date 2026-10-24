using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
using UniVRM10;
namespace LocalHuman
{
    // Controlled audio tests isolate state transitions from variable LLM responses.
    // The existing integration suite separately covers actual TTS/UI/ASR playback.
    public sealed class InteractiveMotionValidation:MonoBehaviour
    {
        const string Dir="/home/yyy/digital-human/artifacts/validation/interactive-motion";
        [Serializable] sealed class AvatarReport {
            public string avatar;public int greetings,gestures,blinks;
            public float maxFootDrift,maxArmAngle,maxHeadAngle,maxSmile,maxBrow,maxBrowMesh,maxLip,maxFocus,maxTransitionStep;
            public bool returnedToIdle,silentDoesNotGreet,switchClean,layerConfigured;
            public bool idleEyeSmile,speechEyeSmile,seriousReleased,interruptReleased,replayMatched;
            public float maxEyeSmileMesh;
            public bool wakeWave,greetingWave;
            public List<string> actions=new List<string>();public List<float> intervals=new List<float>();
        }
        [Serializable] sealed class Report {public bool passed;public string error;public string scope="Cached real TTS replay with controlled semantic text; live TTS/UI covered separately by vrm-stage4";public List<AvatarReport> avatars=new List<AvatarReport>();}
        Report report=new Report();Exception failure;
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-interactive-motion-self-test")>=0)new GameObject("InteractiveMotionValidation").AddComponent<InteractiveMotionValidation>();}
        IEnumerator Start(){
            Directory.CreateDirectory(Dir);var run=Run();
            while(true){object value=null;bool more=false;try{more=run.MoveNext();if(more)value=run.Current;}catch(Exception e){failure=e;}if(!more||failure!=null)break;yield return value;}
            report.passed=failure==null;report.error=failure?.ToString();File.WriteAllText(Dir+"/runtime.json",JsonUtility.ToJson(report,true));Debug.Log("INTERACTIVE_VALIDATION "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);
        }
        static void Require(bool value,string message){if(!value)throw new Exception(message);}
        IEnumerator Run(){
            var loader=FindObjectOfType<VrmAvatarLoader>();float deadline=Time.realtimeSinceStartup+90;
            while(!LocalHumanStartup.Ready&&Time.realtimeSinceStartup<deadline)yield return null;
            Require(LocalHumanStartup.Ready&&loader.CacheReady,"Startup failed");
            Require(AvatarInteractiveMotion.ShouldSmileAt("爷爷，太好了，真棒！"),"Positive semantics missing");
            Require(!AvatarInteractiveMotion.ShouldSmileAt("奶奶不开心，我陪您去看医生。"),"Negative semantics smiled");
            Require(!AvatarInteractiveMotion.ShouldSmileAt("你好，我胸口疼，快急救！"),"Emergency semantics smiled");
            foreach(string value in new[]{"爷爷，早上好！","奶奶，下午好！","您好！","晚上好！"})Require(AvatarInteractiveMotion.IsGreeting(value),"Greeting not matched: "+value);
            Require(!AvatarInteractiveMotion.IsGreeting("您好，胸口疼要及时急救。"),"Emergency greeting waved");
            var motion=loader.GetComponent<AvatarInteractiveMotion>();var source=loader.GetComponent<AudioSource>();var lip=loader.GetComponent<LocalAvatarLipSync>();
            AudioClip signal;
            using(var request=UnityWebRequestMultimedia.GetAudioClip("file:///home/yyy/digital-human/artifacts/validation/voice-latency/gpu-same-text-1.wav",AudioType.WAV)) {
                yield return request.SendWebRequest();Require(request.result==UnityWebRequest.Result.Success,"Cached real TTS fixture missing");signal=DownloadHandlerAudioClip.GetContent(request);
            }
            foreach(string id in new[]{"man"}) {
                var task=loader.SwitchAvatarAsync(id);while(!task.IsCompleted)yield return null;Require(task.Result,"Switch failed");
                yield return new WaitForSecondsRealtime(.6f);
                var avatar=loader.Instance;var animator=avatar.GetComponent<Animator>();
                var result=new AvatarReport{avatar=id};report.avatars.Add(result);
                result.layerConfigured=animator.GetLayerIndex("Interaction")==1&&animator.layerCount==2;
                Require(result.layerConfigured,"Interaction layer missing");
                motion.AcknowledgeWake();yield return new WaitForSecondsRealtime(.7f);
                result.wakeWave=motion.CurrentAction=="Wave"&&motion.LayerWeight>.9f;
                Require(result.wakeWave,"Wake greeting wave missing");
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-wake-wave.png");
                yield return new WaitForSecondsRealtime(2.8f);
                Require(motion.CurrentAction=="Rest"&&motion.LayerWeight==0,"Wake wave did not return to rest");
                float idleDeadline=Time.unscaledTime+16;
                while(Time.unscaledTime<idleDeadline&&motion.EyeSmileWeight<.98f)yield return null;
                result.idleEyeSmile=motion.EyeSmileWeight>=.98f;Require(result.idleEyeSmile,"Idle eye smile missing");
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-idle-eye-smile.png");
                motion.CancelInteraction();
                var view=loader.GetComponent<AvatarViewMode>();bool originalView=view.FullBody;
                view.SetFullBody(true);yield return new WaitForSecondsRealtime(.25f);
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-ground-shadow.png");
                view.SetFullBody(originalView);
                var left=animator.GetBoneTransform(HumanBodyBones.LeftFoot);var right=animator.GetBoneTransform(HumanBodyBones.RightFoot);
                Vector3 lp=left.position,rp=right.position;Quaternion arm=animator.GetBoneTransform(HumanBodyBones.RightUpperArm).localRotation,head=animator.GetBoneTransform(HumanBodyBones.Head).localRotation;
                int greeting=motion.GreetingCount,gesture=motion.GestureCount,blink=lip.BlinkCount;
                motion.BeginUtterance();motion.PrepareSpeech("你好！欢迎，我们一起聊聊，好吗？这是一段自然的交谈！");
                yield return new WaitForSecondsRealtime(.5f);
                result.silentDoesNotGreet=motion.GreetingCount==greeting&&motion.LayerWeight==0;Require(result.silentDoesNotGreet,"Gesture fired before audio");
                UnityEngine.Random.InitState(id=="man"?135:251);source.clip=signal;source.loop=true;source.Play();
                float start=Time.unscaledTime,previousWeight=0;int previousGestures=motion.GestureCount;string previousAction="";bool captured=false;float actionStarted=Time.unscaledTime;var capturedActions=new HashSet<string>();
                while(source.isPlaying&&Time.unscaledTime-start<22) {
                    yield return new WaitForEndOfFrame();
                    result.maxFootDrift=Mathf.Max(result.maxFootDrift,Vector3.Distance(lp,left.position),Vector3.Distance(rp,right.position));
                    result.maxArmAngle=Mathf.Max(result.maxArmAngle,Quaternion.Angle(arm,animator.GetBoneTransform(HumanBodyBones.RightUpperArm).localRotation));
                    result.maxHeadAngle=Mathf.Max(result.maxHeadAngle,Quaternion.Angle(head,animator.GetBoneTransform(HumanBodyBones.Head).localRotation));
                    result.maxSmile=Mathf.Max(result.maxSmile,avatar.Runtime.Expression.GetWeight(new ExpressionKey(ExpressionPreset.happy)));
                    result.maxBrow=Mathf.Max(result.maxBrow,motion.BrowWeight);result.maxFocus=Mathf.Max(result.maxFocus,motion.FocusWeight);
                    result.maxLip=Mathf.Max(result.maxLip,avatar.Runtime.Expression.GetWeight(new ExpressionKey(ExpressionPreset.aa)));
                    result.speechEyeSmile|=motion.EyeSmileWeight>.7f;
                    result.greetingWave|=motion.CurrentAction=="Wave";
                    result.maxTransitionStep=Mathf.Max(result.maxTransitionStep,Mathf.Abs(previousWeight-motion.LayerWeight));previousWeight=motion.LayerWeight;
                    foreach(var r in avatar.GetComponentsInChildren<SkinnedMeshRenderer>())if(r.sharedMesh)for(int n=0;n<r.sharedMesh.blendShapeCount;n++){
                        string name=r.sharedMesh.GetBlendShapeName(n).ToLowerInvariant();if(name.EndsWith("eyeblow_up")||name.Contains("brw_surprised"))result.maxBrowMesh=Mathf.Max(result.maxBrowMesh,r.GetBlendShapeWeight(n));
                        if(name=="fcl_eye_joy"||name.EndsWith("eye_smile"))result.maxEyeSmileMesh=Mathf.Max(result.maxEyeSmileMesh,r.GetBlendShapeWeight(n));
                    }
                    if(motion.CurrentAction!=previousAction){previousAction=motion.CurrentAction;result.actions.Add(previousAction);actionStarted=Time.unscaledTime;}
                    if(motion.GestureCount!=previousGestures){previousGestures=motion.GestureCount;result.intervals.Add(motion.LastGestureInterval);}
                    if(motion.CurrentAction!="Rest"&&Time.unscaledTime-actionStarted>1.1f&&capturedActions.Add(motion.CurrentAction))ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-"+motion.CurrentAction+".png");
                    if(!captured&&Time.unscaledTime-start>1.1f){ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-greeting.png");captured=true;}
                }
                source.Stop();yield return new WaitForSecondsRealtime(.7f);
                result.greetings=motion.GreetingCount-greeting;result.gestures=motion.GestureCount-gesture;result.blinks=lip.BlinkCount-blink;
                result.returnedToIdle=motion.LayerWeight==0&&motion.SmileWeight<=.081f&&motion.EyeSmileWeight==0&&motion.BrowWeight==0&&motion.FocusWeight==0&&motion.CurrentAction=="Rest";
                Require(result.greetings==1&&result.gestures>=3,"Greeting/talk gestures missing");
                Require(result.greetingWave,"Spoken greeting did not wave");
                foreach(float interval in result.intervals)Require(interval>=3&&interval<=6.1f,"Gesture outside 3-6 second interval");
                Require(result.maxFootDrift<.001f,"Gesture moved the feet");Require(result.maxArmAngle>10&&result.maxHeadAngle>1,"Upper body did not animate");
                Require(result.maxSmile>.1f&&result.maxBrow>.2f&&result.maxBrowMesh>1&&result.maxFocus>.9f,"Facial response missing");
                Require(result.maxLip>.01f&&result.blinks>=2,"Speech/blink blocked");Require(result.returnedToIdle,"Motion/expression did not release");
                Require(result.speechEyeSmile&&result.maxEyeSmileMesh>98,"Spoken eye smile not applied to mesh");
                // Replay cues must suppress smiles in the serious segment, even with
                // a positive sentence elsewhere in the complete generated response.
                var subtitles=loader.GetComponent<SpeechSubtitleTrack>();
                source.loop=false;source.clip=signal;
                subtitles.Bind(source,new[]{new SpeechSubtitleTrack.Cue(0,signal.length*.5f,"爷爷，太好了，真棒！"),new SpeechSubtitleTrack.Cue(signal.length*.5f,signal.length,"奶奶，胸口疼需要及时急救。")});
                motion.CancelInteraction();motion.PrepareSpeech("爷爷，太好了，真棒！奶奶，胸口疼需要及时急救。");source.Play();
                yield return new WaitForSecondsRealtime(.55f);
                bool firstSmiled=motion.EyeSmileWeight>.7f;
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Dir+"/"+id+"-speech-eye-smile.png");
                source.time=signal.length*.55f;yield return new WaitForSecondsRealtime(.5f);
                result.seriousReleased=motion.EyeSmileWeight==0;result.replayMatched=firstSmiled&&result.seriousReleased;
                Require(result.replayMatched,"Replay sentiment did not follow current audio cue");
                motion.CancelInteraction();result.interruptReleased=motion.EyeSmileWeight==0;Require(result.interruptReleased,"Interrupted eye smile remained");
                source.Stop();subtitles.Clear();
                // Interrupt a greeting with a live avatar switch; the hidden instance must release all channels.
                motion.BeginUtterance();motion.PrepareSpeech("你好，欢迎！");source.clip=signal;source.loop=true;source.Play();yield return new WaitForSecondsRealtime(.8f);
                var old=animator;var oldFace=avatar.GetComponent<FaceMorphController>();var switching=loader.SwitchAvatarAsync("man");while(!switching.IsCompleted)yield return null;
                Require(switching.Result,"Speaking switch failed");result.switchClean=old.GetLayerWeight(1)==0&&oldFace.InteractionSmile==0&&oldFace.InteractionBrow==0&&oldFace.InteractionEyeSmile==0;
                source.Stop();yield return new WaitForSecondsRealtime(.7f);Require(result.switchClean,"Old avatar kept interaction state");
            }
            source.clip=null;source.loop=false;Destroy(signal);
        }
    }
}
