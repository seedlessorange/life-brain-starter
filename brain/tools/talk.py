#!/usr/bin/env python3
"""Dictation for every Claude-facing input, on every page.

Any input or textarea carrying `data-mic` gets a small microphone button
appended right after it — including ones created later by page script (a
MutationObserver watches). The mic streams speech into the field using the
browser's speech API. Chrome's implementation needs a secure context, which
http:// over the tailnet is not; when unavailable the button says plainly to
use the keyboard's own mic key (which always works) instead of dying silently.

Generators append `talk.block()` once, before </body>.
"""

CSS = """
.talkmic{flex:none;width:34px;height:34px;border-radius:50%;border:1px solid var(--line);
  background:var(--bg);color:var(--dim);cursor:pointer;padding:0;
  display:inline-flex;align-items:center;justify-content:center;align-self:flex-end}
.talkmic:hover{color:var(--text);border-color:var(--dim)}
.talkmic svg{width:16px;height:16px}
.talkmic[aria-pressed="true"]{background:var(--bad);color:var(--paper);
  border-color:transparent;animation:talkpulse 1.4s ease-in-out infinite}
@keyframes talkpulse{0%,100%{opacity:1}50%{opacity:.55}}
@media(prefers-reduced-motion: reduce){
  .talkmic[aria-pressed="true"]{animation:none}
}
.talknote{font-size:11px;color:var(--faint);margin-left:6px;align-self:center}
"""

ENGINE = r"""
(function(){
var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
var MICSVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
  + ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  + '<rect x="9" y="2" width="6" height="12" rx="3"/>'
  + '<path d="M5 10v1a7 7 0 0 0 14 0v-1"/><path d="M12 18v4"/></svg>';
var live = null;                          // one recording at a time

function note(btn, msg){
  var n = document.createElement('span');
  n.className = 'talknote'; n.textContent = msg;
  btn.parentNode.insertBefore(n, btn.nextSibling);
  setTimeout(function(){ n.remove(); }, 3200);
}

function stop(){
  if(!live) return;
  try { live.rec.stop(); } catch(e){}
  live.btn.setAttribute('aria-pressed', 'false');
  live = null;
}

// Push-to-talk for browsers with no speech API (Zen, Firefox, Safari):
// record here, transcribe on the Mac itself (/api/dictate, the same local
// Whisper the voice notes use). Tap to start, tap again to finish; the
// words land a few seconds later. Shared with the ramble/dump/capture mics.
var mediaLive = null;
window.talkRecord = function(btn, el, say){
  say = say || function(){};
  if(mediaLive && mediaLive.btn === btn){ try { mediaLive.mr.stop(); } catch(e){} return; }
  if(mediaLive){ try { mediaLive.mr.stop(); } catch(e){} }
  if(!window.isSecureContext){
    say('The browser blocks the mic on a plain http address — open '
      + '127.0.0.1:7718 on this Mac, or press fn twice for keyboard dictation');
    return;
  }
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia
     || typeof MediaRecorder === 'undefined'){
    say('This browser will not hand over the microphone — press fn twice '
      + 'for keyboard dictation');
    return;
  }
  navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream){
    var mr;
    try { mr = new MediaRecorder(stream); }
    catch(e){
      stream.getTracks().forEach(function(t){ t.stop(); });
      say('Recording is not supported in this browser');
      return;
    }
    var chunks = [];
    mr.ondataavailable = function(e){ if(e.data && e.data.size) chunks.push(e.data); };
    mr.onstop = function(){
      stream.getTracks().forEach(function(t){ t.stop(); });
      btn.setAttribute('aria-pressed', 'false');
      if(mediaLive && mediaLive.timer) clearTimeout(mediaLive.timer);
      mediaLive = null;
      var blob = new Blob(chunks, {type: mr.mimeType || 'audio/webm'});
      if(blob.size < 2000){ say('Heard nothing'); return; }
      say('Transcribing on this Mac…');
      var rd = new FileReader();
      rd.onload = function(){
        fetch('/api/dictate', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({audio: rd.result})})
          .then(function(r){ return r.json(); })
          .then(function(j){
            if(j.error){ say(j.error); return; }
            var t = (j.text || '').trim();
            if(!t){ say('Heard nothing'); return; }
            el.value = (el.value ? el.value.replace(/\s*$/, '') + ' ' : '') + t;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.focus();
          })
          .catch(function(){ say('Could not reach the brain to transcribe'); });
      };
      rd.readAsDataURL(blob);
    };
    mr.start();
    mediaLive = {btn: btn, mr: mr,
                 timer: setTimeout(function(){ try { mr.stop(); } catch(e){} },
                                   120000)};
    btn.setAttribute('aria-pressed', 'true');
    say('Recording — tap the mic again to finish');
  }).catch(function(){
    say('Microphone blocked for this site — allow it from the icon by the address bar');
  });
};

function wire(el){
  if(el.dataset.micwired) return;
  el.dataset.micwired = '1';
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'talkmic';
  btn.innerHTML = MICSVG;
  btn.title = 'Dictate';
  btn.setAttribute('aria-label', 'Dictate into this field');
  btn.setAttribute('aria-pressed', 'false');
  btn.onclick = function(ev){
    ev.preventDefault(); ev.stopPropagation();
    if(live && live.btn === btn){ stop(); return; }
    stop();
    if(!SR || !window.isSecureContext){
      // No streaming speech here (Zen/Firefox/Safari, or an http address the
      // API refuses) — fall back to record-then-transcribe on the Mac.
      window.talkRecord(btn, el, function(m){ if(m) note(btn, m); });
      return;
    }
    var rec = new SR();
    rec.continuous = true; rec.interimResults = true;
    rec.lang = navigator.language || 'en-GB';
    var base = el.value ? el.value.replace(/\s*$/, '') + ' ' : '';
    rec.onresult = function(e){
      var out = '';
      for(var i = e.resultIndex; i < e.results.length; i++)
        out += e.results[i][0].transcript;
      el.value = base + out;
      if(e.results[e.results.length - 1].isFinal) base = el.value + ' ';
      el.dispatchEvent(new Event('input', {bubbles: true}));
    };
    rec.onerror = function(e){
      note(btn, e.error === 'not-allowed' || e.error === 'service-not-allowed'
        ? 'Microphone blocked for this site — allow it from the icon by the address bar'
        : e.error === 'network'
        ? 'The speech service is unreachable — fn twice starts keyboard dictation'
        : 'Dictation stopped (' + e.error + ') — fn twice starts keyboard dictation');
      stop();
    };
    rec.onend = function(){ if(live && live.btn === btn) stop(); };
    live = {rec: rec, btn: btn};
    btn.setAttribute('aria-pressed', 'true');
    el.focus();
    try { rec.start(); } catch(e){ stop(); }
  };
  el.parentNode.insertBefore(btn, el.nextSibling);
}

function sweep(root){
  (root.querySelectorAll ? root.querySelectorAll('[data-mic]') : [])
    .forEach(wire);
}
sweep(document);
new MutationObserver(function(muts){
  muts.forEach(function(m){
    Array.prototype.forEach.call(m.addedNodes, function(n){
      if(n.nodeType !== 1) return;
      if(n.matches && n.matches('[data-mic]')) wire(n);
      sweep(n);
    });
  });
}).observe(document.body, {childList: true, subtree: true});
})();
"""


def block():
    return "<style>" + CSS + "</style>\n<script>" + ENGINE + "</script>\n"
