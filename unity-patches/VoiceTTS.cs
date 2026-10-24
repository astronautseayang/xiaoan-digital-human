using LKZ.Utilitys;
using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
namespace LKZ.VoiceSynthesis
{
    public static class VoiceTTS
    {
        public const string ErrorMess = "本地语音合成失败";
        private static int voiceID = DataSave.GetVoiceID();
        public static int VoiceID { get => voiceID; set { voiceID = value; DataSave.SetVoiceID(value); } }
        [Serializable] private class Payload { public string text; public string text_lang = "zh"; }
        public static IEnumerator Synthesis(string content)
        {
            using (var request = new UnityWebRequest("http://127.0.0.1:9881/api/tts", "POST"))
            {
                request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new Payload {text = content})));
                request.downloadHandler = new DownloadHandlerAudioClip("http://127.0.0.1:9881/api/tts", AudioType.WAV) {streamAudio = false};
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 180;
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                { Debug.LogError("TTS: " + request.error); yield return ErrorMess; yield break; }
                var clip = DownloadHandlerAudioClip.GetContent(request);
                if (!clip) { yield return ErrorMess; yield break; }
                yield return clip;
            }
        }
    }
}
