using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UniJSON;
using UniVRM10;

namespace LocalHuman
{
    // VRM10 evaluates in LateUpdate(11000). Submit expressions in Update,
    // then write independent identity shapes/materials after its expression merger.
    [DefaultExecutionOrder(12000)]
    [DisallowMultipleComponent]
    public sealed class VRMFaceController : MonoBehaviour
    {
        // Suspend cached avatars without discarding identity and palette.
        public bool PreserveOnDisable {get;set;}

        [Serializable] public sealed class ShapeMapping { public string profileKey; public string shapeName; }
        [Tooltip("Relative paths resolve from the project/deployment working directory.")]
        public string testJsonPath = "artifacts/validation/face-stage2/ExportedFaceData/face_params.json";
        public bool enableFKey = true;
        [Tooltip("Opt in to persistent emotions from profile JSON. Photos describe identity; Joy may be a closed-eye smile on the target asset.")]
        public bool applyProfileExpressions = false;
        [Range(.05f, 1f)] public float transitionSeconds = .25f;
        [Range(0f, 1f)] public float studioExposure = 1f;
        public ShapeMapping[] shapeMappings = new ShapeMapping[0];
        [Tooltip("Optional overrides. Empty lists use conservative name matching.")]
        public Material[] skinMaterialOverrides = new Material[0];
        public Material[] featureMaterialOverrides = new Material[0];
        [Tooltip("For Stage 2's two-iris atlas, use one iris tile on shared/mirrored eye UVs. Disable for an asset with a matching dual-eye UV atlas.")]
        public bool useSingleIrisTile = true;
        [Tooltip("Disable for authored eye atlases whose UVs do not match the photo iris tiles.")]
        public bool applyFeatureTexture = true;
        [Tooltip("Disable for merged skin/clothing/hair atlases: preserve authored colors while retaining expression controls.")]
        public bool applyProfilePalette = true;
        public Vrm10Instance Avatar { get; private set; }
        public Animator Animator { get; private set; }
        public SkinnedMeshRenderer[] Renderers { get; private set; }
        public string LastError { get; private set; }
        public string[] UnmatchedControls { get; private set; } = new string[0];
        public bool IsTransitioning { get; private set; }
        public int AppliedProfiles { get; private set; }
        public int SkinMaterialCount => skins.Count;
        public int FeatureMaterialCount => features.Count;
        public Texture2D LoadedTexture => loadedTexture;
        public float LastTransitionDuration { get; private set; }
        sealed class Shape { public SkinnedMeshRenderer renderer; public int index; public float original, start, current, target; }
        sealed class ColorState { public Material material; public string property; public Color original, start, current, target; }
        sealed class TextureState { public Material material; public string property; public Texture original; public Vector2 originalScale, originalOffset, scale, offset; }
        sealed class Expression { public ExpressionKey key; public float original, start, current, target; }
        readonly List<Shape> shapes = new List<Shape>();
        readonly List<ColorState> colors = new List<ColorState>();
        readonly List<TextureState> textures = new List<TextureState>();
        readonly List<Expression> expressions = new List<Expression>();
        readonly HashSet<Material> skins = new HashSet<Material>(), features = new HashSet<Material>();
        FaceMorphController materialSync;
        Texture2D loadedTexture;
        float started, duration;
        bool initialized, hasProfile;

