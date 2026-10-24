using UnityEngine;
using UnityEngine.UI;
namespace LocalHuman
{
    // Procedural UI: no textures, bloom pass or per-frame managed allocations.
    public sealed class VoiceActivityGraphic : MaskableGraphic
    {
        public int Mode;public float Level;float envelope,activity;
        void Update(){envelope=Mathf.Lerp(envelope,Level,1-Mathf.Exp(-Time.unscaledDeltaTime*12));activity=Mathf.MoveTowards(activity,Mode==0?0:1,Time.unscaledDeltaTime*2.5f);SetVerticesDirty();}
        void Ring(VertexHelper vh,float radius,float width,Color c)
        {
            const int n=96;
            for(int i=0;i<n;i++) {
                float a=i*Mathf.PI*2/n,b=(i+1)*Mathf.PI*2/n;int start=vh.currentVertCount;
                var da=new Vector2(Mathf.Cos(a),Mathf.Sin(a));var db=new Vector2(Mathf.Cos(b),Mathf.Sin(b));
                vh.AddVert(da*(radius-width),c,Vector2.zero);vh.AddVert(da*radius,c,Vector2.zero);vh.AddVert(db*radius,c,Vector2.zero);vh.AddVert(db*(radius-width),c,Vector2.zero);
                vh.AddTriangle(start,start+1,start+2);vh.AddTriangle(start,start+2,start+3);
            }
        }
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();float t=Time.unscaledTime;bool active=Mode!=0;float breathe=.5f+.5f*Mathf.Sin(t*(active?3:1.7f));
            Color bright=Color.Lerp(new Color32(69,121,113,255),new Color32(23,163,138,255),activity);
            for(int i=0;i<4;i++){var c=bright;c.a=Mathf.Lerp(.045f,.12f,activity)*(1-i/5f);Ring(vh,87+i*8+breathe*4,7,c);}
            Ring(vh,83+breathe*2,Mathf.Lerp(3,5,activity),bright);
            for(int i=0;i<7;i++) {
                float motion=Mode==2?.35f+.18f*Mathf.Sin(t*4-i*.7f):envelope*(.5f+.5f*Mathf.Sin(t*9+i*1.9f));
                float h=Mathf.Lerp(9,12+motion*64,activity);float x=(i-3)*16;int start=vh.currentVertCount;
                vh.AddVert(new Vector2(x-4,-h/2),bright,Vector2.zero);vh.AddVert(new Vector2(x-4,h/2),bright,Vector2.zero);vh.AddVert(new Vector2(x+4,h/2),bright,Vector2.zero);vh.AddVert(new Vector2(x+4,-h/2),bright,Vector2.zero);vh.AddTriangle(start,start+1,start+2);vh.AddTriangle(start,start+2,start+3);
            }
        }
    }
}
