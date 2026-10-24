using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
namespace LocalHuman
{
    // Segment boundaries come from the actual TTS clips. Inside a long segment,
    // page timing follows audio position and text length (TTS has no word timestamps).
    public sealed class SpeechSubtitleTrack : MonoBehaviour
    {
        public struct Cue
        {
            public float start,end;public string text;
            public Cue(float start,float end,string text){this.start=start;this.end=end;this.text=text;}
        }
        AudioSource source;readonly List<Cue> cues=new List<Cue>();
        readonly List<string> pages=new List<string>();readonly List<float> pageEnds=new List<float>();
        int cachedCue=-1;float cachedWidth;string displayed="";
        public bool HasCaption => cues.Count>0;
        public bool CurrentSpeech(out string text,out float progress)
        {
            text="";progress=0;if(!source||!source.clip||cues.Count==0)return false;
            float position=source.timeSamples/(float)source.clip.frequency;int index=0;
            for(int i=1;i<cues.Count&&position>=cues[i].start;i++)index=i;
            var cue=cues[index];text=cue.text??"";
            progress=Mathf.Clamp01((position-cue.start)/Mathf.Max(.1f,cue.end-cue.start-.22f));return true;
        }
        public void Clear(){source=null;cues.Clear();pages.Clear();pageEnds.Clear();cachedCue=-1;displayed="";}
        public void Bind(AudioSource output,IEnumerable<Cue> timeline)
        {
            Clear();source=output;cues.AddRange(timeline);
        }
        public string Caption(Text target)
        {
            if(!source||cues.Count==0)return "";
            // Hold the last spoken page across download gaps and after completion.
            if(!source.isPlaying&&!string.IsNullOrEmpty(displayed))return displayed;
            float position=source.clip?source.timeSamples/(float)source.clip.frequency:0;
            int index=0;
            for(int i=1;i<cues.Count&&position>=cues[i].start;i++)index=i;
            if(cachedCue!=index||!Mathf.Approximately(cachedWidth,target.rectTransform.rect.width)) {
                cachedCue=index;cachedWidth=target.rectTransform.rect.width;BuildPages(target,cues[index].text??"");
            }
            if(pages.Count==0)return "";
            var cue=cues[index];float duration=Mathf.Max(.1f,cue.end-cue.start-.22f);
            float progress=Mathf.Clamp01((position-cue.start)/duration);int page=0;
            while(page<pages.Count-1&&progress>=pageEnds[page])page++;
            displayed=pages[page];return displayed;
        }
        void BuildPages(Text target,string text)
        {
            pages.Clear();pageEnds.Clear();
            if(string.IsNullOrWhiteSpace(text))return;
            var settings=target.GetGenerationSettings(target.rectTransform.rect.size);
            settings.verticalOverflow=VerticalWrapMode.Overflow;settings.richText=false;
            using(var generator=new TextGenerator()) {
                generator.Populate(text,settings);var lines=generator.lines;
                if(lines.Count==0)pages.Add(text.Trim());
                else for(int i=0;i<lines.Count;i+=2) {
                    int start=Mathf.Clamp(lines[i].startCharIdx,0,text.Length);
                    int end=i+2<lines.Count?Mathf.Clamp(lines[i+2].startCharIdx,start,text.Length):text.Length;
                    string page=text.Substring(start,end-start).Trim();if(page.Length>0)pages.Add(page);
                }
            }
            float total=0;
            foreach(string page in pages) {
                foreach(char c in page)total+=char.IsWhiteSpace(c)?.3f:char.IsPunctuation(c)?2f:1f;
                pageEnds.Add(total);
            }
            for(int i=0;i<pageEnds.Count;i++)pageEnds[i]/=Mathf.Max(1,total);
        }
    }
}
