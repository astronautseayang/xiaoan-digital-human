using UnityEngine;
using System.Collections;
namespace LocalHuman
{
    // A baked Humanoid idle keeps the lower body still; IK follows the real support collider.
    public sealed class VrmGrounding:MonoBehaviour
    {
        Animator animator;readonly Vector3[] anchors=new Vector3[2];readonly float[] offsets=new float[2];
        public float maxSlide,maxGap;public int hits;public bool bothOnGround;readonly bool[] onStand=new bool[2];
        public void Initialize(Animator value,bool shoulderWidthStance=false) {
            animator=value;
            for(int i=0;i<2;i++) {
                var p=animator.GetBoneTransform(i==0?HumanBodyBones.LeftFoot:HumanBodyBones.RightFoot).position;
                anchors[i]=p;offsets[i]=p.y+.57181f;
            }
            if(shoulderWidthStance) {
                var across=animator.GetBoneTransform(HumanBodyBones.LeftUpperArm).position-animator.GetBoneTransform(HumanBodyBones.RightUpperArm).position;
                across.y=0;var center=(anchors[0]+anchors[1])*.5f;
                anchors[0]=new Vector3(center.x+across.x*.5f,anchors[0].y,center.z+across.z*.5f);
                anchors[1]=new Vector3(center.x-across.x*.5f,anchors[1].y,center.z-across.z*.5f);
            }
        }
        IEnumerator Start()
        {
            // IK rotation changes the asset's shoe silhouette. Calibrate the actual deformed sole,
            // not the ankle pivot, after the Animator has evaluated the flat contact pose.
            for(int pass=0;pass<3;pass++){
                yield return new WaitForEndOfFrame();
                float minimum=float.MaxValue;
                foreach(var renderer in GetComponentsInChildren<SkinnedMeshRenderer>()){
                    var mesh=new Mesh();renderer.BakeMesh(mesh);
                    foreach(var v in mesh.vertices)minimum=Mathf.Min(minimum,renderer.transform.TransformPoint(v).y);
                    Destroy(mesh);
                }
                float correction=Mathf.Clamp(-.57181f-minimum,-.02f,.02f);
                for(int i=0;i<2;i++)offsets[i]+=correction;
            }
        }
        void OnAnimatorIK(int layer)
        {
            if(!animator)return;
            for(int i=0;i<2;i++){
                var goal=i==0?AvatarIKGoal.LeftFoot:AvatarIKGoal.RightFoot;var p=anchors[i];
                if(Physics.Raycast(new Vector3(p.x,-.37181f,p.z),Vector3.down,out var hit,.5f,1<<30,QueryTriggerInteraction.Ignore)){
                    onStand[i]=hit.collider.name=="Floor";
                    animator.SetIKPositionWeight(goal,1);animator.SetIKRotationWeight(goal,1);
                    animator.SetIKPosition(goal,hit.point+Vector3.up*offsets[i]);
                    animator.SetIKRotation(goal,Quaternion.FromToRotation(Vector3.up,hit.normal)*transform.rotation);hits++;
                }else{onStand[i]=false;animator.SetIKPositionWeight(goal,0);animator.SetIKRotationWeight(goal,0);}
            }
            bothOnGround=onStand[0]&&onStand[1];
        }
    }
}
