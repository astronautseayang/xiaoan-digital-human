using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UniVRM10;
namespace LocalHuman
{
    public sealed class VRMIntegrationValidation:MonoBehaviour
    {
        const string Dir="/home/yyy/digital-human/artifacts/validation/vrm-stage4";
        [Serializable] sealed class DefaultVoice { public string label; }
        [Serializable] sealed class Report {
            public bool passed,whiteBackground,softShadow,ui,additive,grounded,mouthReleased,photoEmotionIgnored,eyesReopen;
            public int interactiveGreetings,interactiveGestures;public bool interactionReleased;
            public bool voiceEnrollment,voiceReset,answerAutoScroll;public float firstTextSeconds,firstAudioSeconds;
            public bool photoSmileApplied,expressionSmooth,expressionInvalidSafe;public float expressionDuration,maxSmileEyeWeight;public Vector4 photoExpression;
            public int openEyeFrames,closedEyeFrames;public float maxRestingLidWeight;
            public string error,graphicsDevice; public int width,height,playbacks,springChains,springJoints,blinkIdle,blinkSpeech,frames,over33;
            public float maxFrameMs,maxFootDrift,chestMotion,springMotion,maxMorphError,maxProfileError,shadowStrength;
            public float[] rawFrames,vowelMax,blinkIntervals;public string[] screenshots;
        }
        EventSystem testEvents;Report report=new Report(); Exception failure;
        readonly ExpressionPreset[] vowels={ExpressionPreset.aa,ExpressionPreset.ih,ExpressionPreset.ou,ExpressionPreset.ee,ExpressionPreset.oh};
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Initialize(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-vrm-integration-self-test")>=0)new GameObject("VRMIntegrationValidation").AddComponent<VRMIntegrationValidation>();}
        IEnumerator Start(){
            Directory.CreateDirectory(Dir);var run=Run();
            while(true){bool more=false;object value=null;try{more=run.MoveNext();if(more)value=run.Current;}catch(Exception e){failure=e;}
                if(!more||failure!=null)break;yield return value;}
            report.error=failure?.ToString();report.passed=failure==null;
            File.WriteAllText(Path.Combine(Dir,"runtime.json"),JsonUtility.ToJson(report,true));Debug.Log("VRM_STAGE4 "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);
        }
        static void Require(bool ok,string error){if(!ok)throw new Exception(error);}
        void Click(Button button){
            Require(button&&button.IsInteractable(),"Button unavailable: "+button);
            var data=new PointerEventData(testEvents){position=RectTransformUtility.WorldToScreenPoint(null,button.transform.TransformPoint(((RectTransform)button.transform).rect.center)),button=PointerEventData.InputButton.Left};
            var hits=new List<RaycastResult>();testEvents.RaycastAll(data,hits);
            Require(hits.Count>0&&hits[0].gameObject==button.gameObject,"Button not reachable by screen raycast: "+button.name);
            ExecuteEvents.Execute(button.gameObject,data,ExecuteEvents.pointerClickHandler);
        }
        void CheckMerged(Vrm10Instance avatar){
            var expected=new Dictionary<SkinnedMeshRenderer,Dictionary<int,float>>();
            foreach(var clip in avatar.Vrm.Expression.Clips){
                var key=avatar.Vrm.Expression.CreateKey(clip.Clip);float actual=avatar.Runtime.Expression.ActualWeights[key];
                if(key.IsMouth||key.IsBlink)Require(Mathf.Abs(actual-avatar.Runtime.Expression.GetWeight(key))<.0001f,"Emotion suppressed mouth/blink");
                foreach(var binding in clip.Clip.MorphTargetBindings){
                    var node=string.IsNullOrEmpty(binding.RelativePath)?avatar.transform:avatar.transform.Find(binding.RelativePath);
                    var r=node?node.GetComponent<SkinnedMeshRenderer>():null;Require(r,"Invalid face binding");
                    if(!expected.TryGetValue(r,out var shapes)){shapes=new Dictionary<int,float>();expected.Add(r,shapes);}
                    shapes.TryGetValue(binding.Index,out var weight);shapes[binding.Index]=weight+binding.Weight*100*actual;
                }
            }
            foreach(var r in expected)foreach(var shape in r.Value)report.maxMorphError=Mathf.Max(report.maxMorphError,Mathf.Abs(r.Key.GetBlendShapeWeight(shape.Key)-Mathf.Clamp(shape.Value+avatar.GetComponent<FaceMorphController>().ExpressionAddition(r.Key,shape.Key),0,100)));
            Require(report.maxMorphError<.02f,"Native mesh is not additive");
        }
        IEnumerator Run(){
            var loader=FindObjectOfType<VrmAvatarLoader>();float deadline=Time.realtimeSinceStartup+90;
            while(loader&&!loader.Ready&&loader.Error==null&&Time.realtimeSinceStartup<deadline)yield return null;
            Require(loader&&loader.Ready,"VRM load failed");while(!LocalHumanStartup.Ready)yield return null;
            testEvents=EventSystem.current;testEvents.enabled=false;
            var avatar=loader.Instance;var animator=avatar.GetComponent<Animator>();var face=avatar.GetComponent<VRMFaceController>();
            var lip=loader.GetComponent<LocalAvatarLipSync>();var demo=loader.GetComponent<LocalHumanDemo>();var panel=loader.GetComponent<AvatarPipeline.LocalHumanPanel>();
            report.graphicsDevice=SystemInfo.graphicsDeviceName;report.width=Screen.width;report.height=Screen.height;
            report.whiteBackground=Camera.main.clearFlags==CameraClearFlags.SolidColor&&Camera.main.backgroundColor==Color.white;
            var key=GameObject.Find("SoftKey").GetComponent<Light>();report.shadowStrength=key.shadowStrength;report.softShadow=key.shadows==LightShadows.Soft&&Mathf.Abs(key.shadowStrength-.35f)<.001f;
            Require(report.whiteBackground&&report.softShadow,"White studio settings wrong");
            // Keep the actual Stage 2 palette/hair/texture and photo Joy during real speech.
            face.ApplyFaceProfile("/home/yyy/digital-human/artifacts/validation/face-stage2/ExportedFaceData/face_params.json");Require(face.LastError==null,"Stage 2 profile rejected");
            yield return new WaitForSecondsRealtime(.3f);
            string profile="/home/yyy/digital-human/artifacts/validation/face-stage2/ExportedFaceData/face_params.json";face.ApplyFaceProfile(profile);
            yield return new WaitForSecondsRealtime(.4f);
            var morph=avatar.GetComponent<FaceMorphController>();
            Require(morph.CurrentExpression.x>.8f&&morph.PhotoMouthOpen>.05f,"Photo smile/open mouth not applied");
            foreach(var r in face.Renderers)if(r.sharedMesh)for(int i=0;i<r.sharedMesh.blendShapeCount;i++) {
                if(r.sharedMesh.GetBlendShapeName(i).EndsWith("mouth_smile"))Require(r.GetBlendShapeWeight(i)>50,"Smile missing from actual mesh");
                if(r.sharedMesh.GetBlendShapeName(i).EndsWith("eye_smile"))Require(r.GetBlendShapeWeight(i)<23,"Photo smile closed the eyes");
            }
            report.photoSmileApplied=true;report.photoExpression=morph.CurrentExpression;
            foreach(var r in face.Renderers)if(r.sharedMesh)for(int i=0;i<r.sharedMesh.blendShapeCount;i++)if(r.sharedMesh.GetBlendShapeName(i).EndsWith("eye_smile"))report.maxSmileEyeWeight=Mathf.Max(report.maxSmileEyeWeight,r.GetBlendShapeWeight(i));
            var held=morph.CurrentExpression;
            string badExpression=Path.Combine(Dir,"invalid-expression.json");
            File.WriteAllText(badExpression,"{\"skin_tint\":\"#FFFFFF\",\"blendshapes\":{},\"expression\":{\"smile_degree\":2}}");
            face.ApplyFaceProfile(badExpression);Require(face.LastError!=null&&morph.CurrentExpression==held,"Invalid expression mutated profile");
            report.expressionInvalidSafe=true;
            morph.ApplyExpression(Vector4.zero);yield return new WaitForSecondsRealtime(.35f);
            float expressionStart=Time.unscaledTime;morph.ApplyExpression(held);
            Require(morph.CurrentExpression==Vector4.zero,"Expression snapped at start");
            yield return new WaitForSecondsRealtime(.12f);
            Require(morph.CurrentExpression.x>0&&morph.CurrentExpression.x<held.x,"Expression has no intermediate state");
            while(Time.unscaledTime-expressionStart<.3f)yield return null;
            yield return null;report.expressionDuration=Time.unscaledTime-expressionStart;
            report.expressionSmooth=Vector4.Distance(morph.CurrentExpression,held)<.001f&&report.expressionDuration<.35f;
            Require(report.expressionSmooth,"Expression failed 0.3 second transition");
            face.ApplyFaceProfile(profile);yield return new WaitForSecondsRealtime(.35f);
            var happy=new ExpressionKey(ExpressionPreset.happy);
            report.photoEmotionIgnored=!face.applyProfileExpressions&&Mathf.Abs(avatar.Runtime.Expression.GetWeight(happy))<.001f;
            Require(report.photoEmotionIgnored,"Photo smile became a persistent emotion");
            var blinkClip=avatar.Vrm.Expression.Blink;
            var joints=avatar.GetComponentsInChildren<VRM10SpringBoneJoint>();
            report.springChains=avatar.SpringBone.Springs.Count;report.springJoints=joints.Length;
            var chest=animator.GetBoneTransform(HumanBodyBones.Chest);var chestStart=chest.localRotation;
            var rotations=new Quaternion[joints.Length];for(int i=0;i<joints.Length;i++)rotations[i]=joints[i].transform.localRotation;
            var feet=new[]{animator.GetBoneTransform(HumanBodyBones.LeftFoot),animator.GetBoneTransform(HumanBodyBones.RightFoot)};var positions=new[]{feet[0].position,feet[1].position};
            var intervals=new List<float>();int previousBlink=lip.BlinkCount;
            // Observe only native idle breathing; no test torque or joint injection.
            float until=Time.unscaledTime+12;
            while(Time.unscaledTime<until){
                yield return new WaitForEndOfFrame();
                report.chestMotion=Mathf.Max(report.chestMotion,Quaternion.Angle(chestStart,chest.localRotation));
                for(int i=0;i<joints.Length;i++)report.springMotion=Mathf.Max(report.springMotion,Quaternion.Angle(rotations[i],joints[i].transform.localRotation));
                for(int i=0;i<2;i++)report.maxFootDrift=Mathf.Max(report.maxFootDrift,Vector3.Distance(positions[i],feet[i].position));
                if(lip.BlinkCount!=previousBlink){report.blinkIdle++;previousBlink=lip.BlinkCount;if(lip.LastBlinkInterval>0)intervals.Add(lip.LastBlinkInterval);}
                CheckMerged(avatar);
                if(lip.BlinkWeight<.001f){
                    report.openEyeFrames++;
                    foreach(var binding in blinkClip.MorphTargetBindings){
                        var node=string.IsNullOrEmpty(binding.RelativePath)?avatar.transform:avatar.transform.Find(binding.RelativePath);
                        report.maxRestingLidWeight=Mathf.Max(report.maxRestingLidWeight,node.GetComponent<SkinnedMeshRenderer>().GetBlendShapeWeight(binding.Index));
                    }
                }else if(lip.BlinkWeight>.98f)report.closedEyeFrames++;
            }
            report.eyesReopen=report.openEyeFrames>600&&report.closedEyeFrames>=4&&report.maxRestingLidWeight<.01f;
            Require(report.eyesReopen,"Eyelids did not return to a fully open rest pose");
            Require(report.chestMotion>.01f&&report.springMotion>.01f&&report.springChains>0,"Breathing did not produce native secondary motion");
            typeof(LocalHumanDemo).GetField("answer",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic).SetValue(demo,new string('测',500));
            yield return new WaitForSecondsRealtime(.1f);
            report.answerAutoScroll=panel.AnswerScroll.content.rect.height>panel.AnswerScroll.viewport.rect.height&&Mathf.Abs(panel.AnswerScroll.verticalNormalizedPosition)<.01f;
            Require(report.answerAutoScroll,"Long answer did not scroll to latest text");
            // Clipboard, field edit and send all go through the real UI event path.
            GUIUtility.systemCopyBuffer="请用一句话说：欢迎来到纯白展厅，我们可以用语音聊天。";
            Click(panel.Paste);yield return null;Require(panel.Input.text==GUIUtility.systemCopyBuffer,"Paste failed");
            panel.Input.text+="谢谢。";Require(demo.Question==panel.Input.text,"Input event failed");
            int starts=demo.PlaybackStarts;Click(panel.Send);yield return null;
            deadline=Time.unscaledTime+100;
            while((demo.IsBusy||demo.PlaybackStarts==starts)&&Time.unscaledTime<deadline)yield return null;
            Require(demo.PlaybackStarts>starts&&string.IsNullOrEmpty(demo.LastPlaybackError),"UI TTS failed");
            report.firstTextSeconds=demo.FirstTextSeconds;report.firstAudioSeconds=demo.FirstAudioSeconds;
            Require(report.firstTextSeconds>=0&&report.firstAudioSeconds>0,"Streaming timings missing");
            yield return new WaitForSecondsRealtime(.1f);
            Require(panel.Enroll.IsInteractable()&&panel.ResetVoice.IsInteractable(),"Voice buttons unavailable");
            yield return demo.EnrollVoice(File.ReadAllBytes("/home/yyy/digital-human/assets/reference/me.wav"));
            report.voiceEnrollment=demo.VoiceName=="我的录入音色";Require(report.voiceEnrollment,"Voice enrollment failed");
            yield return new WaitForSecondsRealtime(.1f);
            Click(panel.ResetVoice);yield return null;while(demo.IsBusy)yield return null;
            var expectedVoice=JsonUtility.FromJson<DefaultVoice>(File.ReadAllText("/home/yyy/digital-human/config/voice-default.json")).label;
            report.voiceReset=demo.VoiceName==expectedVoice;Require(report.voiceReset,"Voice reset failed");
            yield return demo.Recognize(File.ReadAllBytes("/home/yyy/digital-human/assets/reference/me.wav"));
            Require(demo.PlaybackStarts>=starts+2&&string.IsNullOrEmpty(demo.LastPlaybackError),"ASR/TTS failed");
            yield return null;report.ui=panel.IsVisible&&panel.Record.IsInteractable()&&panel.Replay.IsInteractable();Require(report.ui,"UI did not recover after speech");
            var frames=new List<float>();report.vowelMax=new float[5];
            // Cached real GPT-SoVITS audio, with the renderer/expression checks outside timing calculations.
            for(int replay=0;replay<3&&(frames.Count<240||report.blinkSpeech<1);replay++){
                Click(panel.Replay);deadline=Time.unscaledTime+10;
                while(!demo.IsSpeaking&&Time.unscaledTime<deadline)yield return null;
                Require(demo.IsSpeaking,"Replay failed");yield return new WaitForEndOfFrame();float previous=Time.realtimeSinceStartup;
                while(demo.IsSpeaking){
                    yield return new WaitForEndOfFrame();float now=Time.realtimeSinceStartup,ms=(now-previous)*1000;previous=now;
                    frames.Add(ms);report.maxFrameMs=Mathf.Max(report.maxFrameMs,ms);if(ms>33)report.over33++;
                    for(int i=0;i<5;i++)report.vowelMax[i]=Mathf.Max(report.vowelMax[i],avatar.Runtime.Expression.ActualWeights[new ExpressionKey(vowels[i])]);
                    // Photo Joy stays disabled; the interactive speech layer now owns a bounded happy input.
                    float expectedHappy=loader.GetComponent<AvatarInteractiveMotion>().SmileWeight*.18f;
                    report.maxProfileError=Mathf.Max(report.maxProfileError,Mathf.Abs(avatar.Runtime.Expression.GetWeight(happy)-expectedHappy));CheckMerged(avatar);
                    for(int i=0;i<2;i++)report.maxFootDrift=Mathf.Max(report.maxFootDrift,Vector3.Distance(positions[i],feet[i].position));
                    if(lip.BlinkCount!=previousBlink){if(lip.LastBlinkStarted>=Time.unscaledTime-.03f)report.blinkSpeech++;previousBlink=lip.BlinkCount;if(lip.LastBlinkInterval>0)intervals.Add(lip.LastBlinkInterval);}
                }
                while(demo.IsBusy)yield return null;yield return null;
            }
            report.frames=frames.Count;report.rawFrames=frames.ToArray();report.blinkIntervals=intervals.ToArray();
            foreach(float interval in intervals)Require(interval>=2.5f&&interval<=5.04f,"Blink interval outside 2.5–5s + frame");
            foreach(float maximum in report.vowelMax)Require(maximum>.001f,"A real vowel was inactive");
            report.additive=report.maxProfileError<.001f&&report.maxMorphError<.02f;
            report.grounded=avatar.GetComponent<VrmGrounding>().bothOnGround&&report.maxFootDrift<.002f;
            yield return new WaitForSecondsRealtime(.6f);report.mouthReleased=true;
            foreach(var vowel in vowels)report.mouthReleased&=Mathf.Abs(avatar.Runtime.Expression.GetWeight(new ExpressionKey(vowel))-(vowel==ExpressionPreset.aa?morph.PhotoMouthOpen:0))<.001f;
            Require(report.blinkIdle>=2&&report.blinkSpeech>=1&&report.additive&&report.grounded&&report.mouthReleased,"Runtime isolation/grounding/blink failed");
            var interaction=loader.GetComponent<AvatarInteractiveMotion>();
            report.interactiveGreetings=interaction.GreetingCount;report.interactiveGestures=interaction.GestureCount;
            report.interactionReleased=interaction.LayerWeight==0&&interaction.SmileWeight==0&&interaction.BrowWeight==0&&interaction.FocusWeight==0;
            Require(report.interactiveGreetings>=1&&report.interactionReleased,"Live greeting or interaction release failed");
            report.playbacks=demo.PlaybackStarts;
            // Capture after timed windows. 4K readback is deliberately outside performance sample.
            var pictures=new List<string>();var camera=Camera.main;var oldPosition=camera.transform.position;var oldRotation=camera.transform.rotation;
            for(int view=0;view<4;view++){
                if(view==1){var head=animator.GetBoneTransform(HumanBodyBones.Head).position;camera.transform.position=head+new Vector3(0,.03f,.65f);camera.transform.LookAt(head);}
                if(view==3){camera.transform.SetPositionAndRotation(oldPosition,oldRotation);yield return new WaitForEndOfFrame();string ui=Path.Combine(Dir,"studio-ui.png");ScreenCapture.CaptureScreenshot(ui,2);for(int i=0;i<60&&!File.Exists(ui);i++)yield return new WaitForEndOfFrame();pictures.Add(ui);continue;}
                if(view<2){while(lip.BlinkWeight>.001f || Time.unscaledTime-lip.LastBlinkStarted<.3f)yield return null;}
                if(view==2){deadline=Time.unscaledTime+5;while(lip.BlinkWeight<.98f&&Time.unscaledTime<deadline)yield return new WaitForEndOfFrame();Require(lip.BlinkWeight>=.98f,"No full blink to capture");}
                var rt=RenderTexture.GetTemporary(3840,2160,24);var old=RenderTexture.active;camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
                var image=new Texture2D(3840,2160,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,3840,2160),0,0);image.Apply();string path=Path.Combine(Dir,view==0?"studio.png":view==1?"face.png":"face-blink.png");File.WriteAllBytes(path,image.EncodeToPNG());pictures.Add(path);
                Destroy(image);camera.targetTexture=null;RenderTexture.active=old;RenderTexture.ReleaseTemporary(rt);
            }
            report.screenshots=pictures.ToArray();
            Require(report.frames>=180&&report.over33==0,"Speech performance exceeded 33ms or too few frames");
        }
    }
}
