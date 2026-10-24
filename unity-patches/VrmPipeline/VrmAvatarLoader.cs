using System;
using System.IO;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UniGLTF;
using UniVRM10;
namespace LocalHuman
{
    public sealed class VrmAvatarLoader:MonoBehaviour
    {
        public RuntimeAnimatorController idleController;
        public RuntimeAnimatorController maleIdleController;
        public bool Ready{get;private set;}
        public bool IsSwitching{get;private set;}
        public bool CacheReady{get;private set;}
        public int ImportCount{get;private set;}
        readonly Dictionary<string,Vrm10Instance> cache=new Dictionary<string,Vrm10Instance>();
        readonly Dictionary<string,string> profiles=new Dictionary<string,string>();
        readonly Dictionary<string,DateTime> profileVersions=new Dictionary<string,DateTime>();
        public string CurrentAvatar{get;private set;}
        public string CurrentProfile{get;private set;}
        public string Attribution => "優希 / Yūki · jji-factory";
        public Vrm10Instance Instance{get;private set;}
        public string Error{get;private set;}
        bool disposed;
        [Serializable] sealed class ProfileIdentity { public string avatar_id; }
        async void Start()
        {
            var args=Environment.GetCommandLineArgs();
            int profile=Array.IndexOf(args,"-face-profile");
            // A legacy -avatar woman argument cannot restore the removed character.
            if(await SwitchAvatarAsync("man",profile>=0&&profile+1<args.Length?args[profile+1]:null))
                CacheReady=true;
        }
        public async void SelectAvatar(string id){await SwitchAvatarAsync(id);}
        public string ProfilePath(string id)
        {
            var local=Path.GetFullPath(Path.Combine(Application.dataPath,"../../artifacts/validation/face-stage2",id,"face_params.json"));
            return File.Exists(local)?local:Path.Combine(Application.streamingAssetsPath,"Avatars/Profiles",id,"face_params.json");
        }
        public bool ReloadProfile()
        {
            if(!Ready||IsSwitching)return false;
            try { ValidateProfile(CurrentProfile,CurrentAvatar);Instance.GetComponent<VRMFaceController>().ApplyFaceProfile(CurrentProfile);
                Error=Instance.GetComponent<VRMFaceController>().LastError;
                if(Error==null){profiles[CurrentAvatar]=CurrentProfile;profileVersions[CurrentAvatar]=File.GetLastWriteTimeUtc(CurrentProfile);}
                return Error==null;
            }catch(Exception e){Error=e.Message;return false;}
        }
        static void ValidateProfile(string path,string id)
        {
            if(!File.Exists(path))throw new FileNotFoundException("Face profile not found",path);
            var identity=JsonUtility.FromJson<ProfileIdentity>(File.ReadAllText(path));
            if(!string.IsNullOrEmpty(identity.avatar_id)&&identity.avatar_id!=id)throw new Exception("Face profile avatar_id mismatch: "+identity.avatar_id+" / "+id);
        }
        async Task<Vrm10Instance> PrepareAvatarAsync(string id,string profilePath=null)
        {
            if(cache.TryGetValue(id,out var cached)&&cached)return cached;
            Vrm10Instance candidate=null;
            try {
                string profile=profilePath??ProfilePath(id);
                ValidateProfile(profile,id);
                string path=Path.Combine(Application.streamingAssetsPath,"Avatars","male.vrm");
                candidate=await Vrm10.LoadPathAsync(path,true,ControlRigGenerationOption.None,false,
                    materialGenerator:new UrpVrm10MaterialDescriptorGenerator());
                if(disposed)throw new OperationCanceledException("Avatar loader destroyed");
                ImportCount++;
                var model=candidate.transform;model.SetParent(transform,false);model.name="VrmAvatar_"+id;
                var animator=candidate.GetComponent<Animator>();
                if(!animator||!animator.isHuman||!animator.avatar.isValid)throw new Exception("VRM must have valid Humanoid Avatar");
                animator.keepAnimatorStateOnDisable=true;animator.applyRootMotion=false;animator.runtimeAnimatorController=id=="man"&&maleIdleController?maleIdleController:idleController;animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;
                animator.Rebind();animator.Play("Stable Idle",0,0);animator.Update(.01f);
                var bounds=new Bounds();bool first=true;var adjusted=new HashSet<Material>();
                foreach(var r in candidate.GetComponentsInChildren<SkinnedMeshRenderer>()){
                    var mesh=new Mesh();r.BakeMesh(mesh);
                    foreach(var v in mesh.vertices){var point=r.transform.TransformPoint(v);if(first){bounds=new Bounds(point,Vector3.zero);first=false;}else bounds.Encapsulate(point);}Destroy(mesh);
                    r.updateWhenOffscreen=true;
                    foreach(var m in r.sharedMaterials){
                        if(!m||!m.shader||!m.shader.isSupported||m.shader.name.Contains("InternalError"))throw new Exception("Unsupported VRM material");
                        if(!adjusted.Add(m))continue;
                        foreach(var property in new[]{"_Color","_ShadeColor"})if(m.HasProperty(property)){
                            var color=m.GetColor(property);m.SetColor(property,new Color(color.r*.68f,color.g*.68f,color.b*.68f,color.a));
                        }
                    }
                }
                if(first||bounds.size.y<=0)throw new Exception("Empty VRM mesh bounds");
                float scale=.9f/bounds.size.y;model.localScale=Vector3.one*scale;
                model.localPosition=new Vector3(-bounds.center.x*scale,-.57181f-bounds.min.y*scale,-bounds.center.z*scale);
                // Backpack/robot arm bounds are asymmetric: center the stance on the disc.
                var stance=(animator.GetBoneTransform(HumanBodyBones.LeftFoot).position+animator.GetBoneTransform(HumanBodyBones.RightFoot).position)*.5f;
                model.position-=new Vector3(stance.x,0,stance.z);
                model.gameObject.AddComponent<VrmGrounding>().Initialize(animator,id=="man");
                var capsule=model.gameObject.AddComponent<CapsuleCollider>();capsule.center=new Vector3(0,bounds.center.y,0);capsule.height=bounds.size.y;capsule.radius=.12f;
                var body=model.gameObject.AddComponent<Rigidbody>();body.isKinematic=true;body.useGravity=false;
                var face=model.gameObject.AddComponent<VRMFaceController>();
                // Yuki's merged authored atlas must retain its original eyes and colors.
                face.applyFeatureTexture=id!="man";
                face.applyProfilePalette=id!="man";
                face.PreserveOnDisable=true;face.GetComponent<FaceMorphController>().PreserveOnDisable=true;face.testJsonPath=profile;face.ApplyFaceProfile(profile);
                if(face.LastError!=null)throw new Exception("Face profile rejected: "+face.LastError);
                candidate.GetComponent<RuntimeGltfInstance>().ShowMeshes();
                var caller=new RuntimeOnlyAwaitCaller();
                // Hidden meshes do not warm GPU resources; render behind the loading overlay.
                for(int n=0;n<16;n++){await caller.NextFrame();if(disposed)throw new OperationCanceledException();}
                candidate.gameObject.SetActive(false);
                cache[id]=candidate;profiles[id]=profile;profileVersions[id]=File.GetLastWriteTimeUtc(profile);
                var result=candidate;candidate=null;return result;
            } finally {if(candidate)Destroy(candidate.gameObject);}
        }
        public async Task<bool> SwitchAvatarAsync(string id,string profilePath=null)
        {
            if(IsSwitching||disposed)return false;
            try {
                if(id!="man")throw new ArgumentException("Only the male avatar is available");
                IsSwitching=true;Error=null;
                string profile=profilePath??ProfilePath(id);
                ValidateProfile(profile,id);
                var candidate=await PrepareAvatarAsync(id,profile);
                if(disposed)throw new OperationCanceledException("Avatar loader destroyed");
                var face=candidate.GetComponent<VRMFaceController>();
                if(profiles[id]!=profile||profileVersions[id]!=File.GetLastWriteTimeUtc(profile)) {
                    face.testJsonPath=profile;face.ApplyFaceProfile(profile);
                    if(face.LastError!=null)throw new Exception("Face profile rejected: "+face.LastError);
                    profiles[id]=profile;profileVersions[id]=File.GetLastWriteTimeUtc(profile);
                }
                var previous=Instance;
                candidate.gameObject.SetActive(true);
                GetComponent<LocalAvatarLipSync>().BindAvatar(candidate);
                GetComponent<AvatarInteractiveMotion>().BindAvatar(candidate);
                Instance=candidate;CurrentAvatar=id;CurrentProfile=profile;
                if(previous&&previous!=candidate)previous.gameObject.SetActive(false);
                Ready=true;
                Debug.Log("VRM_READY validHumanoid=true source="+id+" UniVRM=0.128.1 profile="+profile+" imports="+ImportCount);
                return true;
            }catch(Exception e){Error=e.Message;Debug.Log("VRM_SWITCH_REJECTED "+Error);return false;}
            finally{IsSwitching=false;}
        }
        void OnDestroy(){disposed=true;foreach(var instance in cache.Values)if(instance)Destroy(instance.gameObject);cache.Clear();}
    }
}
