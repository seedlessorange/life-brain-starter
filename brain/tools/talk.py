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
    if(!SR){
      note(btn, 'Use the microphone key on your keyboard');
      el.focus();
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
      note(btn, e.error === 'not-allowed'
        ? 'Microphone blocked — allow it in your browser settings'
        : 'Use the microphone key on your keyboard');
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
