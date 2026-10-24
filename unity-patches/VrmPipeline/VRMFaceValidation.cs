using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UniVRM10;
using UniJSON;
namespace LocalHuman
{
    public sealed class VRMFaceValidation:MonoBehaviour
    {
        [Serializable] sealed class Report {
            public bool passed,autoMounted,profileAccepted,smoothStart,expressionReached,customShapeReached,skinMatched,textureBound;
            public bool toonPaletteMatched,hairMatched,neutralAlbedoBound;
            public bool missingTextureSafe,invalidRejected,interruptionSmooth,restored,lipSyncIsolated,blinkIsolated;
            public int skinMaterials,featureMaterials,frames,over33;
            public float transitionSeconds,maxFrameMs;public string error;public string[] unmatched;public float[] rawFrames;
        }
        const string Dir="/home/yyy/digital-human/artifacts/validation/vrm-stage3";
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Initialize(){if(Array.IndexOf(Environment.GetCommandLineArgs(),"-vrm-face-self-test")>=0)new GameObject("VRMFaceValidation").AddComponent<VRMFaceValidation>();}
        Report report=new Report();
        Exception failure;
        IEnumerator Start()
        {
            Directory.CreateDirectory(Dir);
            var routine=Run();
            while(true){object current=null;bool more=false;try{more=routine.MoveNext();if(more)current=routine.Current;}catch(Exception e){failure=e;}
                if(failure!=null||!more)break;yield return current;}
            report.error=failure?.ToString();report.passed=failure==null;
            File.WriteAllText(Path.Combine(Dir,"runtime.json"),JsonUtility.ToJson(report,true));
            Debug.Log("VRM_FACE_STAGE3 "+JsonUtility.ToJson(report));Application.Quit(report.passed?0:2);
        }
        static Color ReadColor(JsonNode json,string key){json.TryGet(key,out var array);var v=new List<float>();foreach(var item in array.ArrayItems())v.Add(item.GetSingle());return new Color(v[0],v[1],v[2],1);}
        static bool Near(Color a,Color b){return Mathf.Abs(a.r-b.r)<.001f&&Mathf.Abs(a.g-b.g)<.001f&&Mathf.Abs(a.b-b.b)<.001f;}
        static void Require(bool value,string error){if(!value)throw new Exception(error);}
        IEnumerator Run()
        {
            var loader=FindObjectOfType<VrmAvatarLoader>();float deadline=Time.realtimeSinceStartup+90;
            while(loader&&!loader.Ready&&loader.Error==null&&Time.realtimeSinceStartup<deadline)yield return null;
            Require(loader&&loader.Ready,"Loader did not become ready");
            while(!LocalHumanStartup.Ready)yield return null;
            var face=loader.Instance.GetComponent<VRMFaceController>();
            report.autoMounted=face&&face.Animator&&face.Renderers.Length>0;Require(report.autoMounted,"Auto discovery failed");
            face.applyProfileExpressions=true; // Explicit emotion API coverage; production photo default is identity-only.
            report.skinMaterials=face.SkinMaterialCount;report.featureMaterials=face.FeatureMaterialCount;
            Require(report.skinMaterials>=2&&report.featureMaterials>=1,"Face/body/eye materials not found");
            var expression=loader.Instance.Runtime.Expression;var happy=new ExpressionKey(ExpressionPreset.happy);
            // Add a real test-only custom shape to an imported mesh, not to production assets.
            var renderer=face.Renderers[0];var original=renderer.sharedMesh;var mesh=Instantiate(original);
            var delta=new Vector3[mesh.vertexCount];delta[0]=new Vector3(.001f,0,0);
            mesh.AddBlendShapeFrame("Stage3JawRound",100,delta,new Vector3[mesh.vertexCount],new Vector3[mesh.vertexCount]);
            renderer.sharedMesh=mesh;int index=mesh.blendShapeCount-1;
            face.shapeMappings=new[]{new VRMFaceController.ShapeMapping{profileKey="JawRound",shapeName="Stage3JawRound"}};
            string profile="/home/yyy/digital-human/artifacts/validation/face-stage2/ExportedFaceData/face_params.json";
            Require(File.Exists(profile),"Run Stage 2 extractor first");
            // First apply the actual extractor output and check decode/optional capabilities.
            face.ApplyFaceProfile(profile);report.profileAccepted=face.LastError==null&&face.AppliedProfiles==1;Require(report.profileAccepted,"Actual Stage 2 profile rejected");
            yield return new WaitForSecondsRealtime(.32f);
            report.textureBound=face.LoadedTexture&&face.LoadedTexture.width==256&&face.LoadedTexture.height==128;
            bool bound=false;foreach(var r in face.Renderers)foreach(var m in r.sharedMaterials)if(m&&m.HasProperty("_MainTex")&&m.GetTexture("_MainTex")==face.LoadedTexture && m.GetTextureScale("_MainTex")==new Vector2(.5f,1))bound=true;
            report.textureBound&=bound;Require(report.textureBound,"PNG was not bound to feature material");
            var packet=File.ReadAllText(profile).ParseAsJson();
            packet.TryGet("skin",out var skinPalette);packet.TryGet("hair",out var hairPalette);
            Color skinBase=ReadColor(skinPalette,"base_color"),skinShade=ReadColor(skinPalette,"shade_color");
            Color hairBase=ReadColor(hairPalette,"base_color"),hairShade=ReadColor(hairPalette,"shade_color");
            var sync=face.GetComponent<FaceMorphController>();
            bool skinOk=true,hairOk=true,neutralOk=true;int skinSlots=0,hairSlots=0;
            foreach(var r in face.Renderers) {
                var materials=r.sharedMaterials;
                for(int slot=0;slot<materials.Length;slot++) {
                    var m=materials[slot];if(!m)continue;string name=m.name.ToLowerInvariant();
                    bool isSkin=name=="alicia_face"||name=="alicia_body";
                    bool isHair=name.Contains("hair")&&!name.Contains("wear");
                    if(!isSkin&&!isHair)continue;
                    var block=new MaterialPropertyBlock();r.GetPropertyBlock(block,slot);
                    neutralOk&=block.GetTexture("_MainTex")&&block.GetTexture("_MainTex")!=m.GetTexture("_MainTex");
                    if(isSkin) {skinSlots++;skinOk&=Near(m.GetColor("_Color"),skinBase)&&Near(m.GetColor("_ShadeColor"),skinShade)&&Near(block.GetColor("_Color"),sync.ShaderColor(skinBase))&&Near(block.GetColor("_ShadeColor"),sync.ShaderColor(skinShade));}
                    if(isHair) {hairSlots++;hairOk&=Near(block.GetColor("_Color"),sync.ShaderColor(hairBase))&&Near(block.GetColor("_ShadeColor"),sync.ShaderColor(hairShade));}
                }
            }
            report.toonPaletteMatched=skinSlots>=2&&skinOk;report.hairMatched=hairSlots>=3&&hairOk;
            report.neutralAlbedoBound=neutralOk;
            Require(report.toonPaletteMatched&&report.hairMatched&&report.neutralAlbedoBound,"Toon palette/hair per-slot block or neutral albedo missing");
            report.unmatched=face.UnmatchedControls;
            // Legacy Joy regression uses a profile without the new explicit expression field.
            string legacy=Path.Combine(Dir,"legacy-profile.json");
            File.WriteAllText(legacy,"{\"skin_tint\":\"#FFD6DD\",\"blendshapes\":{\"Joy\":1}}");
            face.ApplyFaceProfile(legacy);yield return new WaitForSecondsRealtime(.32f);
            float originalHappy=expression.GetWeight(happy);
            // Deterministic targets exercise smooth interpolation and superseding a transition.
            string test=Path.Combine(Dir,"test-profile.json");
            File.WriteAllText(test,"{\"skin_tint\":\"#C8A080\",\"blendshapes\":{\"Joy\":0.2,\"JawRound\":0.6},\"texture_path\":\"missing.png\"}");
            var texture=face.LoadedTexture;face.ApplyFaceProfile(test);
            report.smoothStart=Mathf.Abs(expression.GetWeight(happy)-originalHappy)<.001f;Require(report.smoothStart,"Expression snapped on ApplyFaceProfile");
            yield return new WaitForSecondsRealtime(.1f);
            float mid=expression.GetWeight(happy);Require(mid>.2f&&mid<originalHappy,"No intermediate expression weight");
            File.WriteAllText(test,"{\"skin_tint\":\"#C8A080\",\"blendshapes\":{\"Joy\":0.7,\"JawRound\":0.8}}");
            face.ApplyFaceProfile(test);report.interruptionSmooth=Mathf.Abs(expression.GetWeight(happy)-mid)<.001f;Require(report.interruptionSmooth,"Interrupted transition snapped");
            yield return new WaitForSecondsRealtime(.32f);
            report.expressionReached=Mathf.Abs(expression.GetWeight(happy)-.7f)<.001f;
            report.customShapeReached=Mathf.Abs(renderer.GetBlendShapeWeight(index)-80)<.01f;
            report.transitionSeconds=face.LastTransitionDuration;
            Require(report.expressionReached&&report.customShapeReached&&!face.IsTransitioning,"Targets not reached");
            Require(report.transitionSeconds>=.25f&&report.transitionSeconds<.3f,"Transition did not finish at .25s + one frame");
            report.missingTextureSafe=face.LoadedTexture==texture;Require(report.missingTextureSafe,"Missing/null texture discarded previous image");
            ColorUtility.TryParseHtmlString("#C8A080",out var tint);Color expected=tint*face.studioExposure;int skinCount=0;bool colors=true;
            foreach(var r in face.Renderers)foreach(var m in r.sharedMaterials)if(m&&(m.name=="Alicia_face"||m.name=="Alicia_body")){
                skinCount++;foreach(var prop in new[]{"_Color","_ShadeColor"}){var c=m.GetColor(prop);colors&=Mathf.Abs(c.r-expected.r)<.001f&&Mathf.Abs(c.g-expected.g)<.001f&&Mathf.Abs(c.b-expected.b)<.001f;}}
            report.skinMatched=skinCount>=2&&colors;Require(report.skinMatched,"Face and body tint differ");
            int applied=face.AppliedProfiles;
            foreach(var bad in new[]{"{", "{\"skin_tint\":\"oops\",\"blendshapes\":{}}", "{\"skin_tint\":\"#FFFFFF\",\"blendshapes\":{\"Joy\":2}}", "{\"skin_tint\":\"#FFFFFF\",\"blendshapes\":{},\"hair\":{\"base_color\":[2,0,0],\"shade_color\":[0,0,0]}}"}) {
                File.WriteAllText(test,bad);face.ApplyFaceProfile(test);Require(face.LastError!=null&&face.AppliedProfiles==applied,"Invalid profile accepted");
            }
            face.ApplyFaceProfile(Path.Combine(Dir,"absent.json"));Require(face.LastError!=null&&face.AppliedProfiles==applied,"Missing profile accepted");
            File.WriteAllText(Path.Combine(Dir,"bad.png"),"not png");
            File.WriteAllText(test,"{\"skin_tint\":\"#FFFFFF\",\"blendshapes\":{\"Joy\":0},\"texture_path\":\"bad.png\"}");
            face.ApplyFaceProfile(test);Require(face.LastError!=null&&face.AppliedProfiles==applied,"Invalid PNG accepted");
            report.invalidRejected=Mathf.Abs(expression.GetWeight(happy)-.7f)<.001f&&face.LoadedTexture==texture;Require(report.invalidRejected,"Rejected profile mutated state");
            // Runtime input ownership: face expression cannot write vowels or blink.
            var lip=loader.GetComponent<LocalAvatarLipSync>();lip.enabled=false;
            var aa=new ExpressionKey(ExpressionPreset.aa);var blink=new ExpressionKey(ExpressionPreset.blink);
            expression.SetWeight(aa,.31f);expression.SetWeight(blink,.23f);
            yield return null;
            report.lipSyncIsolated=Mathf.Abs(expression.GetWeight(aa)-.31f)<.001f;report.blinkIsolated=Mathf.Abs(expression.GetWeight(blink)-.23f)<.001f;
            Require(report.lipSyncIsolated&&report.blinkIsolated,"Face controller overwrote lip/blink inputs");lip.enabled=true;
            // Include repeated profile parses and 0.25-second transitions in this frame window.
            File.WriteAllText(test,"{\"skin_tint\":\"#C8A080\",\"blendshapes\":{\"Joy\":0.3,\"JawRound\":0.4}}");
            yield return new WaitForEndOfFrame();
            var frames=new List<float>();float previous=Time.realtimeSinceStartup;
            for(int n=0;n<240;n++){
                if(n%45==0)face.ApplyFaceProfile(test);
                yield return new WaitForEndOfFrame();float now=Time.realtimeSinceStartup;float ms=(now-previous)*1000;previous=now;
                frames.Add(ms);report.maxFrameMs=Mathf.Max(report.maxFrameMs,ms);if(ms>33)report.over33++;
            }
            report.frames=frames.Count;report.rawFrames=frames.ToArray();Require(report.over33==0,"Hot refresh frame exceeded 33ms");
            // Capture the real portrait profile at 4K after the deterministic tests.
            face.applyProfileExpressions=false;face.ApplyFaceProfile(profile);yield return new WaitForSecondsRealtime(.32f);
            var camera=Camera.main;var rt=RenderTexture.GetTemporary(3840,2160,24);var old=RenderTexture.active;
            camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
            var image=new Texture2D(3840,2160,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,3840,2160),0,0);image.Apply();
            File.WriteAllBytes(Path.Combine(Dir,"profile-applied.png"),image.EncodeToPNG());Destroy(image);camera.targetTexture=null;RenderTexture.active=old;RenderTexture.ReleaseTemporary(rt);
            // Open-eye closeup verifies the replacement atlas visually rather than hiding it under Joy.
            File.WriteAllText(test,"{\"skin_tint\":\"#EBC4B6\",\"blendshapes\":{\"Joy\":0}}");
            face.ApplyFaceProfile(profile);yield return new WaitForSecondsRealtime(.32f);
            var oldPosition=camera.transform.position;var oldRotation=camera.transform.rotation;
            var head=face.Animator.GetBoneTransform(HumanBodyBones.Head).position;
            camera.transform.position=head+new Vector3(0,.03f,.65f);camera.transform.LookAt(head);
            rt=RenderTexture.GetTemporary(3840,2160,24);old=RenderTexture.active;camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
            image=new Texture2D(3840,2160,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,3840,2160),0,0);image.Apply();
            File.WriteAllBytes(Path.Combine(Dir,"feature-open.png"),image.EncodeToPNG());Destroy(image);camera.targetTexture=null;RenderTexture.active=old;RenderTexture.ReleaseTemporary(rt);
            camera.transform.SetPositionAndRotation(oldPosition,oldRotation);
            // Removing the component releases the current replacement and restores original materials/shape.
            var lastTexture=face.LoadedTexture;
            Destroy(face);yield return null;yield return new WaitForEndOfFrame();
            report.restored=!lastTexture&&Mathf.Abs(renderer.GetBlendShapeWeight(index))<.01f;Require(report.restored,"Owned texture/shape not restored on removal");
            renderer.sharedMesh=original;Destroy(mesh);
        }
    }
}
