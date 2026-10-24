Shader "LocalHuman/StudioGlass"
{
 Properties { [PerRendererData] _MainTex("Texture",2D)="white"{} }
 SubShader
 {
  Tags {"Queue"="Overlay" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline"}
  Pass
  {
   ZTest Always ZWrite Off Cull Off Blend SrcAlpha OneMinusSrcAlpha
   HLSLPROGRAM
   #pragma vertex vert
   #pragma fragment frag
   #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
   #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Color.hlsl"
   sampler2D _CameraOpaqueTexture;float4 _CameraOpaqueTexture_TexelSize;
   struct A{float4 vertex:POSITION;float4 color:COLOR;};
   struct V{float4 vertex:SV_POSITION;float4 color:COLOR;float4 screen:TEXCOORD0;};
   V vert(A v){V o;o.vertex=TransformObjectToHClip(v.vertex.xyz);o.screen=ComputeScreenPos(o.vertex);o.color=v.color;return o;}
   half4 frag(V i):SV_Target
   {
    float2 uv=i.screen.xy/i.screen.w;float2 d=_CameraOpaqueTexture_TexelSize.xy*3;
    half3 c=tex2D(_CameraOpaqueTexture,uv).rgb*4;
    c+=(tex2D(_CameraOpaqueTexture,uv+float2(d.x,0)).rgb+tex2D(_CameraOpaqueTexture,uv-float2(d.x,0)).rgb+tex2D(_CameraOpaqueTexture,uv+float2(0,d.y)).rgb+tex2D(_CameraOpaqueTexture,uv-float2(0,d.y)).rgb)*2;
    c+=tex2D(_CameraOpaqueTexture,uv+d).rgb+tex2D(_CameraOpaqueTexture,uv-d).rgb+tex2D(_CameraOpaqueTexture,uv+float2(d.x,-d.y)).rgb+tex2D(_CameraOpaqueTexture,uv+float2(-d.x,d.y)).rgb;
    return half4(lerp(c/16,i.color.rgb,i.color.a),1);
   }
   ENDHLSL
  }
 }
}
