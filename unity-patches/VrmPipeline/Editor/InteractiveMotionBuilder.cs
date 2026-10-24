#if UNITY_EDITOR
using System;
using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;

namespace LocalHuman.Editor
{
    // Curves are Humanoid muscles, so the same actions retarget to both VRM skeletons.
    public static class InteractiveMotionBuilder
    {
        public static void AddLayer(AnimatorController controller, AnimationClip idle, bool male)
        {
            string prefix="Assets/Models/"+(male?"Male":"Female")+"Interactive";
            var mask=new AvatarMask { name="UpperBody" };
            for(int i=0;i<(int)AvatarMaskBodyPart.LastBodyPart;i++)mask.SetHumanoidBodyPartActive((AvatarMaskBodyPart)i,false);
            // Spine/Chest stay on the breathing layer. Jaw/eyes stay with VRM/uLipSync.
            foreach(var part in new[]{AvatarMaskBodyPart.Head,AvatarMaskBodyPart.LeftArm,AvatarMaskBodyPart.RightArm,AvatarMaskBodyPart.LeftFingers,AvatarMaskBodyPart.RightFingers})mask.SetHumanoidBodyPartActive(part,true);
            Save(mask,prefix+"UpperBody.mask");
            var sm=new AnimatorStateMachine { name="Interaction" };AssetDatabase.AddObjectToAsset(sm,controller);
            controller.AddLayer(new AnimatorControllerLayer { name="Interaction",stateMachine=sm,avatarMask=mask,defaultWeight=0,blendingMode=AnimatorLayerBlendingMode.Override,iKPass=false });
            foreach(string action in new[]{"Rest","Wave","Nod","Emphasize","Explain","Listen"}) {
                float duration=action=="Wave"?AvatarInteractiveMotion.GreetingSeconds:action=="Rest"?1:2.8f;
                var clip=new AnimationClip { name=action,frameRate=60 };
                foreach(var binding in AnimationUtility.GetCurveBindings(idle)) {
                    string n=binding.propertyName;
                    if(!(n.Contains("Arm ")||n.Contains("Forearm ")||n.Contains("Shoulder ")||n.Contains(" Hand ")||n.StartsWith("LeftHand.")||n.StartsWith("RightHand.")||n.StartsWith("Head ")||n.StartsWith("Neck ")))continue;
                    float rest=AnimationUtility.GetEditorCurve(idle,binding).Evaluate(0);
                    var curve=new AnimationCurve();
                    for(int k=0;k<=56;k++) {
                        float t=k/56f;float envelope=Mathf.SmoothStep(0,1,Mathf.Clamp01(t/.22f))*Mathf.SmoothStep(0,1,Mathf.Clamp01((1-t)/.25f));
                        float target=rest;
                        if(action=="Wave") {
                            // Yuki's large head needs a wider greeting arc to keep fingers out of the hair.
                            if(n=="Right Arm Down-Up")target=male?.05f:.25f;
                            if(n=="Right Arm Front-Back")target=.05f;
                            if(n=="Right Arm Twist In-Out")target=.65f;
                            if(n=="Right Forearm Stretch")target=male?-.25f:-.5f;
                            if(n=="Right Forearm Twist In-Out")target=.1f;
                            // Lift, present an open palm, wave three times, then lower.
                            float wave=Mathf.Sin(Mathf.Clamp01((t-.2f)/.6f)*Mathf.PI*6);
                            if(n=="Right Hand In-Out")target=.28f*wave;
                            if(n=="Right Forearm Twist In-Out")target=.1f+.06f*wave;
                            if(n.StartsWith("RightHand.")&&n.Contains("Stretched"))target=.8f;
                            if(n=="Head Nod Down-Up")target=rest-.045f;
                        }
                        if(action=="Nod"&&n=="Head Nod Down-Up")target=rest-.17f*Mathf.Sin(t*Mathf.PI*4);
                        if(action=="Emphasize") {
                            if(n=="Right Arm Down-Up")target=-.35f;
                            if(n=="Right Arm Front-Back")target=.3f;
                            if(n=="Right Forearm Stretch")target=.25f;
                            if(n=="Right Forearm Twist In-Out")target=-.2f;
                            if(n=="Right Hand Down-Up")target=-.1f;
                        }
                        if(action=="Explain"&&(n.StartsWith("Right ")||n.StartsWith("Left "))) {
                            if(n.Contains("Arm Down-Up"))target=-.32f;
                            if(n.Contains("Arm Front-Back"))target=.18f;
                            if(n.Contains("Forearm Stretch"))target=.38f;
                            if(n.Contains("Forearm Twist In-Out"))target=-.32f;
                            if(n.Contains("Hand Down-Up"))target=-.08f;
                        }
                        if(action=="Listen") {
                            if(n=="Head Tilt Left-Right")target=rest+.055f;
                            if(n=="Neck Turn Left-Right")target=rest+.035f;
                        }
                        curve.AddKey(new Keyframe(t*duration,Mathf.Lerp(rest,target,envelope)));
                    }
                    for(int k=0;k<curve.length;k++){AnimationUtility.SetKeyLeftTangentMode(curve,k,AnimationUtility.TangentMode.ClampedAuto);AnimationUtility.SetKeyRightTangentMode(curve,k,AnimationUtility.TangentMode.ClampedAuto);}
                    AnimationUtility.SetEditorCurve(clip,binding,curve);
                }
                var settings=AnimationUtility.GetAnimationClipSettings(clip);settings.loopTime=action=="Rest";AnimationUtility.SetAnimationClipSettings(clip,settings);
                Save(clip,prefix+action+".anim");
                var state=sm.AddState(action);state.motion=clip;state.writeDefaultValues=false;
                if(action=="Rest")sm.defaultState=state;
            }
        }
        static void Save(UnityEngine.Object asset,string path){AssetDatabase.DeleteAsset(path);AssetDatabase.CreateAsset(asset,path);}
    }
}
#endif
