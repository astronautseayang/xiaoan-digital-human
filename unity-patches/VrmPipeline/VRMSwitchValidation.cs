using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UniVRM10;
namespace LocalHuman {
 public sealed class VRMSwitchValidation:MonoBehaviour {
  const string Dir="/home/yyy/digital-human/artifacts/validation/vrm-switch";
  [Serializable] sealed class Sample {public string avatar;public float[] rawFrames;public float maxFrameMs,maxFootDrift,soleGap;public int over33,blinkCount,springChains;public bool grounded;public float chestMotion,spineMotion,stanceWidth,shoulderWidth,observationSeconds;public int closedEyeFrames,reopenedEyeFrames;public float[] blinkIntervals;}
  [Serializable] sealed class SwitchTiming {public string avatar;public float clickMilliseconds,maxFrameMs;public float[] rawFrames;}
  [Serializable] sealed class Report {public bool discRemoved;public int imports;public bool cacheReused,profilePreserved;public List<SwitchTiming> switching=new List<SwitchTiming>();public bool passed;public string error,device;public bool wrongProfileSafe,unknownSafe,audioPreserved,uiReachable;public int switches;public List<Sample> samples=new List<Sample>();}
  EventSystem testEvents;Report report=new Report();
  [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)] static void Init(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-vrm-switch-self-test")>=0)new GameObject("VRMSwitchValidation").AddComponent<VRMSwitchValidation>();}
  static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
  IEnumerator Start(){Directory.CreateDirectory(Dir);var run=Run();while(true){bool more=false;object current=null;try{more=run.MoveNext();if(more)current=run.Current;}catch(Exception e){report.error=e.ToString();}if(!more||report.error!=null)break;yield return current;}report.passed=report.error==null;File.WriteAllText(Path.Combine(Dir,"runtime.json"),JsonUtility.ToJson(report,true));Debug.Log("VRM_SWITCH_TEST "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);}
  void Click(Button button){Check(button.IsInteractable(),"Disabled switch button");var point=RectTransformUtility.WorldToScreenPoint(null,button.transform.TransformPoint(((RectTransform)button.transform).rect.center));var data=new PointerEventData(testEvents){position=point,button=PointerEventData.InputButton.Left};var hits=new List<RaycastResult>();testEvents.RaycastAll(data,hits);Check(hits.Count>0&&hits[0].gameObject==button.gameObject,"Switch button blocked");ExecuteEvents.Execute(button.gameObject,data,ExecuteEvents.pointerClickHandler);report.uiReachable=true;}
  IEnumerator Run(){
   Check(Screen.width==1920&&Screen.height==1080,"Expected native 1920x1080");report.device=SystemInfo.graphicsDeviceName;var loader=FindObjectOfType<VrmAvatarLoader>();float end=Time.realtimeSinceStartup+90;
   while(!loader.Ready&&loader.Error==null&&Time.realtimeSinceStartup<end)yield return null;Check(loader.Ready,"Initial load failed: "+loader.Error);
   while(!LocalHumanStartup.Ready)yield return null;
   report.discRemoved=GameObject.Find("BevelledDisplayDisc")==null;
   Check(report.discRemoved,"Display disc still present");
   var floor=GameObject.Find("Floor").GetComponent<Collider>();
   Check(floor&&Mathf.Abs(floor.bounds.max.y+.57181f)<.0001f,"Visible ground/support height mismatch");
   testEvents=EventSystem.current;testEvents.enabled=false;
   var panel=loader.GetComponent<AvatarPipeline.LocalHumanPanel>();var source=loader.GetComponent<AudioSource>();
   var clip=AudioClip.Create("Continuous switch audio",48000*60,1,48000,false);var pcm=new float[clip.samples];for(int n=0;n<pcm.Length;n++)pcm[n]=.025f*Mathf.Sin(n*2*Mathf.PI*180/48000);clip.SetData(pcm,0);source.clip=clip;source.loop=true;source.Play();
   var instances=new Dictionary<string,Vrm10Instance>();
   foreach(string id in new[]{"man"}){
    Debug.Log("SWITCH_TEST_BEGIN "+id);var old=loader.Instance;double before=Time.realtimeSinceStartupAsDouble;
    var timing=new SwitchTiming{avatar=id};Click(panel.Refresh);
    timing.clickMilliseconds=(float)((Time.realtimeSinceStartupAsDouble-before)*1000);
    var switchFrames=new List<float>();double lastFrame=before;
    for(int n=0;n<30;n++){yield return new WaitForEndOfFrame();double now=Time.realtimeSinceStartupAsDouble;float ms=(float)((now-lastFrame)*1000);lastFrame=now;switchFrames.Add(ms);timing.maxFrameMs=Mathf.Max(timing.maxFrameMs,ms);}
    timing.rawFrames=switchFrames.ToArray();report.switching.Add(timing);
    Check(timing.clickMilliseconds<33&&timing.maxFrameMs<33,"Switch frame exceeded 33ms "+id+" "+timing.maxFrameMs);
    end=Time.realtimeSinceStartup+90;
    while(loader.IsSwitching&&Time.realtimeSinceStartup<end)yield return null;
    Check(loader.CurrentAvatar==id&&loader.Instance==old,"Switch failed: "+loader.Error);report.switches++;
    if(instances.TryGetValue(id,out var reused))Check(reused==loader.Instance,"Avatar was reimported");else instances[id]=loader.Instance;
    var face=loader.Instance.GetComponent<VRMFaceController>();
    Check(face.enabled&&face.LoadedTexture&&face.GetComponent<FaceMorphController>().enabled,"Cached face state lost");
    Check(face.AppliedProfiles==1,"Unchanged profile decoded again");report.profilePreserved=true;
    Check(source.isPlaying&&source.clip==clip,"Audio reset by switch");report.audioPreserved=true;
    Check(loader.GetComponent<LocalAvatarLipSync>().avatar==loader.Instance,"Lip target not rebound");
    GC.Collect();
    for(int n=0;n<180;n++)yield return new WaitForEndOfFrame();
    Check(loader.GetComponentsInChildren<Vrm10Instance>().Length==1,"Expected one active avatar");Check(loader.GetComponentsInChildren<Vrm10Instance>(true).Length==2,"Expected exactly two cached avatars");
    if(report.switches<=2){
     Debug.Log("SWITCH_TEST_MEASURE "+id);var sample=new Sample{avatar=id,springChains=loader.Instance.SpringBone.Springs.Count};var animator=loader.Instance.GetComponent<Animator>();Check(animator.isHuman&&animator.avatar.isValid,"Invalid humanoid");
     var feet=new[]{animator.GetBoneTransform(HumanBodyBones.LeftFoot),animator.GetBoneTransform(HumanBodyBones.RightFoot)};var start=new[]{feet[0].position,feet[1].position};var frames=new List<float>();double previous=Time.realtimeSinceStartupAsDouble;int blinks=loader.GetComponent<LocalAvatarLipSync>().BlinkCount;
     var chest=animator.GetBoneTransform(HumanBodyBones.Chest);var spine=animator.GetBoneTransform(HumanBodyBones.Spine);
     var chestStart=chest.localRotation;var spineStart=spine.localRotation;
     var lip=loader.GetComponent<LocalAvatarLipSync>();int observedBlink=lip.BlinkCount;
     var intervals=new List<float>();float observedAt=Time.unscaledTime;bool wasClosed=false;
     // Observe several complete breaths and blinks; keep the performance window at 240 frames.
     for(int n=0;n<720;n++) {
      yield return new WaitForEndOfFrame();double now=Time.realtimeSinceStartupAsDouble;
      float ms=(float)((now-previous)*1000);previous=now;
      if(n<240){frames.Add(ms);sample.maxFrameMs=Mathf.Max(sample.maxFrameMs,ms);if(ms>33)sample.over33++;}
      for(int i=0;i<2;i++)sample.maxFootDrift=Mathf.Max(sample.maxFootDrift,Vector3.Distance(start[i],feet[i].position));
      sample.chestMotion=Mathf.Max(sample.chestMotion,SmallRotationAngle(chestStart,chest.localRotation));
      sample.spineMotion=Mathf.Max(sample.spineMotion,SmallRotationAngle(spineStart,spine.localRotation));
      if(lip.BlinkCount!=observedBlink){observedBlink=lip.BlinkCount;if(lip.LastBlinkInterval>0)intervals.Add(lip.LastBlinkInterval);}
      if(lip.BlinkWeight>.98f){sample.closedEyeFrames++;wasClosed=true;}
      if(wasClosed&&lip.BlinkWeight<.001f)sample.reopenedEyeFrames++;
     }
     sample.observationSeconds=Time.unscaledTime-observedAt;sample.blinkIntervals=intervals.ToArray();
     sample.stanceWidth=Vector3.Distance(feet[0].position,feet[1].position);
     sample.shoulderWidth=Vector3.Distance(animator.GetBoneTransform(HumanBodyBones.LeftUpperArm).position,animator.GetBoneTransform(HumanBodyBones.RightUpperArm).position);
     Check(sample.chestMotion>.01f&&sample.spineMotion>.01f,"Missing chest/spine breathing "+id+" chest="+sample.chestMotion+" spine="+sample.spineMotion);
     Check(intervals.Count>=2&&sample.closedEyeFrames>0&&sample.reopenedEyeFrames>0,"Blink did not close and reopen "+id);
     foreach(float interval in intervals)Check(interval>=2.5f&&interval<=5.05f,"Blink interval out of range");
     if(id=="man")Check(Mathf.Abs(sample.stanceWidth-sample.shoulderWidth)<.015f,"Male stance differs from shoulder width");
     sample.rawFrames=frames.ToArray();sample.blinkCount=loader.GetComponent<LocalAvatarLipSync>().BlinkCount-blinks;sample.grounded=loader.Instance.GetComponent<VrmGrounding>().bothOnGround;
     float minimum=float.MaxValue;foreach(var r in loader.Instance.GetComponentsInChildren<SkinnedMeshRenderer>()){var mesh=new Mesh();r.BakeMesh(mesh);foreach(var v in mesh.vertices)minimum=Mathf.Min(minimum,r.transform.TransformPoint(v).y);Destroy(mesh);foreach(var m in r.sharedMaterials)Check(m&&m.shader&&m.shader.isSupported&&!m.shader.name.Contains("InternalError"),"Missing shader");}sample.soleGap=minimum+.57181f;
     report.samples.Add(sample);Check(sample.grounded&&sample.maxFootDrift<.002f&&Mathf.Abs(sample.soleGap)<.005f,"Feet not grounded "+id+" "+sample.soleGap);Check(sample.springChains>0,"Missing spring chains");
     yield return Capture(id,animator);
    }
   }
   report.imports=loader.ImportCount;report.cacheReused=report.imports==1;Check(report.cacheReused,"Repeated model import");
   var same=loader.Instance;var sameSwitch=loader.SwitchAvatarAsync(loader.CurrentAvatar);while(!sameSwitch.IsCompleted)yield return null;Check(sameSwitch.Result&&loader.Instance==same&&same.gameObject.activeSelf,"Same avatar selection failed");
   source.Stop();Destroy(clip);var currentAvatar=loader.Instance;
   var rejected=loader.SwitchAvatarAsync("unknown");while(!rejected.IsCompleted)yield return null;report.unknownSafe=!rejected.Result&&loader.Instance==currentAvatar;
   rejected=loader.SwitchAvatarAsync("man",loader.ProfilePath("woman"));while(!rejected.IsCompleted)yield return null;report.wrongProfileSafe=!rejected.Result&&loader.Instance==currentAvatar;
   Check(report.unknownSafe&&report.wrongProfileSafe,"Rejected switch mutated avatar");Check(Camera.main.backgroundColor==Color.white,"White background lost");foreach(var sample in report.samples)Check(sample.over33==0,"Long steady frames "+sample.avatar);
  }
  // Quaternion.Angle rounds tiny rotations to zero; atan2 preserves subtle breathing motion.
  static float SmallRotationAngle(Quaternion from,Quaternion to){var delta=Quaternion.Inverse(from)*to;return 2*Mathf.Atan2(new Vector3(delta.x,delta.y,delta.z).magnitude,Mathf.Abs(delta.w))*Mathf.Rad2Deg;}
  IEnumerator Capture(string id,Animator animator){var camera=Camera.main;var p=camera.transform.position;var q=camera.transform.rotation;
   for(int i=0;i<2;i++){if(i==1){var target=animator.GetBoneTransform(HumanBodyBones.Head).position;camera.transform.position=target+new Vector3(0,.025f,.62f);camera.transform.LookAt(target);}yield return new WaitForEndOfFrame();var rt=RenderTexture.GetTemporary(3840,2160,24);var active=RenderTexture.active;camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;var texture=new Texture2D(3840,2160,TextureFormat.RGB24,false);texture.ReadPixels(new Rect(0,0,3840,2160),0,0);texture.Apply();File.WriteAllBytes(Path.Combine(Dir,id+(i==0?"-studio.png":"-face.png")),texture.EncodeToPNG());Destroy(texture);camera.targetTexture=null;RenderTexture.active=active;RenderTexture.ReleaseTemporary(rt);}
   camera.transform.SetPositionAndRotation(p,q);yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(Dir,id+"-ui.png"),2);yield return new WaitForSecondsRealtime(.5f);
  }
 }
}