        void Awake() { Initialize(); }
        void Initialize()
        {
            if (initialized) return;
            Avatar = GetComponent<Vrm10Instance>(); Animator = GetComponent<Animator>();
            Renderers = GetComponentsInChildren<SkinnedMeshRenderer>(true);
            if (!Avatar || !Animator) throw new InvalidOperationException("Attach VRMFaceController to the loaded VRM10 root with Animator");
            // Imported GLTF materials are per-instance, owned by RuntimeGltfInstance.
            // Do not clone them: native expression material bindings refer to these objects.
            foreach (var r in Renderers) foreach (var m in r.sharedMaterials) {
                if (!m) continue;
                string name = m.name.ToLowerInvariant();
                bool excluded = ContainsAny(name, "wear", "cloth", "hair", "lash", "mastuge", "brow", "eye", "teeth", "mouth", "robo", "body_nm");
                if (skinMaterialOverrides.Length > 0 ? Array.IndexOf(skinMaterialOverrides, m) >= 0 :
                    !excluded && ContainsAny(name, "skin", "face", "body", "neck")) skins.Add(m);
                if (featureMaterialOverrides.Length > 0 ? Array.IndexOf(featureMaterialOverrides, m) >= 0 :
                    ContainsAny(name, "iris", "pupil") || (name.Contains("eye") && !ContainsAny(name, "white", "lash", "brow", "trans"))) features.Add(m);
            }
            foreach (var m in skins) foreach (var property in new[] { "_Color", "_BaseColor", "_ShadeColor", "_1st_ShadeColor", "_2nd_ShadeColor" }) if (m.HasProperty(property)) {
                Color c = m.GetColor(property); colors.Add(new ColorState { material=m, property=property, original=c, current=c });
            }
            foreach (var m in features) foreach (var property in new[] { "_MainTex", "_BaseMap" }) if (m.HasProperty(property))
                textures.Add(new TextureState { material=m, property=property, original=m.GetTexture(property), originalScale=m.GetTextureScale(property), originalOffset=m.GetTextureOffset(property), scale=m.GetTextureScale(property), offset=m.GetTextureOffset(property) });
            materialSync=GetComponent<FaceMorphController>();
            if(!materialSync)materialSync=gameObject.AddComponent<FaceMorphController>();
            initialized = true;
        }
        static bool ContainsAny(string name, params string[] words) { foreach (var word in words) if (name.Contains(word)) return true; return false; }
        static bool TryPreset(string name, out ExpressionPreset preset)
        {
            switch (name.ToLowerInvariant()) {
                case "joy": case "happy": preset=ExpressionPreset.happy; return true;
                case "sorrow": case "sad": preset=ExpressionPreset.sad; return true;
                case "angry": preset=ExpressionPreset.angry; return true;
                case "fun": case "relaxed": preset=ExpressionPreset.relaxed; return true;
                case "surprised": preset=ExpressionPreset.surprised; return true;
                case "neutral": preset=ExpressionPreset.neutral; return true;
                default: preset=ExpressionPreset.custom; return false;
            }
        }
        bool Reserved(SkinnedMeshRenderer renderer, int index)
        {
            foreach (var clip in Avatar.Vrm.Expression.Clips) foreach (var binding in clip.Clip.MorphTargetBindings) {
                var node = string.IsNullOrEmpty(binding.RelativePath) ? transform : transform.Find(binding.RelativePath);
                if (node && node.GetComponent<SkinnedMeshRenderer>() == renderer && binding.Index == index) return true;
            }
            return false;
        }
        // Call on Unity's main thread. A rejected profile leaves the previous targets intact.
        public void ApplyFaceProfile(string jsonPath)
        {
            Texture2D candidate = null;
            try {
                Initialize();
                string fullPath = Path.GetFullPath(jsonPath);
                var info = new FileInfo(fullPath);
                if (!info.Exists || info.Length > 4*1024*1024) throw new IOException("Profile missing or exceeds 4 MiB");
                var json = File.ReadAllText(fullPath).ParseAsJson();
                if (!json.IsMap()) throw new FormatException("Profile must be a JSON object");
                if (!json.TryGet("skin_tint", out var skin) || !ColorUtility.TryParseHtmlString(skin.GetString(), out var tint))
                    throw new FormatException("skin_tint must be a valid HTML color");
                if (!json.TryGet("blendshapes", out var weights) || !weights.IsMap()) throw new FormatException("blendshapes must be an object");
                var values = new Dictionary<string,float>(StringComparer.OrdinalIgnoreCase);
                foreach (var item in weights.ObjectItems()) {
                    if (item.Value.Value.ValueType != ValueNodeType.Integer && item.Value.Value.ValueType != ValueNodeType.Number)
                        throw new FormatException("BlendShape weights must be numbers");
                    float value = item.Value.GetSingle();
                    if (float.IsNaN(value) || float.IsInfinity(value) || value < 0 || value > 1) throw new FormatException("BlendShape weights must be finite and in [0,1]");
                    values.Add(item.Key.GetString(), value);
                }
                bool hasExpression=json.TryGet("expression",out var photoExpression);
                Vector4 photo=Vector4.zero;
                if(hasExpression) {
                    if(!photoExpression.IsMap())throw new FormatException("expression must be an object");
                    string[] names={"smile_degree","eye_smile_left","eye_smile_right","mouth_open"};
                    for(int i=0;i<4;i++) {
                        if(!photoExpression.TryGet(names[i],out var v)||(v.Value.ValueType!=ValueNodeType.Integer&&v.Value.ValueType!=ValueNodeType.Number))throw new FormatException("Missing numeric expression "+names[i]);
                        float f=v.GetSingle();if(float.IsNaN(f)||float.IsInfinity(f)||f<0||f>1)throw new FormatException("expression weights must be finite in [0,1]");photo[i]=f;
                    }
                }
                bool toonSkin=json.TryGet("skin",out var palette) && palette.Value.ValueType!=ValueNodeType.Null;
                Color baseColor=tint, shadeColor=tint, shade2Color=tint;
                if(toonSkin) {
                    if(!palette.IsMap())throw new FormatException("skin must be an object");
                    baseColor=ReadRgb(palette,"base_color");shadeColor=ReadRgb(palette,"shade_color");shade2Color=ReadRgb(palette,"shade2_color");
                }
                bool hasHair=json.TryGet("hair",out var hair) && hair.Value.ValueType!=ValueNodeType.Null;
                Color hairBase=Color.white,hairShade=Color.white;
                if(hasHair) {
                    if(!hair.IsMap())throw new FormatException("hair must be an object");
                    hairBase=ReadRgb(hair,"base_color");hairShade=ReadRgb(hair,"shade_color");
                }
                // Missing optional texture keeps the current texture. Invalid image rejects the profile.
                if (json.TryGet("texture_path", out var tex) && tex.Value.ValueType != ValueNodeType.Null) {
                    string path = tex.GetString();
                    if (!string.IsNullOrWhiteSpace(path)) {
                        if (!Path.IsPathRooted(path)) path=Path.Combine(Path.GetDirectoryName(fullPath), path);
                        if (File.Exists(path)) {
                            if (new FileInfo(path).Length > 16*1024*1024) throw new IOException("Texture exceeds 16 MiB");
                            // Inspect dimensions before allocating a decoded image.
                            byte[] bytes = File.ReadAllBytes(path);
                            if (!SafePng(bytes)) throw new FormatException("Texture must be a PNG <=4096 per side and <=16 megapixels");
                            candidate = new Texture2D(2,2,TextureFormat.RGBA32,false);
                            if (!candidate.LoadImage(bytes, false)) throw new FormatException("Cannot decode texture");
                            candidate.name="FaceProfileFeatureTexture";candidate.wrapMode=TextureWrapMode.Clamp;
                        }
                    }
                }
                var expressionTargets = new Dictionary<ExpressionKey,float>();
                var shapeTargets = new Dictionary<Shape,float>();
                var unmatched = new List<string>();
                foreach (var pair in values) {
                    if (TryPreset(pair.Key, out var preset)) {
                        if (!applyProfileExpressions || hasExpression) continue;
                        var key = new ExpressionKey(preset);
                        if (Avatar.Runtime.Expression.ExpressionKeys.Contains(key)) { expressionTargets[key]=pair.Value;continue; }
                        unmatched.Add(pair.Key);continue;
                    }
                    string target = pair.Key;
                    foreach (var mapping in shapeMappings) if (mapping != null && string.Equals(mapping.profileKey,pair.Key,StringComparison.OrdinalIgnoreCase)) target=mapping.shapeName;
                    bool matched=false;
                    foreach (var r in Renderers) {
                        if (!r.sharedMesh) continue;
                        for (int i=0;i<r.sharedMesh.blendShapeCount;i++) {
                            if (!string.Equals(r.sharedMesh.GetBlendShapeName(i),target,StringComparison.OrdinalIgnoreCase) || Reserved(r,i)) continue;
                            var shape=shapes.Find(s=>s.renderer==r && s.index==i);
                            if (shape==null) { float v=r.GetBlendShapeWeight(i);shape=new Shape{renderer=r,index=i,original=v,current=v};shapes.Add(shape); }
                            shapeTargets[shape]=pair.Value*100;matched=true;
                        }
                    }
                    if (!matched) unmatched.Add(pair.Key);
                }
                foreach (var pair in expressionTargets) if (!expressions.Exists(e=>e.key.Equals(pair.Key))) {
                    float v=Avatar.Runtime.Expression.GetWeight(pair.Key);
                    expressions.Add(new Expression{key=pair.Key,original=v,current=v});
                }
                foreach (var e in expressions) { e.start=e.current;e.target=expressionTargets.TryGetValue(e.key,out var v)?v:e.original; }
                foreach (var s in shapes) { s.start=s.current;s.target=shapeTargets.TryGetValue(s,out var v)?v:s.original; }
                materialSync.enabled=true;
                if(applyProfilePalette)materialSync.ApplyPalette(toonSkin,hasHair,hairBase,hairShade,baseColor*studioExposure,shadeColor*studioExposure,transitionSeconds);
                if(hasExpression)materialSync.ApplyExpression(photo);
                else materialSync.ClearExpression();
                foreach (var c in colors) {
                    Color color=c.property=="_2nd_ShadeColor"?shade2Color:
                        c.property=="_ShadeColor"||c.property=="_1st_ShadeColor"?shadeColor:baseColor;
                    c.start=c.current;c.target=applyProfilePalette?new Color(color.r*studioExposure,color.g*studioExposure,color.b*studioExposure,c.original.a):c.original;
                }
                if (candidate) {
                    bool atlas = useSingleIrisTile && candidate.width==256 && candidate.height==128 && json.TryGet("pupil_layout",out var layout) && layout.GetString().StartsWith("256x128",StringComparison.Ordinal);
                    foreach (var t in textures) if (applyFeatureTexture) {
                        t.scale=atlas?new Vector2(.5f,1):t.originalScale;t.offset=atlas?Vector2.zero:t.originalOffset;
                        t.material.SetTexture(t.property,candidate);t.material.SetTextureScale(t.property,t.scale);t.material.SetTextureOffset(t.property,t.offset);
                    }
                    var old=loadedTexture;loadedTexture=candidate;candidate=null;if (old) Destroy(old);
                }
                UnmatchedControls=unmatched.ToArray();LastError=null;AppliedProfiles++;hasProfile=true;
                started=Time.unscaledTime;duration=Mathf.Max(.01f,transitionSeconds);IsTransitioning=true;
                Debug.Log("VRM_FACE_APPLIED unmatched="+string.Join(",",UnmatchedControls));
            } catch (Exception e) { if(candidate)Destroy(candidate);LastError=e.Message;Debug.Log("VRM_FACE_REJECTED "+LastError); }
        }
        static Color ReadRgb(JsonNode json,string key)
        {
            if(!json.TryGet(key,out var array)||!array.IsArray())throw new FormatException(key+" must be an RGB array");
            var values=new List<float>();
            foreach(var item in array.ArrayItems()) {
                if(item.Value.ValueType!=ValueNodeType.Integer&&item.Value.ValueType!=ValueNodeType.Number)throw new FormatException(key+" must contain numbers");
                float v=item.GetSingle();if(float.IsNaN(v)||float.IsInfinity(v)||v<0||v>1)throw new FormatException(key+" must be finite sRGB in [0,1]");values.Add(v);
            }
            if(values.Count!=3)throw new FormatException(key+" must have 3 channels");
            return new Color(values[0],values[1],values[2],1);
        }
        static bool SafePng(byte[] data)
        {
            if(data.Length<33 || data[0]!=137 || data[1]!=80 || data[2]!=78 || data[3]!=71 || data[4]!=13 || data[5]!=10 || data[6]!=26 || data[7]!=10 || data[12]!=73 || data[13]!=72 || data[14]!=68 || data[15]!=82)return false;
            uint w=((uint)data[16]<<24)|((uint)data[17]<<16)|((uint)data[18]<<8)|data[19];
            uint h=((uint)data[20]<<24)|((uint)data[21]<<16)|((uint)data[22]<<8)|data[23];
            return w>0 && h>0 && w<=4096 && h<=4096 && (ulong)w*h<=16_000_000;
        }
        void Update()
        {
            if(enableFKey && Input.GetKeyDown(KeyCode.F))ApplyFaceProfile(testJsonPath);
            if(!hasProfile)return;
            float t=Mathf.Clamp01((Time.unscaledTime-started)/duration);
            // Fixed start/end lerp reaches the target in .25 s; it is not asymptotic.
            t=t*t*(3-2*t);
            foreach(var e in expressions){e.current=Mathf.Lerp(e.start,e.target,t);Avatar.Runtime.Expression.SetWeight(e.key,e.current);}
            foreach(var s in shapes)s.current=Mathf.Lerp(s.start,s.target,t);
            foreach(var c in colors)c.current=Color.Lerp(c.start,c.target,t);
            if(IsTransitioning && t>=1){IsTransitioning=false;LastTransitionDuration=Time.unscaledTime-started;}
        }
        void LateUpdate()
        {
            if(!hasProfile)return;
            foreach(var s in shapes)if(s.renderer)s.renderer.SetBlendShapeWeight(s.index,s.current);
            foreach(var c in colors)if(c.material)c.material.SetColor(c.property,c.current);
            if(applyFeatureTexture&&loadedTexture)foreach(var t in textures)if(t.material){t.material.SetTexture(t.property,loadedTexture);t.material.SetTextureScale(t.property,t.scale);t.material.SetTextureOffset(t.property,t.offset);}
        }
        [ContextMenu("Reload Face Profile (Play Mode)")]
        public void ReloadTestProfile(){if(Application.isPlaying)ApplyFaceProfile(testJsonPath);}
        void OnDisable()
        {
            if(!initialized||PreserveOnDisable)return;
            foreach(var e in expressions)if(Avatar)Avatar.Runtime.Expression.SetWeight(e.key,e.original);
            foreach(var s in shapes)if(s.renderer)s.renderer.SetBlendShapeWeight(s.index,s.original);
            foreach(var c in colors)if(c.material)c.material.SetColor(c.property,c.original);
            foreach(var t in textures)if(t.material){t.material.SetTexture(t.property,t.original);t.material.SetTextureScale(t.property,t.originalScale);t.material.SetTextureOffset(t.property,t.originalOffset);}
            if(materialSync)materialSync.enabled=false;
            hasProfile=false;IsTransitioning=false;
        }
        void OnDestroy()
        {
            foreach(var t in textures)if(t.material){t.material.SetTexture(t.property,t.original);t.material.SetTextureScale(t.property,t.originalScale);t.material.SetTextureOffset(t.property,t.originalOffset);}
            if(loadedTexture)Destroy(loadedTexture);
            if(materialSync)Destroy(materialSync);
        }
    }
}
