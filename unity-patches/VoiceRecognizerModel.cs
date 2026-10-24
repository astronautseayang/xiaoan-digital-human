using LKZ.Commands.Voice;
using LKZ.DependencyInject;
using LKZ.TypeEventSystem;
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;

namespace LKZ.Voice
{
    // Local HTTP recognition with silence endpointing. No remote WebSocket service.
    public sealed class VoiceRecognizerModel
    {
        [Inject] private MonoBehaviour _mono { get; set; }
        [Inject] private ISendCommand SendCommand { get; set; }
        [Inject] private IRegisterCommand RegisterCommand { get; set; }
        const int Rate = 16000;
        const int RingSeconds = 10;
        const float Threshold = 0.012f;
        const string Url = "http://127.0.0.1:9881/api/asr";
        AudioClip microphone;
        Coroutine capture;
        Coroutine upload;
        bool enabled;
        bool busy;
        int position;
        readonly List<float> utterance = new List<float>();
        readonly List<float> preroll = new List<float>();
        int silenceSamples;
        int voicedSamples;
        [Serializable] sealed class Result { public string text; public string care_command; }

        public void Initialized()
        {
            RegisterCommand.Register<SettingVoiceRecognitionCommand>(SetEnabled);
            capture = _mono.StartCoroutine(Capture());
        }

        void SetEnabled(SettingVoiceRecognitionCommand command)
        {
            enabled = command.IsStartVoiceRecognition;
            Clear();
            if (microphone) position = Mathf.Max(0, Microphone.GetPosition(null));
        }

        void Clear()
        {
            utterance.Clear(); preroll.Clear(); silenceSamples = 0; voicedSamples = 0;
        }

        IEnumerator Capture()
        {
            yield return Application.RequestUserAuthorization(UserAuthorization.Microphone);
            if (!Application.HasUserAuthorization(UserAuthorization.Microphone) || Microphone.devices.Length == 0)
            { Debug.LogError("本地语音识别需要可用的麦克风及录音权限。"); yield break; }
            microphone = Microphone.Start(null, true, RingSeconds, Rate);
            if (!microphone) { Debug.LogError("麦克风启动失败。"); yield break; }
            float deadline = Time.realtimeSinceStartup + 5;
            while (Microphone.GetPosition(null) <= 0 && Time.realtimeSinceStartup < deadline) yield return null;
            if (Microphone.GetPosition(null) <= 0) { Debug.LogError("麦克风启动超时。"); yield break; }
            position = Microphone.GetPosition(null);
            var wait = new WaitForSecondsRealtime(0.1f);
            while (true)
            {
                yield return wait;
                int end = Microphone.GetPosition(null);
                if (end < 0) continue;
                int count = (end - position + microphone.samples) % microphone.samples;
                if (count == 0) continue;
                var samples = new float[count * microphone.channels];
                bool read = microphone.GetData(samples, position);
                position = end;
                if (!read || !enabled || busy) { Clear(); continue; }
                // Unity normally captures mono; average channels if the device returns more.
                var mono = new float[count];
                double energy = 0;
                for (int n = 0; n < count; n++)
                {
                    float value = 0;
                    for (int c = 0; c < microphone.channels; c++) value += samples[n * microphone.channels + c];
                    mono[n] = value / microphone.channels;
                    energy += mono[n] * mono[n];
                }
                bool speech = Math.Sqrt(energy / count) >= Threshold;
                if (utterance.Count == 0)
                {
                    if (!speech)
                    {
                        preroll.AddRange(mono);
                        if (preroll.Count > Rate / 4) preroll.RemoveRange(0, preroll.Count - Rate / 4);
                        continue;
                    }
                    utterance.AddRange(preroll); preroll.Clear();
                }
                utterance.AddRange(mono);
                silenceSamples = speech ? 0 : silenceSamples + count;
                if (speech) voicedSamples += count;
                if (silenceSamples >= Rate * 0.7f || utterance.Count >= Rate * 12)
                {
                    if (voicedSamples >= Rate / 4)
                    {
                        byte[] wav = ToWav(utterance, microphone.frequency);
                        busy = true;
                        upload = _mono.StartCoroutine(Recognize(wav));
                    }
                    Clear();
                }
            }
        }

        IEnumerator Recognize(byte[] wav)
        {
            try
            {
                var parts = new List<IMultipartFormSection> { new MultipartFormFileSection("file", wav, "speech.wav", "audio/wav") };
                using (var request = UnityWebRequest.Post(Url, parts))
                {
                    request.timeout = 90;
                    yield return request.SendWebRequest();
                    if (request.result != UnityWebRequest.Result.Success)
                    { Debug.LogError("本地语音识别失败: " + request.error + " " + request.downloadHandler.text); yield break; }
                    Result result = null;
                    try { result = JsonUtility.FromJson<Result>(request.downloadHandler.text); }
                    catch (Exception e) { Debug.LogError(e.Message); }
                    if (enabled && result != null && string.IsNullOrEmpty(result.care_command) && !string.IsNullOrWhiteSpace(result.text))
                    {
                        SendCommand.Send(new VoiceRecognitionResultCommand { IsComplete = false, text = result.text });
                        SendCommand.Send(new VoiceRecognitionResultCommand { IsComplete = true, text = string.Empty });
                    }
                }
            }
            finally { busy = false; upload = null; }
        }

        static byte[] ToWav(List<float> samples, int rate)
        {
            using (var stream = new MemoryStream())
            using (var writer = new BinaryWriter(stream))
            {
                writer.Write(System.Text.Encoding.ASCII.GetBytes("RIFF")); writer.Write(36 + samples.Count * 2);
                writer.Write(System.Text.Encoding.ASCII.GetBytes("WAVEfmt ")); writer.Write(16);
                writer.Write((short)1); writer.Write((short)1); writer.Write(rate); writer.Write(rate * 2);
                writer.Write((short)2); writer.Write((short)16);
                writer.Write(System.Text.Encoding.ASCII.GetBytes("data")); writer.Write(samples.Count * 2);
                foreach (float sample in samples) writer.Write((short)(Mathf.Clamp(sample, -1, 1) * 32767));
                return stream.ToArray();
            }
        }

        public void OnDestroy()
        {
            enabled = false;
            if (_mono && capture != null) _mono.StopCoroutine(capture);
            if (_mono && upload != null) _mono.StopCoroutine(upload);
            if (microphone) { Microphone.End(null); UnityEngine.Object.Destroy(microphone); }
            Clear();
        }
    }
}
