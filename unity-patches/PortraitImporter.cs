#if UNITY_EDITOR
using System;
using System.IO;
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using UnityEditor.Animations;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
namespace LocalHuman.Editor
{
    public static class PortraitImporter
    {
        [MenuItem("Local Human/Import portrait and create demo scene")]
        public static void CreateDemo()
        {
            const string dir = "Assets/LocalPortrait";

            AssetDatabase.Refresh();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var root = new GameObject("LocalDigitalHuman"); root.SetActive(false);
            var loader=root.AddComponent<VrmAvatarLoader>();loader.maleIdleController=CreateIdle(true);loader.idleController=loader.maleIdleController;
            root.AddComponent<AvatarInteractiveMotion>();
            var audio = root.GetComponent<AudioSource>(); audio.playOnAwake = false; audio.spatialBlend = 0;
            var analyzer = root.AddComponent<global::uLipSync.uLipSync>();
            analyzer.profile = AssetDatabase.LoadAssetAtPath<global::uLipSync.Profile>("Assets/uLipSync/Assets/Profiles/uLipSync-Profile-Sample.asset");
            if (!analyzer.profile) throw new FileNotFoundException("Bundled uLipSync profile missing");
            var binding = root.AddComponent<LocalAvatarLipSync>(); binding.profile = analyzer.profile;
            var demo = root.AddComponent<LocalHumanDemo>();
            demo.chineseFont = AssetDatabase.LoadAssetAtPath<Font>("Assets/LocalPortrait/DroidSansFallbackFull.ttf");
            demo.portraitBytes=null;demo.clothBytes=null;
            var glass=new Material(Shader.Find("LocalHuman/StudioGlass")){name="StudioGlass"};
            AssetDatabase.DeleteAsset("Assets/LocalPortrait/StudioGlass.mat");AssetDatabase.CreateAsset(glass,"Assets/LocalPortrait/StudioGlass.mat");demo.glassMaterial=glass;
            StudioEnvironment();
            root.SetActive(true);
            PrefabUtility.SaveAsPrefabAsset(root, dir + "/Portrait.prefab");
            var rendererData = AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.Universal.UniversalRendererData>("Assets/Settings/Windows Pipeline Asset_Renderer.asset");
            if (!rendererData)throw new InvalidOperationException("Forward renderer missing");
            rendererData.rendererFeatures.RemoveAll(f=>!f);
            foreach(var feature in rendererData.rendererFeatures)if(feature)feature.SetActive(false);
            var ssao=rendererData.rendererFeatures.Find(f=>f && f.GetType().Name=="ScreenSpaceAmbientOcclusion");
            if(!ssao){ssao=(UnityEngine.Rendering.Universal.ScriptableRendererFeature)ScriptableObject.CreateInstance(typeof(UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset).Assembly.GetType("UnityEngine.Rendering.Universal.ScreenSpaceAmbientOcclusion"));ssao.name="Studio Contact SSAO";AssetDatabase.AddObjectToAsset(ssao,rendererData);rendererData.rendererFeatures.Add(ssao);}
            var ao=new SerializedObject(ssao);var settings=ao.FindProperty("m_Settings");
            settings.FindPropertyRelative("AOMethod").intValue=1;settings.FindPropertyRelative("Downsample").boolValue=true;
            settings.FindPropertyRelative("AfterOpaque").boolValue=true;settings.FindPropertyRelative("Source").intValue=0;
            settings.FindPropertyRelative("Intensity").floatValue=.32f;settings.FindPropertyRelative("Radius").floatValue=.03f;
            settings.FindPropertyRelative("Samples").intValue=2;settings.FindPropertyRelative("BlurQuality").intValue=1;
            settings.FindPropertyRelative("DirectLightingStrength").floatValue=.15f;
            ao.ApplyModifiedPropertiesWithoutUndo();ssao.Create();ssao.SetActive(true);EditorUtility.SetDirty(ssao);EditorUtility.SetDirty(rendererData);
            var pipeline = AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset>("Assets/Settings/Windows.asset");
            UnityEngine.Rendering.GraphicsSettings.defaultRenderPipeline = pipeline;
            QualitySettings.skinWeights=SkinWeights.FourBones;QualitySettings.renderPipeline = pipeline;pipeline.shadowDistance=12;pipeline.renderScale=1;pipeline.supportsCameraOpaqueTexture=true;pipeline.maxAdditionalLightsCount=2;pipeline.msaaSampleCount=4;pipeline.supportsCameraDepthTexture=true;var pipelineSettings=new SerializedObject(pipeline);pipelineSettings.FindProperty("m_MainLightShadowsSupported").boolValue=true;pipelineSettings.FindProperty("m_MainLightShadowmapResolution").intValue=2048;pipelineSettings.FindProperty("m_SoftShadowsSupported").boolValue=true;pipelineSettings.FindProperty("m_AdditionalLightsRenderingMode").intValue=(int)UnityEngine.Rendering.Universal.LightRenderingMode.PerPixel;pipelineSettings.ApplyModifiedPropertiesWithoutUndo();EditorUtility.SetDirty(pipeline);
            var camera = new GameObject("Camera").AddComponent<Camera>(); camera.tag = "MainCamera";
            camera.transform.position = new Vector3(0, .10f, 1.20f);
            camera.transform.LookAt(new Vector3(0,.12f,0));
            camera.orthographic = false; camera.fieldOfView = 32; camera.nearClipPlane = .01f; camera.farClipPlane = 20;
            camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = Color.white;
            camera.gameObject.AddComponent<AudioListener>();
            StudioStaging(camera);
            PreserveVrmShaders();
            EditorSceneManager.SaveScene(scene, "Assets/LocalDigitalHuman.unity");
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene("Assets/LocalDigitalHuman.unity", true) };
            AssetDatabase.SaveAssets();
            Debug.Log("Standard VRM studio scene generated; legacy character generators excluded.");
        }
        static Material Surface(string name, Color color, float smooth = .2f)
        {
            var material = new Material(Shader.Find("Universal Render Pipeline/Lit")) { name = name, color = color };
            material.SetFloat("_Smoothness", smooth);
            string path = "Assets/LocalPortrait/" + name + ".mat";
            AssetDatabase.DeleteAsset(path); AssetDatabase.CreateAsset(material, path); return material;
        }
        static GameObject Solid(string name, PrimitiveType type, Vector3 position, Vector3 scale, Material material, Transform parent = null)
        {
            var go = GameObject.CreatePrimitive(type); go.name = name;
            go.transform.SetParent(parent,false); go.transform.localPosition = position; go.transform.localScale = scale;
            go.GetComponent<Renderer>().sharedMaterial = material;
            UnityEngine.Object.DestroyImmediate(go.GetComponent<Collider>()); return go;
        }
        static void StudioEnvironment()
        {
            const float floorY=-.57181f;
            var white=Surface("CycloramaPorcelain",Color.white,0);
            white.shader=Shader.Find("LocalHuman/StudioWhite");white.SetFloat("_Metallic",0);white.SetFloat("_Smoothness",0);EditorUtility.SetDirty(white);
            var floor=Solid("Floor",PrimitiveType.Cube,new Vector3(0,floorY-.0125f,-1.2f),new Vector3(20,.025f,20),white);
            floor.GetComponent<Renderer>().enabled=false; // Collider remains the same support height.
            var vertices=new System.Collections.Generic.List<Vector3>();var triangles=new System.Collections.Generic.List<int>();
            var section=new System.Collections.Generic.List<Vector2>{new Vector2(8,floorY),new Vector2(-1.2f,floorY)};
            const float radius=1.8f;
            for(int i=1;i<=64;i++){float angle=i*Mathf.PI*.5f/64;section.Add(new Vector2(-1.2f-radius*Mathf.Sin(angle),floorY+radius*(1-Mathf.Cos(angle))));}
            section.Add(new Vector2(-3,5));
            foreach(var point in section){vertices.Add(new Vector3(-10,point.y,point.x));vertices.Add(new Vector3(10,point.y,point.x));}
            for(int i=0;i<section.Count-1;i++){int n=i*2;triangles.AddRange(new[]{n,n+1,n+2,n+1,n+3,n+2});}
            var mesh=new Mesh{name="ContinuousCycloramaMesh"};mesh.SetVertices(vertices);mesh.SetTriangles(triangles,0);mesh.RecalculateNormals();mesh.RecalculateBounds();
            // Use analytic tangent normals at the floor/arc seam to avoid a shading crease.
            var normals=mesh.normals;for(int i=0;i<section.Count;i++){float angle=i<2?0:i==section.Count-1?Mathf.PI*.5f:(i-1)*Mathf.PI*.5f/64;normals[i*2]=normals[i*2+1]=new Vector3(0,Mathf.Cos(angle),Mathf.Sin(angle));}mesh.normals=normals;
            AssetDatabase.DeleteAsset("Assets/LocalPortrait/Cyclorama.asset");AssetDatabase.CreateAsset(mesh,"Assets/LocalPortrait/Cyclorama.asset");
            var backdrop=new GameObject("CycloramaBackdrop",typeof(MeshFilter),typeof(MeshRenderer));backdrop.GetComponent<MeshFilter>().sharedMesh=mesh;backdrop.GetComponent<Renderer>().sharedMaterial=white;
            backdrop.GetComponent<Renderer>().shadowCastingMode=UnityEngine.Rendering.ShadowCastingMode.Off;
            RenderSettings.ambientMode=UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight=new Color(232/255f,238/255f,245/255f)*.75f;
            RenderSettings.fog=false;
            var key=new GameObject("SoftKey").AddComponent<Light>();key.type=LightType.Directional;key.color=new Color(1,.95f,.9f);key.intensity=.8f;key.shadowBias=.08f;key.shadowNormalBias=.25f;
            key.transform.rotation=Quaternion.Euler(35,145,0);key.shadows=LightShadows.Soft;key.shadowStrength=.55f;
            var fill=new GameObject("HairRimFill").AddComponent<Light>();fill.type=LightType.Directional;fill.intensity=.45f;fill.color=new Color(.80f,.88f,1);fill.transform.rotation=Quaternion.Euler(25,-25,0);
        }
        static RuntimeAnimatorController CreateIdle(bool relaxedMale=false)
        {
            string clipPath=relaxedMale?"Assets/Models/RelaxedMaleIdle.anim":"Assets/Models/StableIdle.anim";
            var source=AssetDatabase.LoadAssetAtPath<AnimationClip>("Assets/Animations/Idle_Stand.anim");
            if(!source)throw new Exception("Humanoid idle source missing");
            var clip=UnityEngine.Object.Instantiate(source);clip.name="Stable Humanoid Idle";
            // Freeze captured standing muscles; animate only subtle chest breathing.
            foreach(var binding in AnimationUtility.GetCurveBindings(clip)){
                var curve=AnimationUtility.GetEditorCurve(clip,binding);float value=curve.Evaluate(0);
                AnimationUtility.SetEditorCurve(clip,binding,AnimationCurve.Constant(0,3.5f,value));
            }
            foreach(var binding in AnimationUtility.GetCurveBindings(clip)){
                string name=binding.propertyName;
                if(name.StartsWith("LeftHandT")||name.StartsWith("RightHandT")||name.StartsWith("LeftHandQ")||name.StartsWith("RightHandQ"))AnimationUtility.SetEditorCurve(clip,binding,null);
                else if(name.Contains("Arm ")||name.Contains("Shoulder ")||name.Contains("Forearm ")||name.Contains(" Hand ")||name.StartsWith("LeftHand.")||name.StartsWith("RightHand.")){
                    float value=0;
                    if(name.Contains("Arm Down-Up"))value=relaxedMale?-.60f:-.55f;
                    if(name.Contains("Arm Front-Back"))value=relaxedMale?.03f:-.08f;
                    if(name.Contains("Forearm Stretch"))value=relaxedMale?.90f:.85f;
                    if(relaxedMale&&name.Contains("Forearm Twist"))value=.42f;
                    if(relaxedMale&&name.Contains("Shoulder Down-Up"))value=-.10f;
                    if(relaxedMale&&name.Contains("Shoulder Front-Back"))value=-.12f;
                    if(name.Contains("Stretched"))value=relaxedMale?.45f:.35f;
                    if(relaxedMale&&name.Contains("Spread"))value=-.45f;
                    AnimationUtility.SetEditorCurve(clip,binding,AnimationCurve.Constant(0,3.5f,value));
                }
                else if(relaxedMale&&name.Contains("Upper Leg In-Out"))
                    AnimationUtility.SetEditorCurve(clip,binding,AnimationCurve.Constant(0,3.5f,.12f));
            }
            // Humanoid muscle curves add a small, seamless 3.5-second breath to the standing pose.
            foreach(var muscle in new[]{"Chest Front-Back","Spine Front-Back"}) {
                var binding=EditorCurveBinding.FloatCurve("",typeof(Animator),muscle);
                var curve=AnimationUtility.GetEditorCurve(clip,binding);float rest=(curve==null?0:curve.Evaluate(0))-.025f;
                float amplitude=muscle.StartsWith("Chest")?.008f:.003f;
                var breath=new AnimationCurve();
                for(int i=0;i<=4;i++) {
                    float phase=i*Mathf.PI*.5f;
                    float tangent=amplitude*2*Mathf.PI/3.5f*Mathf.Cos(phase);
                    breath.AddKey(new Keyframe(i*.875f,rest+amplitude*Mathf.Sin(phase),tangent,tangent));
                }
                AnimationUtility.SetEditorCurve(clip,binding,breath);
            }
            var settings=AnimationUtility.GetAnimationClipSettings(clip);settings.loopTime=true;settings.keepOriginalOrientation=true;
            settings.keepOriginalPositionY=true;settings.keepOriginalPositionXZ=true;settings.loopBlendOrientation=true;settings.loopBlendPositionY=true;settings.loopBlendPositionXZ=true;
            AnimationUtility.SetAnimationClipSettings(clip,settings);
            AssetDatabase.DeleteAsset(clipPath);AssetDatabase.CreateAsset(clip,clipPath);
            string path=relaxedMale?"Assets/Models/RelaxedMaleIdle.controller":"Assets/Models/StableIdle.controller";AssetDatabase.DeleteAsset(path);
            var controller=AnimatorController.CreateAnimatorControllerAtPath(path);var layers=controller.layers;layers[0].iKPass=true;controller.layers=layers;
            var state=controller.layers[0].stateMachine.AddState("Stable Idle");state.motion=clip;controller.layers[0].stateMachine.defaultState=state;
            InteractiveMotionBuilder.AddLayer(controller,clip,relaxedMale);
            return controller;
        }
        static void PreserveVrmShaders()
        {
            var graphics=new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/GraphicsSettings.asset")[0]);
            var shaders=graphics.FindProperty("m_AlwaysIncludedShaders");
            foreach(var name in new[]{"VRM10/Universal Render Pipeline/MToon10"}){
                var shader=Shader.Find(name);if(!shader)throw new Exception("VRM shader missing: "+name);
                bool exists=false;for(int i=0;i<shaders.arraySize;i++)if(shaders.GetArrayElementAtIndex(i).objectReferenceValue==shader)exists=true;
                if(!exists){int n=shaders.arraySize;shaders.InsertArrayElementAtIndex(n);shaders.GetArrayElementAtIndex(n).objectReferenceValue=shader;}
            }
            graphics.ApplyModifiedPropertiesWithoutUndo();
        }
        static void StudioStaging(Camera camera)
        {
            var floor=GameObject.Find("Floor");floor.layer=30;floor.AddComponent<BoxCollider>();
            var key=GameObject.Find("SoftKey").GetComponent<Light>();key.intensity=.95f;key.color=new Color32(255,237,219,255);key.transform.rotation=Quaternion.Euler(50,155,0);key.shadows=LightShadows.Soft;key.shadowBias=.005f;key.shadowNormalBias=.01f;key.shadowStrength=.42f;
            var fill=GameObject.Find("HairRimFill").GetComponent<Light>();fill.color=new Color32(255,239,220,255);fill.intensity=.62f;
            var rim=new GameObject("WarmStudioRimLight").AddComponent<Light>();rim.type=LightType.Directional;rim.color=new Color(1,.91f,.78f);rim.intensity=.38f;rim.transform.rotation=Quaternion.Euler(25,-150,0);
            RenderSettings.ambientMode=UnityEngine.Rendering.AmbientMode.Trilight;
            RenderSettings.ambientSkyColor=new Color(.85f,.82f,.77f);
            RenderSettings.ambientEquatorColor=new Color(.70f,.67f,.61f);
            RenderSettings.ambientGroundColor=new Color(.48f,.44f,.39f);
            // Small static reflection environment: no realtime cubemap rendering.
            const string reflectionPath="Assets/WarmStudioReflection.cubemap";
            var environment=AssetDatabase.LoadAssetAtPath<Cubemap>(reflectionPath);
            if(!environment){environment=new Cubemap(16,TextureFormat.RGBA32,true);AssetDatabase.CreateAsset(environment,reflectionPath);}
            for(int face=0;face<6;face++){
                var pixels=new Color[256];for(int i=0;i<pixels.Length;i++)pixels[i]=face==2?new Color(.92f,.88f,.81f):face==3?new Color(.45f,.42f,.38f):new Color(.72f,.69f,.63f);
                environment.SetPixels(pixels,(CubemapFace)face);
            }
            environment.Apply(true);EditorUtility.SetDirty(environment);
            RenderSettings.defaultReflectionMode=UnityEngine.Rendering.DefaultReflectionMode.Custom;RenderSettings.customReflection=environment;RenderSettings.reflectionIntensity=.45f;
            var probe=new GameObject("WarmPortraitReflection").AddComponent<ReflectionProbe>();probe.mode=UnityEngine.Rendering.ReflectionProbeMode.Custom;probe.customBakedTexture=environment;probe.size=Vector3.one*8;probe.intensity=.45f;
            var data=camera.GetUniversalAdditionalCameraData();data.renderPostProcessing=false;data.requiresDepthTexture=true;data.requiresColorTexture=true;
        }
        public static void BuildLinux()
        {
            CreateDemo();
            PlayerSettings.SetScriptingBackend(BuildTargetGroup.Standalone, ScriptingImplementation.Mono2x);
            string output = Environment.GetEnvironmentVariable("HUMAN_BUILD_PATH") ?? "../build/LocalDigitalHuman.x86_64";
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));
            var report = BuildPipeline.BuildPlayer(new[] { "Assets/LocalDigitalHuman.unity" }, output, BuildTarget.StandaloneLinux64, BuildOptions.CleanBuildCache);
            foreach(var step in report.steps)foreach(var message in step.messages)if(message.type==LogType.Warning||message.type==LogType.Error)Debug.Log("BUILD_DIAGNOSTIC: "+message.content);
            File.WriteAllText("../artifacts/validation/avatar-build.json", "{\"warnings\":"+report.summary.totalWarnings+",\"errors\":"+report.summary.totalErrors+",\"result\":\""+report.summary.result+"\"}");
            if(report.summary.totalWarnings>0)throw new Exception("Build must be warning free: "+report.summary.totalWarnings);
            if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) throw new Exception("Unity Linux build failed");
        }
    }
}
#endif
