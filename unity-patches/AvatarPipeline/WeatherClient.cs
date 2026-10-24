using System;
using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
namespace LocalHuman
{
    // The gateway provides city estimation and measured/modelled weather data.
    public sealed class WeatherClient : MonoBehaviour
    {
        [Serializable] sealed class Location { public string city,source; }
        [Serializable] sealed class Day { public string date; public float high,low; public float rain_probability; }
        [Serializable] sealed class Weather { public Location location; public string condition,observed_at,detail; public float temperature; public Day[] days; public bool stale; }
        LocalHumanDemo demo;
        Canvas canvas;
        Text city,temperature,forecast;
        Button card;
        bool loading;
        string Gateway => demo.gateway;
        IEnumerator Start()
        {
            demo=GetComponent<LocalHumanDemo>();Build();
            while(true){yield return Refresh(false);yield return new WaitForSecondsRealtime(30);}
        }
        void Update()
        {
            if(!canvas)return;
            canvas.enabled=LocalHumanStartup.Ready&&!GetComponent<SeniorCareClient>().Active;
            card.interactable=!loading;
        }
        IEnumerator Refresh(bool force)
        {
            if(loading)yield break;
            loading=true;
            try {
                using(var r=UnityWebRequest.Get(Gateway+"/api/weather"+(force?"?refresh=true":""))) {
                    r.timeout=35;yield return r.SendWebRequest();
                    if(r.result!=UnityWebRequest.Result.Success){forecast.text="天气暂不可用 · 点击卡片重试";yield break;}
                    var w=JsonUtility.FromJson<Weather>(r.downloadHandler.text);
                    if(w==null||w.location==null||w.days==null||w.days.Length==0){forecast.text="暂未获得有效天气";yield break;}
                    city.text=w.location.city+(w.location.source=="network"?" · 网络估算":" · 已选城市");
                    temperature.text=w.condition+"  "+w.temperature.ToString("0.#")+"℃";
                    forecast.text=(w.stale?"旧数据 · ":"")+"今日 "+w.days[0].low.ToString("0.#")+"～"+w.days[0].high.ToString("0.#")+"℃  降水 "+w.days[0].rain_probability.ToString("0")+"%";

                }
            } finally {loading=false;}
        }
        RectTransform Box(Transform parent,string name,Vector2 position,Vector2 size)
        {
            var g=new GameObject(name,typeof(RectTransform),typeof(LocalHuman.AvatarPipeline.RoundedCard));
            var r=g.GetComponent<RectTransform>();r.SetParent(parent,false);r.anchorMin=r.anchorMax=r.pivot=new Vector2(.5f,.5f);r.anchoredPosition=position;r.sizeDelta=size;
            var graphic=g.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>();graphic.color=new Color32(225,236,232,255);graphic.radius=18;return r;
        }
        Text Label(Transform parent,string text,float y,float height,int size)
        {
            var g=new GameObject("WeatherText",typeof(RectTransform),typeof(Text));
            var r=g.GetComponent<RectTransform>();r.SetParent(parent,false);r.anchorMin=r.anchorMax=r.pivot=new Vector2(.5f,.5f);r.anchoredPosition=new Vector2(0,y);r.sizeDelta=new Vector2(416,height);
            var t=g.GetComponent<Text>();t.font=demo.chineseFont;t.fontSize=size;t.text=text;t.color=new Color32(29,53,52,255);t.alignment=TextAnchor.MiddleCenter;t.raycastTarget=false;return t;
        }
        void Build()
        {
            var g=new GameObject("WeatherCanvas",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));g.transform.SetParent(transform,false);
            canvas=g.GetComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceOverlay;canvas.sortingOrder=49;
            var scaler=g.GetComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;scaler.referenceResolution=new Vector2(1600,900);scaler.screenMatchMode=CanvasScaler.ScreenMatchMode.Expand;
            var panel=Box(g.transform,"WeatherCard",new Vector2(475,80),new Vector2(440,160));
            card=panel.gameObject.AddComponent<Button>();card.targetGraphic=panel.GetComponent<LocalHuman.AvatarPipeline.RoundedCard>();card.onClick.AddListener(()=>StartCoroutine(Refresh(true)));
            city=Label(panel,"正在获取城市…",44,36,26);
            temperature=Label(panel,"正在查询天气",0,50,34);
            forecast=Label(panel,"",-44,36,22);

        }
    }
}
