using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UniVRM10;
namespace LocalHuman
{
    public sealed class VrmStageValidation:MonoBehaviour
    {
        [Serializable] sealed class Report{
            public bool bothOnStand;public float soleGap;public int screenWidth,screenHeight;
            public bool passed,humanoid,idle,whiteBackground,ui,rootPreserved,materialsSupported;
            public int frames,over33,springChains,springJoints,ikHits,renderers,materials,playbackStarts;
            public float maxFrameMs,maxFootDrift,springRotationDegrees;
            public string error,graphicsDevice;public float[] rawFrames;public string[] screenshots;
        }
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Initialize(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-vrm-self-test")>=0)new GameObject("VrmStageValidation").AddComponent<VrmStageValidation>();}
        IEnumerator Start(){yield return Run();}
        IEnumerator Run()
        {
            var report=new Report{graphicsDevice=SystemInfo.graphicsDeviceName};
            string dir="/home/yyy/digital-human/artifacts/validation/vrm-stage1";Directory.CreateDirectory(dir);
            var loader=FindObjectOfType<VrmAvatarLoader>();float deadline=Time.realtimeSinceStartup+90;
            while(loader&&!loader.Ready&&loader.Error==null&&Time.realtimeSinceStartup<deadline)yield return null;
            if(!loader||!loader.Ready){report.error=loader?loader.Error:"Missing loader";Save(report,dir);yield break;}
            while(!LocalHumanStartup.Ready)yield return null;
            var instance=loader.Instance;var animator=instance.GetComponent<Animator>();var ground=instance.GetComponent<VrmGrounding>();
            report.humanoid=animator.isHuman&&animator.avatar.isValid;
            report.idle=animator.GetCurrentAnimatorStateInfo(0).IsName("Stable Idle")&&!animator.applyRootMotion;
            report.rootPreserved=loader.transform.position==Vector3.zero&&loader.transform.rotation==Quaternion.identity&&loader.transform.localScale==Vector3.one;
            report.whiteBackground=Camera.main.clearFlags==CameraClearFlags.SolidColor&&Camera.main.backgroundColor==Color.white;
            report.ui=FindObjectOfType<AvatarPipeline.LocalHumanPanel>()!=null;
            report.materialsSupported=true;
            foreach(var r in instance.GetComponentsInChildren<SkinnedMeshRenderer>()){
                report.renderers++;foreach(var m in r.sharedMaterials){report.materials++;report.materialsSupported&=m&&m.shader&&m.shader.isSupported&&!m.shader.name.Contains("InternalError");}
            }
            var joints=instance.GetComponentsInChildren<VRM10SpringBoneJoint>();report.springChains=instance.SpringBone.Springs.Count;report.springJoints=joints.Length;
            var baseline=new Quaternion[joints.Length];for(int n=0;n<joints.Length;n++)baseline[n]=joints[n].transform.localRotation;
            var feet=new[]{animator.GetBoneTransform(HumanBodyBones.LeftFoot),animator.GetBoneTransform(HumanBodyBones.RightFoot)};
            var footStart=new[]{feet[0].position,feet[1].position};
            // Warm runtime native expressions, materials and SpringBone before the measured interval.
            for(int n=0;n<90;n++)yield return new WaitForEndOfFrame();
            for(int n=0;n<joints.Length;n++)baseline[n]=joints[n].transform.localRotation;
            footStart[0]=feet[0].position;footStart[1]=feet[1].position;
            var ms=new List<float>();float previous=Time.realtimeSinceStartup;
            for(int n=0;n<240;n++){
                yield return new WaitForEndOfFrame();float now=Time.realtimeSinceStartup;float delta=(now-previous)*1000;previous=now;ms.Add(delta);
                report.maxFrameMs=Mathf.Max(report.maxFrameMs,delta);if(delta>33)report.over33++;
                for(int i=0;i<2;i++)report.maxFootDrift=Mathf.Max(report.maxFootDrift,Vector3.Distance(footStart[i],feet[i].position));
                for(int i=0;i<joints.Length;i++)report.springRotationDegrees=Mathf.Max(report.springRotationDegrees,Quaternion.Angle(baseline[i],joints[i].transform.localRotation));
            }
            report.screenWidth=Screen.width;report.screenHeight=Screen.height;report.bothOnStand=ground.bothOnGround;
            float minimum=float.MaxValue;foreach(var r in instance.GetComponentsInChildren<SkinnedMeshRenderer>()){var baked=new Mesh();r.BakeMesh(baked);foreach(var v in baked.vertices)minimum=Mathf.Min(minimum,r.transform.TransformPoint(v).y);Destroy(baked);}
            report.soleGap=minimum+.57181f;
            report.frames=ms.Count;report.rawFrames=ms.ToArray();report.ikHits=ground.hits;
            // Native secondary motion response to a small torso turn; feet stay under IK.
            var chest=animator.GetBoneTransform(HumanBodyBones.Chest);
            for(int n=0;n<24;n++){
                yield return null;chest.localRotation*=Quaternion.Euler(0,Mathf.Sin(n*.3f)*3,0);
                yield return new WaitForEndOfFrame();
                for(int i=0;i<joints.Length;i++)report.springRotationDegrees=Mathf.Max(report.springRotationDegrees,Quaternion.Angle(baseline[i],joints[i].transform.localRotation));
            }
            yield return FindObjectOfType<LocalHumanDemo>().ChatWithAudio("你好，请用一句话介绍自己。");
            yield return FindObjectOfType<LocalHumanDemo>().Recognize(File.ReadAllBytes("/home/yyy/digital-human/assets/reference/me.wav"));
            report.playbackStarts=FindObjectOfType<LocalHumanDemo>().PlaybackStarts;
            var camera=Camera.main;Vector3 oldPos=camera.transform.position;Quaternion oldRot=camera.transform.rotation;
            var pictures=new List<string>();
            for(int n=0;n<8;n++){
                Vector3 target=new Vector3(0,-.15f,0);float angle=new[]{0,45,90,180,-45,0,0,0}[n]*Mathf.Deg2Rad;
                if(n<5)camera.transform.position=target+new Vector3(Mathf.Sin(angle)*1.75f,.17f,Mathf.Cos(angle)*1.75f);
                else{target=n==5?animator.GetBoneTransform(HumanBodyBones.Head).position:n==6?animator.GetBoneTransform(HumanBodyBones.RightHand).position:(feet[0].position+feet[1].position)*.5f;camera.transform.position=target+new Vector3(0,.03f,n==5?.65f:.5f);}
                camera.transform.LookAt(target);yield return new WaitForEndOfFrame();
                var rt=RenderTexture.GetTemporary(3840,2160,24);camera.targetTexture=rt;camera.Render();var previousRT=RenderTexture.active;RenderTexture.active=rt;
                var texture=new Texture2D(3840,2160,TextureFormat.RGB24,false);texture.ReadPixels(new Rect(0,0,3840,2160),0,0);texture.Apply();
                string path=Path.Combine(dir,"view-"+n+".png");File.WriteAllBytes(path,texture.EncodeToPNG());pictures.Add(path);
                Destroy(texture);RenderTexture.active=previousRT;camera.targetTexture=null;RenderTexture.ReleaseTemporary(rt);
            }
            camera.transform.SetPositionAndRotation(oldPos,oldRot);
            yield return new WaitForEndOfFrame();string uiPath=Path.Combine(dir,"view-ui.png");ScreenCapture.CaptureScreenshot(uiPath,2);
            for(int n=0;n<30;n++){yield return new WaitForEndOfFrame();if(File.Exists(uiPath))break;}pictures.Add(uiPath);
            report.screenshots=pictures.ToArray();
            report.passed=report.bothOnStand&&Mathf.Abs(report.soleGap)<.003f&&report.humanoid&&report.idle&&report.rootPreserved&&report.whiteBackground&&report.ui&&report.materialsSupported&&report.springChains>0&&report.springRotationDegrees>.01f&&report.ikHits>0&&report.maxFootDrift<.002f&&report.over33==0&&report.playbackStarts>=2;
            Save(report,dir);
        }
        void Save(Report report,string dir){File.WriteAllText(Path.Combine(dir,"runtime.json"),JsonUtility.ToJson(report,true));Debug.Log("VRM_STAGE1 "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);}
    }
}
