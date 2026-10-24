using System;
using System.Text;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using LKZ.Logics;
using Newtonsoft.Json.Linq;
namespace LKZ.GPT
{
    public static class LLM
    {
        [Serializable] public class Message { public string role; public string content; }
        [Serializable] public class Payload
        {
            public string model = "local-qwen";
            public bool stream = false;
            public int max_tokens = 128;
            public float temperature = 0.6f;
            public List<Message> messages;
        }
        private static readonly List<Message> history = new List<Message>();
        public static IEnumerator Request(string content, Action<string, bool> callback)
        {
            var config = Resources.Load<LLMConfig>("LLMConfig");
            string url = config && !string.IsNullOrWhiteSpace(config.url) ? config.url : "http://127.0.0.1:8080/v1/chat/completions";
            var messages = new List<Message> { new Message { role = "system", content = "你是友好的中文数字人助手。用简体中文简洁回答，不超过八十字。" } };
            messages.AddRange(history);
            messages.Add(new Message {role = "user", content = content});
            using (var request = new UnityWebRequest(url, "POST"))
            {
                request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(JsonUtility.ToJson(new Payload { messages = messages })));
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 90;
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                { Debug.LogError("LLM: " + request.error); callback?.Invoke("本地大模型服务暂时不可用。", true); yield break; }
                string answer = null;
                try { answer = JToken.Parse(request.downloadHandler.text)["choices"]?[0]?["message"]?["content"]?.ToString(); }
                catch (Exception e) { Debug.LogError(e.Message); }
                if (string.IsNullOrWhiteSpace(answer)) { callback?.Invoke("模型未返回有效内容。", true); yield break; }
                history.Add(new Message {role = "user", content = content});
                history.Add(new Message {role = "assistant", content = answer});
                while (history.Count > 8) history.RemoveRange(0, 2);
                callback?.Invoke(answer, true);
            }
        }
    }
}
