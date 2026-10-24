using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
namespace LocalHuman
{
    // Initialize resources before revealing the interactive character, then measure frames.
    [DefaultExecutionOrder(-1000)]
    public sealed class LocalHumanStartup : MonoBehaviour
    {
        public static bool Ready {get;private set;}
        readonly List<float> frames=new List<float>();
        float began;bool fontReady;LocalHumanDemo demo;
        [Serializable] sealed class StartupReport
        {
            public float preparationMilliseconds,maxInteractiveFrameMilliseconds,p95InteractiveFrameMilliseconds;
            public int interactiveFrames,framesOver100Milliseconds,framesOver33Milliseconds,targetFrameRate;
            public int screenWidth,screenHeight,vSyncCount;public double displayRefreshHz;
            public float[] frameMilliseconds;
            public float maximumCpuMilliseconds,maximumGpuMilliseconds;public string graphicsDevice;public float renderScale;
            public bool bakedPortraitTexture,passed;
            public string measurement="From BeforeSceneLoad to ready; subsequent 240 frame intervals. Engine/window initialization precedes this measurement.";
        }
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Initialize()
        {
            // Use the software cap on high-refresh displays; vSync overrides targetFrameRate.
            Ready=false;QualitySettings.vSyncCount=0;Application.targetFrameRate=60;
            var go=new GameObject("LocalHumanStartup");DontDestroyOnLoad(go);go.AddComponent<LocalHumanStartup>();
        }
        void Awake(){began=Time.realtimeSinceStartup;}
        IEnumerator Start()
        {
            // Let the loading surface paint while the first scene render uploads resources.
            yield return null;demo=FindObjectOfType<LocalHumanDemo>();
            if(!demo){Ready=true;yield break;}
            while(!fontReady)yield return null;
            var features=demo.GetComponent<VrmAvatarLoader>();
            while(features&&(!features.Ready||!features.CacheReady))yield return null;
            // Warm texture upload, skinned identity shapes and face shader under the loading overlay.
            for(int i=0;i<12;i++)yield return new WaitForEndOfFrame();
            yield return new WaitForEndOfFrame();
            yield return new WaitForEndOfFrame();
            Ready=true;
            var report=new StartupReport{preparationMilliseconds=(Time.realtimeSinceStartup-began)*1000,targetFrameRate=Application.targetFrameRate,bakedPortraitTexture=!demo.portraitBytes};
            report.screenWidth=Screen.width;report.screenHeight=Screen.height;report.vSyncCount=QualitySettings.vSyncCount;report.displayRefreshHz=Screen.currentResolution.refreshRateRatio.value;
            var timings=new FrameTiming[1];
            report.graphicsDevice=SystemInfo.graphicsDeviceName;report.renderScale=((UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset)QualitySettings.renderPipeline).renderScale;
            float previous=Time.realtimeSinceStartup;
            for(int i=0;i<240;i++)
            {
                yield return new WaitForEndOfFrame();float now=Time.realtimeSinceStartup;
                frames.Add((now-previous)*1000);previous=now;
                FrameTimingManager.CaptureFrameTimings();
                if(FrameTimingManager.GetLatestTimings(1,timings)>0){report.maximumCpuMilliseconds=Mathf.Max(report.maximumCpuMilliseconds,(float)timings[0].cpuFrameTime);report.maximumGpuMilliseconds=Mathf.Max(report.maximumGpuMilliseconds,(float)timings[0].gpuFrameTime);}
            }
            report.frameMilliseconds=frames.ToArray();foreach(float ms in frames)if(ms>33)report.framesOver33Milliseconds++;
            frames.Sort();report.interactiveFrames=frames.Count;report.maxInteractiveFrameMilliseconds=frames[frames.Count-1];report.p95InteractiveFrameMilliseconds=frames[(int)(frames.Count*.95f)];
            foreach(float ms in frames)if(ms>100)report.framesOver100Milliseconds++;
            report.passed=report.bakedPortraitTexture&&report.maxInteractiveFrameMilliseconds<=33f;
            string path="/home/yyy/digital-human/logs/client-startup.json";
            string[] args=Environment.GetCommandLineArgs();int index=Array.IndexOf(args,"-human-startup-self-test");
            if(index>=0&&index+1<args.Length)path=args[index+1];
            Directory.CreateDirectory(Path.GetDirectoryName(path));File.WriteAllText(path,JsonUtility.ToJson(report,true));Debug.Log("STARTUP: "+JsonUtility.ToJson(report));
            if(index>=0)Application.Quit(report.passed?0:2);
            else Destroy(gameObject);
        }
        void OnGUI()
        {
            if(Ready)return;
            if(demo&&!fontReady)
            {
                if(demo.chineseFont)
                {
                    string text="本地数字人输入文字或按录音按钮开始你好请介绍一下自己中文系统法粘贴问题发送停止最长秒重播上一条回答就绪正在准备播放录音取消错误就绪 / Send Record Stop 0123456789…";
                    int size=GUI.skin.label.fontSize>0?GUI.skin.label.fontSize:demo.chineseFont.fontSize;
                    demo.chineseFont.RequestCharactersInTexture(text,size,FontStyle.Normal);
                }
                fontReady=true;
            }
            GUI.depth=-10000;GUI.color=Color.white;GUI.DrawTexture(new Rect(0,0,Screen.width,Screen.height),Texture2D.whiteTexture);GUI.color=Color.white;
            GUI.Label(new Rect(Screen.width*.5f-100,Screen.height*.5f-15,240,30),"正在准备，请稍候…");
        }
    }
}
