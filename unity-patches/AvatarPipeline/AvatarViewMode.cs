using UnityEngine;
namespace LocalHuman
{
    // View changes only move the camera; the avatar keeps its current animation.
    public sealed class AvatarViewMode : MonoBehaviour
    {
        Camera view;Vector3 portraitPosition;Quaternion portraitRotation;float portraitFov;
        public bool FullBody {get;private set;}
        void Start()
        {
            view=Camera.main;if(!view)return;
            portraitPosition=view.transform.position;portraitRotation=view.transform.rotation;portraitFov=view.fieldOfView;
            SetFullBody(PlayerPrefs.GetInt("AvatarFullBodyView",0)==1);
        }
        public void SetFullBody(bool full)
        {
            if(!view)return;
            FullBody=full;
            if(full){view.transform.position=new Vector3(0,-.24f,2.65f);view.transform.rotation=Quaternion.Euler(0,180,0);view.fieldOfView=32;}
            else {view.transform.SetPositionAndRotation(portraitPosition,portraitRotation);view.fieldOfView=portraitFov;}
            PlayerPrefs.SetInt("AvatarFullBodyView",full?1:0);PlayerPrefs.Save();
        }
    }
}
