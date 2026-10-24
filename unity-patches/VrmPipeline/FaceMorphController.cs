using System;
using System.Collections.Generic;
using UnityEngine;
using UniVRM10;

namespace LocalHuman
{
    // Material companion to VRMFaceController. Per-slot blocks preserve native VRM bindings.
    [DefaultExecutionOrder(12010)]
    public sealed class FaceMorphController : MonoBehaviour
    {
        // Suspend cached avatars without discarding identity and palette.
        public bool PreserveOnDisable {get;set;}

        // Explicit photo expressions are separate from legacy identity/Joy controls.
        // Prefer artist-authored regional shapes: Alicia happy includes fully shut eyes.
        sealed class ExpressionShape {
            public SkinnedMeshRenderer renderer; public int index; public int channel; public float gain; public bool native;
        }
        readonly List<ExpressionShape> expressionShapes = new List<ExpressionShape>();
        readonly HashSet<(SkinnedMeshRenderer,int)> appliedShapes=new HashSet<(SkinnedMeshRenderer,int)>();
        Vrm10Instance expressionAvatar;
        Vector4 expressionStart, expressionTarget;
        public Vector4 CurrentExpression { get; private set; }
        float expressionStarted;
        bool expressionActive, regionalSmile;
        public float InteractionSmile {get;set;}
        public float InteractionBrow {get;set;}
        public float InteractionEyeSmile {get;set;}
        public float PhotoMouthOpen => expressionActive ? CurrentExpression.w * .65f * CurrentExpression.x : 0;
        public float ExpressionAddition(SkinnedMeshRenderer renderer, int index) {
            float result=0;
            foreach(var shape in expressionShapes) if(shape.renderer==renderer&&shape.index==index)
                result+=(shape.channel==6?InteractionEyeSmile:shape.channel==5?InteractionBrow:shape.channel==4?(CurrentExpression.y+CurrentExpression.z)*.5f:CurrentExpression[shape.channel])*shape.gain*100;
            return result;
        }
        public void ClearExpression() {
            foreach(var shape in expressionShapes)if(shape.renderer&&!shape.native)shape.renderer.SetBlendShapeWeight(shape.index,0);
            expressionActive=false;CurrentExpression=Vector4.zero;
        }
        void DiscoverExpressions() {
            if(!expressionAvatar) {
                expressionAvatar=GetComponent<Vrm10Instance>();
                foreach(var r in GetComponentsInChildren<SkinnedMeshRenderer>(true)) {
                    if(!r.sharedMesh)continue;
                    for(int i=0;i<r.sharedMesh.blendShapeCount;i++) {
                        string n=r.sharedMesh.GetBlendShapeName(i).ToLowerInvariant();
                        int channel=-1;float gain=1;
                        if(n=="fcl_mth_smile"||n=="fcl_mth_joy"||n.EndsWith("mouth_smile")){channel=0;gain=.75f;regionalSmile=true;}
                        else if(n.EndsWith("mouth_ornerup")||n.EndsWith("mouth_cornerup")){channel=0;gain=.25f;}
                        else if(n.Contains("eye")&&n.Contains("smile")&&!n.Contains("brow")&&!n.Contains("blow")) {
                            // Keep the iris visible. Full closure remains owned by natural blink.
                            channel=n.EndsWith("_r")||n.EndsWith("right")?2:n.EndsWith("_l")||n.EndsWith("left")?1:4;gain=.22f;
                        }
                        else if(n.EndsWith("eyeblow_smile")||n.EndsWith("eyebrow_smile")){channel=0;gain=.3f;}
                        else if((n.Contains("brow")||n.Contains("blow")||n.Contains("brw"))&&(n.Contains("up")||n.Contains("surprised"))) {channel=5;gain=.4f;}
                        if(channel>=0) {
                            bool bound=false;
                            foreach(var clip in expressionAvatar.Vrm.Expression.Clips)foreach(var binding in clip.Clip.MorphTargetBindings) {
                                var node=string.IsNullOrEmpty(binding.RelativePath)?transform:transform.Find(binding.RelativePath);
                                if(node&&node.GetComponent<SkinnedMeshRenderer>()==r&&binding.Index==i)bound=true;
                            }
                            expressionShapes.Add(new ExpressionShape{renderer=r,index=i,channel=channel,gain=gain,native=bound});
                            if(channel==0&&regionalSmile&&(n.Contains("mouth_smile")||n=="fcl_mth_joy"||n=="fcl_mth_smile"))
                                expressionShapes.Add(new ExpressionShape{renderer=r,index=i,channel=6,gain=.45f,native=bound});
                        }
                        // Use one combined eye shape, never combined Joy plus left/right Joy.
                        if(n=="fcl_eye_joy"||n.EndsWith("eye_smile")) {
                            bool bound=false;
                            foreach(var clip in expressionAvatar.Vrm.Expression.Clips)foreach(var binding in clip.Clip.MorphTargetBindings) {
                                var node=string.IsNullOrEmpty(binding.RelativePath)?transform:transform.Find(binding.RelativePath);
                                if(node&&node.GetComponent<SkinnedMeshRenderer>()==r&&binding.Index==i)bound=true;
                            }
                            expressionShapes.Add(new ExpressionShape{renderer=r,index=i,channel=6,gain=1,native=bound});
                        }
                    }
                }
            }
        }
        public void ApplyExpression(Vector4 value) {
            DiscoverExpressions();
            expressionStart=CurrentExpression;expressionTarget=value;
            expressionStarted=Time.unscaledTime;expressionActive=true;
        }
        void Update() {
            DiscoverExpressions();
            if(!expressionAvatar)return;
            float t=Mathf.Clamp01((Time.unscaledTime-expressionStarted)/.3f);
            CurrentExpression=expressionActive?Vector4.Lerp(expressionStart,expressionTarget,t*t*(3-2*t)):Vector4.zero;
            // VRM0 imports migrate Joy to VRM10 happy. Regional shapes avoid closed-eye Joy.
            expressionAvatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.happy),Mathf.Max(regionalSmile?0:CurrentExpression.x*.2f,InteractionSmile*.18f));
            var lip=GetComponentInParent<LocalAvatarLipSync>();
            if(!lip||!lip.enabled)expressionAvatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.aa),PhotoMouthOpen);
        }
        sealed class Slot {
            public Renderer renderer; public Material material; public int index;
            public MaterialPropertyBlock original, block;
            public bool hair, active;
            public Color startBase, startShade, currentBase, currentShade, targetBase, targetShade;
        }
        readonly List<Slot> slots = new List<Slot>();
        readonly Dictionary<(Texture, bool, bool), Texture2D> neutralTextures = new Dictionary<(Texture, bool, bool), Texture2D>();
        [Tooltip("Normalize the additive three-light MToon studio in linear space; keep profile RGB in sRGB.")]
        [Range(.25f,1f)] public float studioLightNormalization=.55f;
        public Color ShaderColor(Color srgb) {
            Color c=QualitySettings.activeColorSpace==ColorSpace.Linear?srgb.linear:srgb;
            return new Color(c.r*studioLightNormalization,c.g*studioLightNormalization,c.b*studioLightNormalization,srgb.a);
        }
        float started, duration;
        public int HairMaterialCount { get; private set; }
        public Color HairBaseColor { get; private set; }
        public Color HairShadeColor { get; private set; }
        void Awake()
        {
            foreach (var renderer in GetComponentsInChildren<Renderer>(true)) {
                var materials = renderer.sharedMaterials;
                for(int i=0;i<materials.Length;i++) {
                    var m=materials[i];if(!m)continue;
                    string name=m.name.ToLowerInvariant();
                    bool hair=name.Contains("hair")&&!name.Contains("wear")&&!name.Contains("accessor");
                    bool skin=!name.Contains("robo")&&!name.Contains("body_nm")&&!name.Contains("wear")&&(name.Contains("skin")||name.Contains("face")||name.Contains("body"))
                        &&!name.Contains("eye")&&!name.Contains("lash")&&!name.Contains("mastuge")&&!name.Contains("brow")&&!name.Contains("hair");
                    if(!hair&&!skin)continue;
                    var original=new MaterialPropertyBlock();renderer.GetPropertyBlock(original,i);
                    var block=new MaterialPropertyBlock();renderer.GetPropertyBlock(block,i);
                    Color b=m.HasProperty("_Color")?m.GetColor("_Color"):Color.white;
                    Color s=m.HasProperty("_ShadeColor")?m.GetColor("_ShadeColor"):b;
                    slots.Add(new Slot{renderer=renderer,material=m,index=i,hair=hair,original=original,block=block,currentBase=b,currentShade=s});
                    if(hair)HairMaterialCount++;
                }
            }
        }
        public void ApplyPalette(bool toonSkin, bool hasHair, Color hairBase, Color hairShade, Color skinBase, Color skinShade, float seconds)
        {
            foreach(var slot in slots) {
                if(slot.hair&&!hasHair)continue;
                // Neutralize authored yellow/peach albedo before applying the new palette.
                // Preserve alpha, UVs, normal maps and dark linework. No photo is projected onto VRM UVs.
                foreach(var property in new[]{"_MainTex","_BaseMap","_ShadeTex"}) if((slot.hair||toonSkin)&&slot.material.HasProperty(property)) {
                    var source=slot.material.GetTexture(property);
                    if(source)slot.block.SetTexture(property,NeutralTexture(source,slot.hair,slot.material.name=="Alicia_face"));
                }
                slot.active=true;
                slot.startBase=slot.currentBase;slot.startShade=slot.currentShade;
                slot.targetBase=slot.hair?hairBase:skinBase;slot.targetShade=slot.hair?hairShade:skinShade;
            }
            started=Time.unscaledTime;duration=Mathf.Max(.01f,seconds);
        }
        Texture2D NeutralTexture(Texture source,bool hair,bool aliciaBrows)
        {
            var key=(source,hair,aliciaBrows);if(neutralTextures.TryGetValue(key,out var cached))return cached;
            int w=Mathf.Min(source.width,2048),h=Mathf.Min(source.height,2048);
            var rt=RenderTexture.GetTemporary(w,h,0,RenderTextureFormat.ARGB32,RenderTextureReadWrite.sRGB);
            var previous=RenderTexture.active;
            var texture=new Texture2D(w,h,TextureFormat.RGBA32,false);
            try {
                Graphics.Blit(source,rt);RenderTexture.active=rt;
                texture.ReadPixels(new Rect(0,0,w,h),0,0);texture.Apply();
                var pixels=texture.GetPixels32();
                for(int i=0;i<pixels.Length;i++) {
                    Color c=pixels[i];Color.RGBToHSV(c,out var hue,out var saturation,out var value);
                    if(hair || (hue<.14f && saturation<.4f && value>.35f)) {
                        float v=hair?.75f+.25f*value:Mathf.Max(.72f,.2126f*c.r+.7152f*c.g+.0722f*c.b);
                        pixels[i]=new Color(v,v,v,c.a);
                    }
                    // Alicia's eyebrows occupy a separate gold tile in her face atlas.
                    // Skin tint otherwise makes the filled brow almost disappear. Keep
                    // this asset-specific tile dark; never darken the surrounding face.
                    float u=(i%w+.5f)/w, vAtlas=(i/w+.5f)/h;
                    if(aliciaBrows&&u>=.84f&&vAtlas>=.744f&&vAtlas<=.875f) {
                        float ink=.12f+.10f*value;
                        pixels[i]=new Color(ink,ink,ink,c.a);
                    }
                }
                texture.SetPixels32(pixels);texture.Apply(false,true);
                texture.name="FaceProfileNeutral_"+source.name;texture.wrapMode=source.wrapMode;texture.filterMode=source.filterMode;
                neutralTextures[key]=texture;return texture;
            } catch { Destroy(texture);throw; }
            finally { RenderTexture.active=previous;RenderTexture.ReleaseTemporary(rt); }
        }
        void LateUpdate()
        {
            appliedShapes.Clear();
            foreach(var shape in expressionShapes)if(shape.renderer) {
                if(!appliedShapes.Add((shape.renderer,shape.index)))continue;
                // Native VRM merger resets these weights every frame before this LateUpdate.
                // Sum once, never feed last frame's corrected value back to the native inputs.
                float addition=ExpressionAddition(shape.renderer,shape.index);
                shape.renderer.SetBlendShapeWeight(shape.index,Mathf.Clamp((shape.native?shape.renderer.GetBlendShapeWeight(shape.index):0)+addition,0,100));
            }
            float t=Mathf.Clamp01((Time.unscaledTime-started)/Mathf.Max(.01f,duration));t=t*t*(3-2*t);
            foreach(var s in slots)if(s.active&&s.renderer) {
                {
                    s.currentBase=Color.Lerp(s.startBase,s.targetBase,t);s.currentShade=Color.Lerp(s.startShade,s.targetShade,t);
                    // MToon10 uses _Color/_ShadeColor; URP Lit/other toon shaders use the aliases.
                    foreach(var prop in new[]{"_Color","_BaseColor"})if(s.material.HasProperty(prop))s.block.SetVector(prop,ShaderColor(s.currentBase));
                    foreach(var prop in new[]{"_ShadeColor","_1st_ShadeColor"})if(s.material.HasProperty(prop))s.block.SetVector(prop,ShaderColor(s.currentShade));
                    if(s.hair){HairBaseColor=s.currentBase;HairShadeColor=s.currentShade;}
                }
                s.renderer.SetPropertyBlock(s.block,s.index);
            }
        }
        void OnDisable() {
            InteractionEyeSmile=InteractionSmile=InteractionBrow=0;
            if(PreserveOnDisable)return;
            if(expressionActive&&expressionAvatar) {
                expressionAvatar.Runtime.Expression.SetWeight(new ExpressionKey(ExpressionPreset.happy),0);
                foreach(var shape in expressionShapes)if(shape.renderer)shape.renderer.SetBlendShapeWeight(shape.index,0);
            }
            ClearExpression();
            foreach(var s in slots)if(s.active&&s.renderer){s.renderer.SetPropertyBlock(s.original,s.index);s.active=false;}
        }
        void OnDestroy() { foreach(var texture in neutralTextures.Values)if(texture)Destroy(texture); }
    }
}
