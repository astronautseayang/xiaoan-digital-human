using System;
using UnityEngine;
namespace LocalHuman
{
    [RequireComponent(typeof(AudioSource))]
    public sealed class SeniorAudioLimiter : MonoBehaviour
    {
        public volatile bool LoudGain;
        public volatile bool Emergency;
        float envelope=1;
        // Runs on Unity's audio thread: no Unity API calls or allocations.
        void OnAudioFilterRead(float[] data,int channels)
        {
            float boost=(LoudGain||Emergency)?1.9953f:1f;
            for(int i=0;i<data.Length;i+=channels) {
                float peak=0;
                for(int c=0;c<channels;c++)peak=Math.Max(peak,Math.Abs(data[i+c]*boost));
                float target=peak>.891f?.891f/peak:1f;
                envelope=target<envelope?target:Math.Min(target,envelope+.00015f);
                for(int c=0;c<channels;c++)data[i+c]=Math.Max(-.891f,Math.Min(.891f,data[i+c]*boost*envelope));
            }
        }
    }
}
