Shader "LocalHuman/StudioWhite"
{
 Properties { [MainColor] _BaseColor("White",Color)=(1,1,1,1) _Metallic("Metallic",Float)=0 _Smoothness("Smoothness",Float)=0 }
 SubShader
 {
  Tags {"RenderPipeline"="UniversalPipeline" "RenderType"="Opaque"}
  Pass
  {
   Tags {"LightMode"="UniversalForward"}
   HLSLPROGRAM
   #pragma vertex Vert
   #pragma fragment Frag
   #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
   #pragma multi_compile_fragment _ _SHADOWS_SOFT
   #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
   #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
   CBUFFER_START(UnityPerMaterial)
   half4 _BaseColor;float _Metallic,_Smoothness;
   CBUFFER_END
   struct A {float4 positionOS:POSITION;};struct V {float4 positionCS:SV_POSITION;float3 world:TEXCOORD0;};
   V Vert(A a){V o;o.world=TransformObjectToWorld(a.positionOS.xyz);o.positionCS=TransformWorldToHClip(o.world);return o;}
   half4 Frag(V i):SV_Target
   {
    // White studio receives the avatar shadow without ambient color tint.
    Light key = GetMainLight(TransformWorldToShadowCoord(i.world));
    half shade = key.shadowAttenuation;
    return half4(_BaseColor.rgb * shade, 1);
   }
   ENDHLSL
  }
  UsePass "Universal Render Pipeline/Lit/DepthOnly"
  UsePass "Universal Render Pipeline/Lit/DepthNormals"
 }
}
