#!/usr/bin/env python3
"""The talk orb: speak to the brain and hear it answer, on every page.

Three orbs share one voice:
- the Talk button in the bar: a small live orb in a ring; tap it to talk;
- the talk panel it opens: a large orb, what was said, and the answer;
- Orbit's deck on Today (skin-only furniture, hidden in every other skin):
  a full-screen hero with the large orb in the middle. Tapping that orb
  talks in place, no panel; the bar's button talks there too while the
  deck is on screen.

She speaks and pauses; the clip goes to /api/voice/turn (warm Whisper,
voice.py's router, Kokoro or `say`), and the answer comes back as words and
sound. After it speaks it listens again for a few seconds, so a
conversation needs no more taps; silence puts it back to rest. Esc stops
it. Nothing is recorded unless a talk has started, and the audio is gone
once it is transcribed.

The orbs draw in the skin's `--orb` colour when it has one (Orbit's teal),
else in its ink, so every skin gets its own. They hold still under reduced
motion, and a big orb stops drawing when it is off screen.

Also carried here, because they ride with the voice:
- the plan meter: any element with data-planmeter gets the weekly and
  five-hour percentages from /api/plan-usage (plan_usage.py); a `slim` one
  is a single line, and one with data-full-at stays that line until the
  week passes that share;
- "Hear it" under an answer in the box (data-hear): the answer, read aloud;
- the deck's skill tiles (data-skill-run), which start a run the way the
  box's Run row does.

chrome.py's ask_block() drops block() into every page, once; tab_today.py
puts deck_html() at the top of Today.
"""
import re
from datetime import datetime


CSS = r"""
.vorbbtn{display:inline-flex;align-items:center;gap:8px;font:inherit;
  font-size:var(--t-sm,13px);font-weight:600;cursor:pointer;color:var(--ink);
  background:var(--surface);border:1px solid var(--line2);
  border-radius:var(--r-btn,10px);padding:4px 12px 4px 5px;white-space:nowrap}
.vorbbtn:hover{border-color:var(--dim)}
.vorbring{position:relative;flex:none;display:block;width:26px;height:26px;
  border-radius:50%;overflow:hidden;
  background:radial-gradient(circle at 50% 50%,
    color-mix(in oklab,var(--orb,var(--ink)) 16%,transparent),transparent 70%);
  box-shadow:inset 0 0 0 1px color-mix(in oklab,var(--orb,var(--ink)) 30%,transparent);
  transition:box-shadow .3s}
.vorbmini{display:block;width:100%;height:100%}
.vorbbtn[data-state="listening"] .vorbring{box-shadow:inset 0 0 0 1.5px var(--orb-listen,var(--cold)),
  0 0 10px color-mix(in oklab,var(--orb-listen,var(--cold)) 45%,transparent)}
/* Thinking has its own colour, the skin's amber "wait": a friend could not
   tell when it was listening and when to stay quiet (8 Oct). */
.vorbbtn[data-state="thinking"] .vorbring{
  box-shadow:inset 0 0 0 1.5px var(--orb-think,var(--wait,var(--ink))),
  0 0 10px color-mix(in oklab,var(--orb-think,var(--wait,var(--ink))) 45%,transparent)}
.vorbbtn[data-state="speaking"] .vorbring{
  box-shadow:inset 0 0 0 1.5px var(--orb,var(--ink)),
  0 0 10px color-mix(in oklab,var(--orb,var(--ink)) 35%,transparent)}
.vorbstate{display:none}
/* Below a wide laptop the bar keeps the orb alone, round, as on a phone:
   with School, Jobs and News in the bar and a long name, the word pushed
   the last tab under the find button up to 1280px (9 Oct). */
@media (max-width:1280px){.vorbbtn .vorbtxt{display:none}
  .vorbbtn{padding:0;width:34px;height:34px;justify-content:center;border-radius:50%}}
/* The smallest phones: the bar had exactly one button's room to spare
   before the Talk button, and the logo met the sync dot (360px, 28 Sep). */
@media (max-width:380px){.vorbbtn{width:30px;height:30px}.vorbring{width:24px;height:24px}}
.vscrim{position:fixed;inset:0;z-index:97;opacity:0;transition:opacity .2s ease-out;
  background:color-mix(in oklab,var(--paper) 55%,transparent);
  -webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}
.vscrim.on{opacity:1}
.vscrim[hidden],.vpanel[hidden]{display:none}
.vpanel{position:fixed;z-index:98;left:50%;top:50%;
  width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 40px);
  display:flex;flex-direction:column;align-items:center;box-sizing:border-box;
  padding:18px 20px 16px;background:var(--paper);color:var(--ink);
  border:1px solid var(--line);border-radius:var(--r-xl,20px);
  box-shadow:0 30px 80px -30px rgba(0,0,0,.45);opacity:0;
  transform:translate(-50%,-47%) scale(.98);
  transition:opacity .2s ease-out,transform .28s cubic-bezier(.16,1,.3,1)}
.vpanel.on{opacity:1;transform:translate(-50%,-50%)}
.vx{position:absolute;top:10px;right:12px;width:32px;height:32px;border-radius:50%;
  font-size:20px;line-height:1;cursor:pointer;color:var(--dim);background:none;
  border:0}
.vx:hover{color:var(--ink)}
.vlabel{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);
  align-self:flex-start}
.vorb{display:block;width:min(280px,58vw);height:min(280px,58vw);margin:2px 0}
.vstate{min-height:1.4em;font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);text-align:center}
.vpanel[data-state="error"] .vstate{color:var(--bad);letter-spacing:.01em;
  text-transform:none;font-size:13px}
.vlog{align-self:stretch;display:flex;flex-direction:column;gap:9px;overflow-y:auto;
  max-height:34vh;margin:12px 0 6px;padding:0 2px}
.vlog:empty{display:none}
.vline{max-width:92%;font-size:14.5px;line-height:1.45;overflow-wrap:anywhere}
.vline.her{align-self:flex-end;text-align:right;color:var(--dim)}
.vline.brain{align-self:flex-start}
.vline details{margin-top:4px;font-size:12.5px;color:var(--dim)}
.vline summary{cursor:pointer}
.vline pre{margin:6px 0 0;white-space:pre-wrap;font:inherit}
.vline.note{align-self:center;font-size:12.5px;color:var(--dim)}
.deckend{display:block;margin:10px auto 0;font:inherit;font-size:13px;cursor:pointer;
  color:var(--ink);background:none;border:1px solid var(--line2);border-radius:999px;padding:6px 16px}
.deckend:hover{border-color:var(--ink)}
.deckend[hidden]{display:none}
:root[data-style="orbit"] .deckend{grid-column:2;grid-row:6;justify-self:center}
.vopen{font:inherit;font-size:12px;cursor:pointer;color:var(--orb,var(--ink));background:none;
  border:0;border-bottom:1px solid currentColor;padding:0;margin-left:4px}
/* While she talks on Orbit's deck the orb steps back and the words get the
   room: the whole answer, scrolling if it is long, no fade over its start. */
:root[data-style="orbit"] .skinx-deck.talking{--ob-orb:min(360px,34vh,34vw)}
:root[data-style="orbit"] .skinx-deck.talking .deckorbbtn{transition:width .45s ease}
:root[data-style="orbit"] .skinx-deck.talking .decklog{height:auto;max-height:42vh;
  overflow-y:auto;justify-content:flex-start;-webkit-mask:none;mask:none;padding-bottom:6px}
:root[data-style="orbit"] .skinx-deck.talking .decklog .vline.note{font-size:13px}
.vbar{display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;
  margin-top:8px}
.vtalk{font:inherit;font-size:14px;font-weight:600;cursor:pointer;color:var(--paper);
  background:var(--ink);border:0;border-radius:999px;padding:10px 24px;min-width:140px}
.vtalk:disabled{opacity:.55;cursor:default}
.vhint{font-size:11.5px;color:var(--faint,var(--dim))}
@media (hover:none){.vesc{display:none}}
@media (max-width:560px){
  .vpanel{left:0;right:0;top:auto;bottom:0;width:100vw;max-height:92vh;
    border-radius:20px 20px 0 0;border-bottom:0;transform:translateY(6%);
    padding-bottom:max(16px,env(safe-area-inset-bottom))}
  .vpanel.on{transform:none}
}
@media (prefers-reduced-motion:reduce){.vpanel,.vscrim{transition:none}}
/* The deck's working parts; how it looks is Orbit's (skins/orbit.css). */
.deckorbbtn{display:block;padding:0;margin:0 auto;border:0;background:none;
  cursor:pointer;border-radius:50%;aspect-ratio:1;color:inherit}
.deckorbbtn:focus-visible{outline:2px solid var(--orb,var(--ink));outline-offset:6px}
.deckorb{display:block;width:100%;height:100%}
/* the plan meter */
.planmeter[hidden]{display:none}
.pmhead{display:flex;align-items:baseline;gap:8px;font-size:11px;
  letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
.pmold{letter-spacing:.04em;text-transform:none;color:var(--faint,var(--dim))}
.pmrow{display:flex;align-items:baseline;gap:6px;margin:4px 0 6px}
.pmnum{font-size:34px;font-weight:300;line-height:1;letter-spacing:-.02em}
.pmunit{font-size:12px;color:var(--dim)}
.pmbar{position:relative;display:block;height:10px;border-radius:3px;overflow:hidden;
  background:repeating-linear-gradient(90deg,
    color-mix(in oklab,var(--ink) 14%,transparent) 0 1px,transparent 1px 5px),
    color-mix(in oklab,var(--ink) 6%,transparent)}
.pmbar i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;
  background:color-mix(in oklab,var(--ink) 70%,transparent)}
.pmbar.wait i{background:var(--wait)}
.pmbar.bad i{background:var(--bad)}
.pmfoot{margin-top:6px;font-size:12px;color:var(--dim)}
.pmnone{margin:0;font-size:12px;color:var(--dim)}
.planmeter.slim{display:flex;align-items:center;gap:8px;padding:8px 16px 0;
  font-size:12px;color:var(--dim)}
.planmeter.slim .pmbar{flex:1;max-width:160px;height:6px}
.planmeter.slim b{color:var(--ink);font-weight:600}
.askhear{font:inherit;font-size:11.5px;cursor:pointer;color:var(--dim);background:none;
  border:0;padding:6px 0 0;display:inline-flex;align-items:center;gap:5px}
.askhear:hover{color:var(--ink)}
.askhear.on{color:var(--ink)}
.vpick{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:6px 0}
.vpick .aplabel{min-width:64px;margin:0}
.vpick select{font:inherit;font-size:14px;color:var(--ink);background:var(--surface);
  border:1px solid var(--line2);border-radius:var(--r-btn,10px);padding:6px 10px;max-width:100%}
"""

HTML = """
<div class="vscrim" id="vscrim" hidden></div>
<div class="vpanel" id="vpanel" hidden role="dialog" aria-modal="true"
  aria-label="Talk to the brain" data-state="idle">
  <button class="vx" id="vx" aria-label="Close">&times;</button>
  <div class="vlabel">Voice</div>
  <canvas class="vorb" id="vorb" aria-hidden="true"></canvas>
  <div class="vstate" id="vstate" role="status">Tap to talk</div>
  <div class="vlog" id="vlog" aria-live="polite"></div>
  <div class="vbar">
    <button class="vtalk" id="vtalk">Tap to talk</button>
    <span class="vhint">pause to send<span class="vesc"> &middot; Esc closes</span></span>
  </div>
</div>
"""

JS = r"""
(function(){
var P = document.getElementById('vpanel');
if(!P) return;
var D = document.querySelector('.skinx-deck');
var scrim = document.getElementById('vscrim');
var reduce = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function q(root, sel){ return root ? root.querySelector(sel) : null; }

// ---- colours: the skin's --orb when it has one, else its ink. Re-read every
// two seconds, because the style picker changes the skin under the page.
var TOK = {at: 0};
function tokens(){
  var now = Date.now();
  if(now - TOK.at < 2000) return TOK;
  var cs = getComputedStyle(document.documentElement);
  function g(n){ return cs.getPropertyValue(n).trim(); }
  var ink = g('--ink') || '#222';
  var bg = getComputedStyle(document.body).backgroundColor, m = bg.match(/[\d.]+/g), dark = false;
  if(m && m.length >= 3 && !(m.length > 3 && +m[3] === 0))
    dark = .2126 * m[0] + .7152 * m[1] + .0722 * m[2] < 110;
  TOK = {at: now, orb: g('--orb') || ink, listen: g('--orb-listen') || g('--cold') || ink,
         think: g('--orb-think') || g('--wait') || ink, bad: g('--bad') || '#c33', dark: dark};
  return TOK;
}
// One soft light, drawn once per colour and stamped for every node: a
// bright centre fading to nothing. Cheap, and it is what makes the cloud
// read as lit from inside rather than as dots.
var SPR = {};
function sprite(col){
  if(SPR[col]) return SPR[col];
  var c = document.createElement('canvas'); c.width = c.height = 64;
  var x = c.getContext('2d'), g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, col); g.addColorStop(1, 'rgba(0,0,0,0)');
  x.globalAlpha = .6; x.fillStyle = g; x.fillRect(0, 0, 64, 64);
  var g2 = x.createRadialGradient(32, 32, 0, 32, 32, 12);
  g2.addColorStop(0, col); g2.addColorStop(1, 'rgba(0,0,0,0)');
  x.globalAlpha = 1; x.fillStyle = g2; x.fillRect(0, 0, 64, 64);
  x.beginPath(); x.arc(32, 32, 5, 0, 6.2832); x.fillStyle = col; x.fill();
  SPR[col] = c;
  return c;
}

// ---- the orbs. A mini is points on a sphere's skin; a big one is a cloud,
// most points near the surface and the rest inside, each tied to its
// nearest neighbours, so it reads as a lit network, not a wireframe.
function sphere(canvas, kind){
  var n = kind === 'mini' ? 72 : kind === 'deck' ? 900 : 520;
  var pts = [], links = [], g = Math.PI * (3 - Math.sqrt(5));
  for(var i = 0; i < n; i++){
    var y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = g * i;
    var x = Math.cos(th) * r, z = Math.sin(th) * r, rad = 1;
    if(kind !== 'mini'){
      rad = Math.random() < .6 ? .8 + Math.random() * .2 : Math.pow(Math.random(), .5) * .8;
      x += (Math.random() - .5) * .12; y += (Math.random() - .5) * .12; z += (Math.random() - .5) * .12;
    }
    pts.push([x * rad, y * rad, z * rad, Math.random()]);
  }
  var k = kind === 'mini' ? 2 : 3, lim = kind === 'mini' ? .5 : kind === 'deck' ? .05 : .07;
  for(var a = 0; a < n; a++){
    var best = [];
    for(var b = 0; b < n; b++){
      if(a === b) continue;
      var dx = pts[a][0]-pts[b][0], dy = pts[a][1]-pts[b][1], dz = pts[a][2]-pts[b][2],
          d = dx*dx + dy*dy + dz*dz;
      if(d > lim) continue;
      best.push([d, b]);
    }
    best.sort(function(u, v){ return u[0] - v[0]; });
    for(var j = 0; j < Math.min(k, best.length); j++)
      if(best[j][1] > a) links.push([a, best[j][1]]);
  }
  // which links touch each point, so a signal can hop on through the net
  var adj = pts.map(function(){ return []; });
  links.forEach(function(L, ix){ adj[L[0]].push(ix); adj[L[1]].push(ix); });
  return {c: canvas, kind: kind, pts: pts, links: links, adj: adj, q: new Array(n),
          on: true, sig: [], acc: 0};
}
// Signals: light running along the network's links, hopping node to node.
// A trickle at rest, a flow while thinking, her voice while listening.
var SIGRATE = {idle: .5, listening: 3, thinking: 26, speaking: 8, error: 0};
function signals(o, ctx, Q, col, dt, spr, unit){
  if(reduce || !o.links.length) return;
  var rate = SIGRATE[S] + (S === 'listening' ? level * 30 : 0);
  o.acc += rate * dt / 1000;
  while(o.acc >= 1 && o.sig.length < 70){
    o.acc -= 1;
    var li = (Math.random() * o.links.length) | 0;
    o.sig.push({l: li, t: 0, fwd: Math.random() < .5, hops: 2 + ((Math.random() * 4) | 0)});
  }
  if(o.acc >= 1) o.acc = 0;
  var dur = S === 'thinking' ? 320 : 650, keep = [];
  ctx.strokeStyle = col; ctx.lineWidth = .9;
  for(var i = 0; i < o.sig.length; i++){
    var g = o.sig[i], L = o.links[g.l], A = Q[g.fwd ? L[0] : L[1]], B = Q[g.fwd ? L[1] : L[0]];
    g.t += dt / dur;
    if(g.t >= 1){
      // hop on from the far end, while it has hops left
      var end = g.fwd ? L[1] : L[0], nx = o.adj[end];
      if(g.hops > 0 && nx.length){
        var li2 = nx[(Math.random() * nx.length) | 0];
        if(li2 !== g.l){ g.l = li2; g.fwd = o.links[li2][0] === end; g.t = 0; g.hops--; keep.push(g); }
      }
      continue;
    }
    keep.push(g);
    var x = A[0] + (B[0] - A[0]) * g.t, y = A[1] + (B[1] - A[1]) * g.t;
    var depth = ((A[2] + B[2]) / 2 + 1) / 2, glow = Math.sin(Math.PI * g.t);
    ctx.globalAlpha = (.12 + .35 * depth) * glow;
    ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
    var sz = (8 + depth * 8) * (unit || 1);
    ctx.globalAlpha = (.45 + .55 * depth) * glow;
    ctx.drawImage(spr, x - sz / 2, y - sz / 2, sz, sz);
  }
  o.sig = keep;
}
var ORBS = [], S = 'idle', level = 0, rot = 0, lastT = 0, pending = false;
function visible(o){
  if(!o.c.isConnected) return false;
  if(o.kind === 'panel') return !P.hidden;
  if(o.kind === 'deck') return o.on && o.c.offsetParent !== null;
  return o.c.offsetParent !== null;
}
function draw(o, now){
  var c = o.c, dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
  if(!w || !h) return;
  var W = Math.round(w * dpr), H = Math.round(h * dpr);
  if(c.width !== W || c.height !== H){ c.width = W; c.height = H; }
  var ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  var T = tokens(), mini = o.kind === 'mini';
  var col = S === 'listening' ? T.listen : S === 'thinking' ? T.think
          : S === 'error' ? T.bad : T.orb;
  var think = S === 'thinking' && !reduce;
  var breathe = reduce ? 0 : Math.sin(now / 1900) * .02;
  var R = Math.min(w, h) * (mini ? .46 : .42)
          * (1 + breathe + level * (mini ? .1 : .16) + (think ? Math.sin(now / 170) * .012 : 0));
  var cr = Math.cos(rot), sr = Math.sin(rot), ct = Math.cos(.38), st = Math.sin(.38);
  var pts = o.pts, Q = o.q, n = pts.length, i;
  for(i = 0; i < n; i++){
    var p = pts[i], dr = (reduce || mini) ? 0 : Math.sin(now / 2600 + p[3] * 30) * .016;
    var x = p[0] * (1 + dr), y = p[1] * (1 + dr), z = p[2] * (1 + dr);
    var x2 = x * cr + z * sr, z1 = -x * sr + z * cr;
    var y2 = y * ct - z1 * st, z2 = y * st + z1 * ct;
    var jig = think ? Math.sin(now / 95 + p[3] * 40) * .03 : 0;
    var kk = 1.1 / (1.55 - z2 * .45);
    Q[i] = [w / 2 + x2 * R * (1 + jig) * kk, h / 2 + y2 * R * (1 + jig) * kk, z2, p[3],
            Math.sqrt(x2 * x2 + y2 * y2)];
  }
  var add = !mini && T.dark;
  if(!mini){
    // a soft light at the heart of it
    var g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, R * 1.15);
    g.addColorStop(0, col); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.globalAlpha = .13 + level * .14 + (S === 'speaking' ? .05 : 0);
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  }
  if(add) ctx.globalCompositeOperation = 'lighter';
  // the links: faint, fainter at the back
  ctx.strokeStyle = col; ctx.lineWidth = mini ? .55 : .5;
  var LA = mini ? [.18, .3, .45] : (add ? [.03, .07, .13] : [.05, .1, .2]);
  for(var bk = 0; bk < 3; bk++){
    ctx.beginPath();
    for(var l = 0; l < o.links.length; l++){
      var A = Q[o.links[l][0]], B = Q[o.links[l][1]], zz = (A[2] + B[2]) / 2;
      if((zz < -.33 ? 0 : zz < .33 ? 1 : 2) !== bk) continue;
      ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]);
    }
    ctx.globalAlpha = Math.min(1, LA[bk] + level * .1);
    ctx.stroke();
  }
  if(mini){
    ctx.fillStyle = col;
    var DA = [.45, .7, 1], DS = [.5, .7, .9];
    for(bk = 0; bk < 3; bk++){
      ctx.beginPath();
      for(i = 0; i < n; i++){
        var pp = Q[i];
        if((pp[2] < -.33 ? 0 : pp[2] < .33 ? 1 : 2) !== bk) continue;
        ctx.moveTo(pp[0] + DS[bk], pp[1]); ctx.arc(pp[0], pp[1], DS[bk], 0, 6.2832);
      }
      ctx.globalAlpha = Math.min(1, DA[bk] * (S === 'idle' ? .85 : 1) + level * .15);
      ctx.fill();
    }
  } else {
    // the nodes: each a small light, bigger and brighter at the front,
    // each breathing on its own slow beat
    var spr = sprite(col), unit = Math.max(1, R / 170);
    for(i = 0; i < n; i++){
      var q2 = Q[i], depth = (q2[2] + 1) / 2, ph = q2[3];
      var tw = reduce ? 1 : .78 + .22 * Math.sin(now / 1300 + ph * 40);
      if(think) tw *= .7 + .3 * Math.sin(now / 150 + ph * 25);
      var bright = ph > .965 && q2[2] > -.2;
      // the rim catches the light, the way an atmosphere does
      var rim = Math.max(0, Math.min(1, (q2[4] - .72) / .26));
      var sz = (bright ? 17 : 4.5 + depth * 9 + rim * 3) * unit;
      ctx.globalAlpha = Math.min(1, (bright ? .95 : .14 + depth * .55 + rim * .25) * tw + level * .15);
      ctx.drawImage(spr, q2[0] - sz / 2, q2[1] - sz / 2, sz, sz);
    }
    signals(o, ctx, Q, col, o.dt || 16, spr, unit);
  }
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = 1;
}
function frame(now){
  pending = false;
  now = now || performance.now();
  var dt = lastT ? Math.min(64, now - lastT) : 16; lastT = now;
  var speed = {idle: .00008, listening: .00022, thinking: .001, speaking: .00035, error: .00005}[S] || .0001;
  if(!reduce) rot += speed * dt;
  var big = false, any = false;
  for(var i = 0; i < ORBS.length; i++){
    if(!visible(ORBS[i])) continue;
    any = true; if(ORBS[i].kind !== 'mini') big = true;
    ORBS[i].dt = dt;
    draw(ORBS[i], now);
  }
  if(!any || reduce) return;
  pending = true;
  // Only the bar's little orb on screen, and nothing happening: a slow
  // redraw is plenty, and it keeps an idle tab from burning battery.
  if(!big && S === 'idle') setTimeout(function(){ requestAnimationFrame(frame); }, 70);
  else requestAnimationFrame(frame);
}
function kick(){ if(!pending){ pending = true; requestAnimationFrame(frame); } }
function addOrb(canvas, kind){
  if(!canvas || canvas._orb) return;
  var o = sphere(canvas, kind); canvas._orb = o; ORBS.push(o);
  if(kind === 'deck' && window.IntersectionObserver){
    new IntersectionObserver(function(es){
      es.forEach(function(e){ o.on = e.isIntersecting; }); kick();
    }).observe(canvas);
  }
  kick();
}
addOrb(q(P, '#vorb'), 'panel');
if(D) addOrb(q(D, '.deckorb'), 'deck');
document.querySelectorAll('.vorbmini').forEach(function(c){ addOrb(c, 'mini'); });

// ---- where a talk happens: the panel, or the deck
var PANEL = {root: P, msg: q(P, '#vstate'), log: q(P, '#vlog'), keep: 14};
var DECK = D ? {root: D, msg: q(D, '.decksub'), log: q(D, '.decklog'), keep: 4,
                idle: (q(D, '.decksub') || {}).textContent || ''} : null;
// A phone has no Space or Esc key, so its hints name only what works there.
var KEYLESS = !!(window.matchMedia && matchMedia('(hover: none) and (pointer: coarse)').matches);
if(DECK && KEYLESS){ DECK.idle = 'Tap the orb to talk'; if(DECK.msg) DECK.msg.textContent = DECK.idle; }
var CUR = PANEL;
var WORD = {idle: 'idle', listening: 'listening', thinking: 'thinking', speaking: 'speaking', error: 'idle'};
var LABEL = {idle: 'Tap to talk', listening: 'Listening · pause to send',
             thinking: 'Thinking', speaking: 'Speaking', error: ''};
function deckOnScreen(){
  if(!DECK) return false;
  var o = q(D, '.deckorb'); o = o && o._orb;
  return !!(o && o.on && D.offsetParent !== null);
}
function setState(s, msg){
  S = s;
  if(s === 'idle' && CUR === DECK) roomToTalk(false);
  P.setAttribute('data-state', s);
  if(D) D.setAttribute('data-state', s);
  document.querySelectorAll('.vorbbtn').forEach(function(b){
    b.setAttribute('data-state', s);
    var st = q(b, '.vorbstate'); if(st) st.textContent = 'Claude · ' + WORD[s];
  });
  var btnText = s === 'listening' ? 'Send now' : s === 'speaking' ? 'Stop'
              : s === 'thinking' ? 'Thinking…' : 'Tap to talk';
  [q(P, '#vtalk'), q(D, '.decktalk')].forEach(function(b){
    if(!b) return; b.textContent = btnText; b.disabled = s === 'thinking';
  });
  if(DECK){
    D.querySelectorAll('.deckpills [data-s]').forEach(function(p){
      p.classList.toggle('on', p.getAttribute('data-s') === WORD[s]);
    });
  }
  if(CUR === DECK){
    var on = D.classList.contains('talking');
    if(DECK.msg) DECK.msg.textContent = msg || (on ? (KEYLESS ? 'Say “that’s all” to finish'
                                                     : 'Say “that’s all” or press Esc to finish') : DECK.idle);
    var endb = q(D, '.deckend'); if(endb) endb.hidden = !on;
  }
  else if(PANEL.msg) PANEL.msg.textContent = msg || LABEL[s] || '';
  kick();
}

// ---- sound: one element, unlocked by the first tap (iOS plays nothing
// that did not start inside a tap, unless the element already has).
var player = new Audio(), unlocked = false;
var SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
function unlock(){
  if(unlocked) return; unlocked = true;
  try { player.src = SILENT; var p = player.play(); if(p && p.catch) p.catch(function(){}); } catch(e){}
}
function hush(){ try { player.onpause = null; player.pause(); } catch(e){} }
function sound(src, done){
  if(!src){ if(done) done(); return; }
  hush();
  var fin = false;
  function end(){ if(fin) return; fin = true; if(done) done(); }
  player.onended = end; player.onerror = end;
  player.onpause = function(){ if(!player.ended) end(); };
  player.src = src;
  var p = player.play();
  if(p && p.catch) p.catch(end);
}
function play(src, done, tail, lang){
  if(!src){ if(done) done(); return; }
  setState('speaking');
  var rest = tail ? fetch('/api/voice/say', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                           body: JSON.stringify({text: tail, lang: lang || ''})})
                      .then(function(r){ return r.json(); })
                      .then(function(j){ return j.audio || null; })
                      .catch(function(){ return null; }) : null;
  sound(src, function(){
    if(!rest){ level = 0; if(done) done(); return; }
    rest.then(function(a){
      if(!a || S !== 'speaking'){ level = 0; if(done) done(); return; }
      sound(a, function(){ level = 0; if(done) done(); });
    });
  });
}

// ---- listening, with a pause to send
var rec = null, ac = null;
// What talking still needs on this computer, from /api/voice/warm. A friend's
// Mac without the speech engine listened, then said "ffmpeg is needed" (8 Oct).
var DEAF = '';
function listen(auto){
  if(rec || S === 'thinking') return;
  if(DEAF){ setState('error', DEAF); return; }
  if(!window.isSecureContext){
    setState('error', 'The browser only lends the mic on 127.0.0.1:7718 or the ts.net address');
    return;
  }
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined'){
    setState('error', 'This browser will not share the microphone');
    return;
  }
  var here = CUR;
  navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true,
                                               autoGainControl: true}}).then(function(stream){
    if(DEAF || CUR !== here || (here === PANEL && P.hidden)){
      stream.getTracks().forEach(function(t){ t.stop(); });
      if(DEAF) setState('error', DEAF);
      return;
    }
    var an = null;
    try {
      ac = ac || new (window.AudioContext || window.webkitAudioContext)();
      if(ac.state === 'suspended') ac.resume();
      an = ac.createAnalyser(); an.fftSize = 1024;
      ac.createMediaStreamSource(stream).connect(an);
    } catch(e){ an = null; }
    var mr;
    try { mr = new MediaRecorder(stream); }
    catch(e){ stream.getTracks().forEach(function(t){ t.stop(); });
              setState('error', 'Recording is not supported in this browser'); return; }
    var r = {stream: stream, mr: mr, chunks: [], an: an, start: performance.now(),
             spoke: false, loud: 0, floor: 0, auto: !!auto, why: ''};
    mr.ondataavailable = function(e){ if(e.data && e.data.size) r.chunks.push(e.data); };
    mr.onstop = function(){ finish(r); };
    rec = r;
    mr.start(250);
    setState('listening');
  }).catch(function(){
    setState('error', 'Microphone blocked. Allow it from the icon by the address bar');
  });
}
function stopRec(why){
  if(!rec) return;
  rec.why = why;
  try { rec.mr.stop(); } catch(e){ finish(rec); }
}
function finish(r){
  if(rec === r) rec = null;
  level = 0;
  try { r.stream.getTracks().forEach(function(t){ t.stop(); }); } catch(e){}
  if(r.done) return; r.done = true;
  if(r.why === 'cancel') return;
  if(r.why === 'nothing'){ setState('idle', r.auto ? '' : 'Heard nothing. Tap to try again'); return; }
  var blob = new Blob(r.chunks, {type: r.mr.mimeType || 'audio/webm'});
  if(blob.size < 2000){ setState('idle', 'Heard nothing. Tap to try again'); return; }
  setState('thinking', 'Listening back');
  var rd = new FileReader();
  rd.onload = function(){ turn({audio: rd.result}, r.auto); };
  rd.readAsDataURL(blob);
}
setInterval(function(){
  var now = performance.now();
  if(rec && rec.an){
    var buf = new Float32Array(rec.an.fftSize); rec.an.getFloatTimeDomainData(buf);
    var s = 0; for(var i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    var rms = Math.sqrt(s / buf.length), el = now - rec.start;
    if(el < 350) rec.floor = Math.max(rec.floor, rms);
    // Listening again after a reply, only real speech counts: a higher bar,
    // held for a quarter of a second. Room noise and the tail of the
    // brain's own voice had been heard as words, and answered.
    var th = rec.auto ? Math.max(.03, Math.min(.02, rec.floor) * 3.5)
                      : Math.max(.014, Math.min(.02, rec.floor) * 2.4);
    if(rms > th){ rec.loud = now; rec.run = (rec.run || 0) + 1;
                  if(el > 300 && rec.run >= (rec.auto ? 5 : 2)) rec.spoke = true; }
    else rec.run = 0;
    level = level * .6 + Math.min(1, rms * 9) * .4;
    // Her pauses mid-thought run long: 2.2 s of quiet before it sends
    // (1.3 s cut her off), and 12 s to start speaking at all.
    // Twenty seconds in, she is rambling, and thinking pauses run longer.
    var quiet = el > 20000 ? 3500 : 2200;
    if(rec.spoke && now - rec.loud > quiet) stopRec('send');
    else if(!rec.spoke && el > (rec.auto ? 8000 : 12000)) stopRec('nothing');
    else if(el > 300000) stopRec('send');
  } else if(rec){
    level = .18 + .08 * Math.sin(now / 200);
    if(now - rec.start > 30000) stopRec('send');
  } else if(S === 'speaking'){
    level = level * .7 + (.1 + .25 * Math.abs(Math.sin(now / 130)) * Math.random()) * .3;
  } else level *= .8;
  if(reduce && S !== 'idle') kick();
}, 50);

// ---- one turn
var HIST = [];
function line(who, text, more, convo){
  if(!text || !CUR.log) return;
  var d = document.createElement('div');
  d.className = 'vline ' + who;
  d.textContent = text;
  if(convo){
    var o = document.createElement('button');
    o.className = 'vopen'; o.type = 'button'; o.textContent = 'Open in the box';
    o.onclick = function(){ if(window.brainBox && window.brainBox.openConvo) window.brainBox.openConvo(convo); };
    d.appendChild(document.createTextNode(' ')); d.appendChild(o);
  }
  if(more){
    var det = document.createElement('details');
    det.innerHTML = '<summary>The full answer</summary><pre></pre>';
    det.querySelector('pre').textContent = more;
    d.appendChild(det);
  }
  CUR.log.appendChild(d);
  while(CUR.log.children.length > CUR.keep) CUR.log.removeChild(CUR.log.firstChild);
  CUR.log.scrollTop = CUR.log.scrollHeight;
  return d;
}
// What she tells it is filed by a run in the box. "Filing it now" stayed
// the last word, so she never saw what changed (9 Oct): when the run ends,
// its own summary takes that line's place.
function filedGist(t){
  var p = String(t || '').split(/\n\s*\n/).map(function(x){
    return x.replace(/[`*_#>]/g, '').replace(/\s+/g, ' ').trim(); })
    .filter(function(x){ return x && !/^committed\.?$/i.test(x); })[0] || '';
  return p.length > 260 ? p.slice(0, 257).replace(/\s+\S*$/, '') + '…' : p;
}
function watchFiled(el, cid){
  if(!el || !cid) return;
  var q = encodeURIComponent(cid), base = -1, tries = 0;
  var said = function(){
    return fetch('/api/sessions/transcript?id=' + q).then(function(r){ return r.json(); })
      .then(function(t){ return (t.events || []).filter(function(e){
        return e.k === 'claude' && (e.t || '').trim(); }); });
  };
  said().then(function(evs){ base = evs.length; poll(); }).catch(function(){});
  function poll(){
    if(!el.isConnected || ++tries > 120) return;
    fetch('/api/sessions/feed?id=' + q).then(function(r){ return r.json(); })
      .then(function(f){
        if(f.running){ setTimeout(poll, 2500); return; }
        return said().then(function(evs){
          if(evs.length <= base){ setTimeout(poll, 2500); return; }
          var g = filedGist(evs[evs.length - 1].t);
          if(g && el.firstChild) el.firstChild.nodeValue = 'Done: ' + g;
        });
      }).catch(function(){ setTimeout(poll, 5000); });
  }
}
function turn(payload, auto){
  var here = CUR;
  setState('thinking');
  payload.history = HIST.slice(-8);
  fetch('/api/voice/turn', {method: 'POST', headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(payload)})
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(CUR !== here || (here === PANEL && P.hidden)) return;
      if(j.error){ setState('error', j.error); return; }
      // Nothing real heard: after a reply that just means she is done.
      if(!j.heard){ setState('idle', auto ? '' : 'Heard nothing. Tap to try again'); return; }
      line('her', j.heard);
      HIST.push({who: 'her', text: j.heard});
      var said = j.say || '';
      if(j.open){ stop(); location.href = j.open; return; }
      if(j.full && !j.filed){
        line('brain', said + ' → the box');
        HIST.push({who: 'brain', text: said});
        play(j.audio, function(){ stop(); if(window.brainBox) window.brainBox.open({text: j.full, send: true}); });
        return;
      }
      var more = (j.text && j.text.replace(/\s+/g, ' ').trim() !== said.trim()
                  && j.text.length > said.length + 40) ? j.text : '';
      line('brain', said || j.text, more);
      if(j.filed){
        var what = {update: 'Filing it now.', dump: 'Sorting it into the brain.',
                    'do': 'Working on it.'}[j.filed.kind] || 'Filing it now.';
        watchFiled(line('note', j.filed.id ? what : 'Queued: the next run does it.', '',
                        j.filed.id), j.filed.id);
      }
      HIST.push({who: 'brain', text: j.gist || said || j.text});
      play(j.audio, function(){
        if(CUR !== here || (here === PANEL && P.hidden)) return;
        if(j.end){ stop(); return; }
        setState('idle');
        // The conversation keeps its turn: listen again, briefly. Silence
        // puts it back to rest.
        setTimeout(function(){ if(S === 'idle' && CUR === here && !rec
                                  && !(here === PANEL && P.hidden)) listen(true); }, 700);
      }, j.tail, j.say_lang);
    })
    .catch(function(){ setState('error', 'Could not reach the brain'); });
}

// ---- starting, stopping
function warmUp(){
  fetch('/api/voice/warm', {method: 'POST', headers: {'Content-Type': 'application/json'},
                            body: '{}'})
    .then(function(r){ return r.json(); })
    .then(function(j){
      DEAF = (j && j.need) || '';
      if(DEAF && (rec || S === 'listening')){ stopRec('cancel'); setState('error', DEAF); }
    }).catch(function(){});
}
function openPanel(){
  if(!P.hidden) return;
  scrim.hidden = false; P.hidden = false;
  requestAnimationFrame(function(){ scrim.classList.add('on'); P.classList.add('on'); });
  kick();
}
function stop(){
  stopRec('cancel'); hush();
  if(D){ clearTimeout(restTimer); D.classList.remove('talking');
         var eb = q(D, '.deckend'); if(eb) eb.hidden = true;
         if(DECK && DECK.msg) DECK.msg.textContent = DECK.idle; }
  if(!P.hidden){
    scrim.classList.remove('on'); P.classList.remove('on');
    scrim.hidden = true; P.hidden = true;
  }
  setState('idle');
}
var restTimer = 0;
function roomToTalk(on){
  if(!D) return;
  clearTimeout(restTimer);
  if(on) D.classList.add('talking');
  // The words stay up two minutes after the last one, then the orb returns.
  else restTimer = setTimeout(function(){ if(S === 'idle') stop(); }, 120000);
}
function talkIn(surf){
  unlock();
  if(surf === DECK) roomToTalk(true);
  if(CUR !== surf && (rec || S !== 'idle')) stop();
  CUR = surf;
  if(surf === PANEL) openPanel();
  warmUp();
  listen(false);
}
function toggle(surf){
  unlock();
  if(CUR === surf && S === 'listening'){ stopRec('send'); return; }
  if(CUR === surf && S === 'speaking'){ hush(); setState('idle'); return; }
  if(S === 'thinking') return;
  talkIn(surf);
}
q(P, '#vtalk').onclick = function(){ toggle(PANEL); };
q(P, '#vx').onclick = stop;
scrim.onclick = stop;
if(D){
  D.addEventListener('click', function(e){
    if(e.target.closest('.deckend')){ e.preventDefault(); stop(); return; }
    if(e.target.closest('.deckorbbtn, .decktalk')){ e.preventDefault(); toggle(DECK); }
    var j = e.target.closest('[data-deckjump]');
    if(j){
      e.preventDefault();
      var t = document.getElementById(j.getAttribute('data-deckjump'));
      if(t) t.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'start'});
    }
  });
}
document.addEventListener('click', function(e){
  var b = e.target.closest && e.target.closest('[data-talk]');
  if(!b) return;
  e.preventDefault();
  var where = deckOnScreen() ? DECK : PANEL;
  if(CUR === where && S !== 'idle'){ toggle(where); return; }
  talkIn(where);
});
document.addEventListener('keydown', function(e){
  var active = !P.hidden || S !== 'idle';
  // On the deck, Space is the way in: the page is at its top, nothing is
  // typed into, no panel is open.
  // Space is the way in, anywhere she is not typing: on the deck when it is
  // on screen, in the panel everywhere else. Not while the box is open, and
  // not on a focused control, which answers Space itself.
  var box = document.getElementById('askpanel');
  var tg = e.target, busy = tg && (tg.tagName === 'INPUT' || tg.tagName === 'TEXTAREA'
      || tg.tagName === 'SELECT' || tg.tagName === 'BUTTON' || tg.tagName === 'A'
      || tg.isContentEditable);
  if(!active && e.key === ' ' && !busy && !e.metaKey && !e.ctrlKey && !e.altKey
     && P.hidden && !(box && !box.hidden)){
    e.preventDefault(); talkIn(deckOnScreen() ? DECK : PANEL); return;
  }
  if(!active) return;
  if(e.key === 'Escape'){ e.preventDefault(); stop(); return; }
  // A focused button already answers Space itself; answering too would
  // start and stop in one press.
  var t = e.target, typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
                                   || t.tagName === 'BUTTON' || t.isContentEditable);
  if(e.key === ' ' && !typing){ e.preventDefault(); toggle(CUR); }
});
window.brainVoice = {open: function(){ talkIn(deckOnScreen() ? DECK : PANEL); }, close: stop,
  // True while a talk is on, or its words are still on screen: the page's
  // own refresh waits for this, so a filed update cannot wipe the conversation.
  busy: function(){ return S !== 'idle' || !!rec || !P.hidden
                           || !!(D && D.classList.contains('talking')); }};

// ---- the deck: clock, the evening turn, runs, the skill tiles
if(D){
  var DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],
      MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var clk = q(D, '[data-deckclock]'), place = clk ? clk.getAttribute('data-place') : '';
  var nlab = q(D, '[data-decknextlab]');
  var pad = function(n){ return (n < 10 ? '0' : '') + n; };
  var tick = function(){
    var d = new Date(), h = d.getHours();
    // The three done and the evening come: the deck stops handing out
    // work. Wrap up leads the skills, and the next hour waits for next time.
    var eve = D.getAttribute('data-alldone') === '1' && (h >= 17 || h < 4);
    D.classList.toggle('eve', eve);
    if(nlab) nlab.textContent = eve ? 'Next time' : 'Your next hour';
    if(!clk) return;
    // The date in the bar's own format (THU 08 OCT); Orbit shows it only
    // where the bar hides its own, so the screen says the date once.
    clk.innerHTML = '<b>' + pad(h) + ':' + pad(d.getMinutes()) + '</b><small>'
      + '<span class="deckdate">' + DAYS[d.getDay()] + ' ' + pad(d.getDate()) + ' '
      + MON[d.getMonth()] + (place ? ' · ' : '') + '</span>' + esc(place) + '</small>';
  };
  tick(); setInterval(tick, 1000);
  var runs = q(D, '[data-deckruns]');
  var runTick = function(){
    if(!runs || !deckOnScreen() || document.hidden) return;
    fetch('/api/agent').then(function(r){ return r.json(); }).then(function(j){
      // Name the run and light its tile: a click has to show where it
      // happened (7 Oct, "I clicked Catch me up, then nothing happened").
      var tile = j.running && q(D, '[data-skill-run="' + j.job + '"]');
      D.querySelectorAll('.decktile.running').forEach(function(t){
        if(t !== tile) t.classList.remove('running'); });
      if(tile) tile.classList.add('running');
      var name = tile ? (tile.getAttribute('data-label') || '') : '';
      runs.textContent = j.running ? (name || 'A run') + ' is running · the report lands in Jobs'
        : (j.pending ? j.pending + ' waiting in the queue' : 'Runs in the background · reports land in Jobs');
      runs.classList.toggle('on', !!j.running);
    }).catch(function(){});
  };
  setTimeout(runTick, 1500); setInterval(runTick, 20000);
  D.addEventListener('click', function(e){
    var b = e.target.closest('[data-skill-run]');
    if(!b) return;
    e.preventDefault();
    var label = (b.getAttribute('data-label') || b.textContent).trim();
    if(!confirm('Start Claude Code to ' + label.toLowerCase()
                + '? It runs on your Mac, on your subscription.')) return;
    function go(anyway){
      var body = {job: b.getAttribute('data-skill-run')};
      if(anyway) body.anyway = true;
      return fetch('/api/agent', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                  body: JSON.stringify(body)})
        .then(function(r){ return r.json(); })
        .then(function(j){ if(j.error) throw new Error(j.error); });
    }
    // Said under the tiles, where she clicked, not under the orb.
    function said(m, on){ if(!runs) return; runs.textContent = m; runs.classList.toggle('on', !!on); }
    said('Starting ' + label.toLowerCase() + '…', true);
    go(false).then(function(){ b.classList.add('running');
                               said(label + ' is running · the report lands in Jobs', true); })
      .catch(function(err){
        var m = (err && err.message) || String(err);
        if(/you set( for today|[.])/.test(m) && confirm(m + '\n\nRun this one anyway?')){
          go(true).then(function(){ b.classList.add('running');
                                    said(label + ' is running · the report lands in Jobs', true); })
            .catch(function(e2){ said((e2 && e2.message) || String(e2)); });
          return;
        }
        said(m);
      });
  });
}

// ---- "Hear it" under an answer in the box
document.addEventListener('click', function(e){
  var b = e.target.closest && e.target.closest('[data-hear]');
  if(!b) return;
  e.preventDefault(); e.stopPropagation();
  unlock();
  if(b.classList.contains('on')){ hush(); b.classList.remove('on'); b.lastChild.textContent = ' Hear it'; return; }
  var body = b.parentNode && b.parentNode.querySelector('.askbody');
  var text = body ? (body.innerText || body.textContent || '') : '';
  if(!text.trim()) return;
  document.querySelectorAll('[data-hear].on').forEach(function(o){ o.classList.remove('on'); o.lastChild.textContent = ' Hear it'; });
  b.lastChild.textContent = ' Getting the voice…';
  fetch('/api/voice/say', {method: 'POST', headers: {'Content-Type': 'application/json'},
                           body: JSON.stringify({text: text})})
    .then(function(r){ return r.json(); })
    .then(function(j){
      if(j.error || !j.audio){ b.lastChild.textContent = ' ' + (j.error || 'No voice'); return; }
      b.classList.add('on'); b.lastChild.textContent = ' Stop';
      sound(j.audio, function(){ b.classList.remove('on'); b.lastChild.textContent = ' Hear it'; });
    })
    .catch(function(){ b.lastChild.textContent = ' Could not reach the brain'; });
}, true);

// ---- the voice picker (under the hood)
function pickVal(lang){ var s = document.getElementById('vp-' + lang); return s ? s.value : ''; }
function voiceNote(m){ var n = document.querySelector('[data-voicenote]'); if(n) n.textContent = m; }
document.addEventListener('change', function(e){
  var s = e.target.closest && e.target.closest('[data-voiceset]');
  if(!s) return;
  var body = {}; body[s.getAttribute('data-voiceset')] = s.value;
  fetch('/api/voice/set', {method: 'POST', headers: {'Content-Type': 'application/json'},
                           body: JSON.stringify(body)})
    .then(function(r){ return r.json(); })
    .then(function(j){ voiceNote(j.error ? j.error : 'Saved. The next answer speaks this way'); })
    .catch(function(){ voiceNote('Could not reach the brain'); });
});
document.addEventListener('click', function(e){
  var b = e.target.closest && e.target.closest('[data-voicehear]');
  if(!b) return;
  e.preventDefault(); unlock();
  var lang = b.getAttribute('data-voicehear');
  b.disabled = true;
  fetch('/api/voice/preview', {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify({lang: lang, voice: pickVal(lang),
                                                     speed: pickVal('speed') || 1})})
    .then(function(r){ return r.json(); })
    .then(function(j){
      b.disabled = false;
      if(j.error || !j.audio){ voiceNote(j.error || 'No voice'); return; }
      sound(j.audio);
    })
    .catch(function(){ b.disabled = false; voiceNote('Could not reach the brain'); });
});

// ---- the plan meter
function when(iso){
  var d = new Date(iso); if(isNaN(d)) return '';
  return d.toLocaleString([], {weekday: 'short', hour: '2-digit', minute: '2-digit'});
}
function ago(ts){
  var m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 60 ? m + ' min ago' : Math.round(m / 60) + ' h ago';
}
function meter(el, j){
  // Another agent runs the brain: its plan is not one the brain can read
  // (plan_usage.py says off), so no meter at all, not an empty one.
  if(j.off){ el.innerHTML = ''; el.hidden = true; return; }
  var w = j.week, f = j.five_hour, pct = w ? Math.round(w.pct) : 0;
  // data-full-at: one quiet line until the week passes that share, then the card
  var full = el.getAttribute('data-full-at');
  if(full !== null) el.classList.toggle('slim', pct < +full);
  var slim = el.classList.contains('slim');
  if(!w && !f){
    el.innerHTML = slim ? '' : '<p class="pmnone">No reading from your plan yet: ' + esc(j.why || 'try later') + '</p>';
    el.hidden = slim; return;
  }
  var tone = pct >= 90 ? ' bad' : pct >= 75 ? ' wait' : '';
  var tip = 'Your Claude plan, the same numbers /usage shows in Claude Code'
            + (j.fresh ? '' : '. Last known ' + ago(j.at) + (j.why ? ' (' + j.why + ')' : ''));
  var bar = '<span class="pmbar' + tone + '" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'
            + pct + '" aria-label="This week’s plan used"><i style="width:' + Math.min(100, pct) + '%"></i></span>';
  el.title = tip;
  if(slim){
    el.innerHTML = '<span>Plan</span>' + bar + '<b>' + pct + '%</b><span>this week'
      + (f ? ' · 5h ' + Math.round(f.pct) + '%' : '') + '</span>';
  } else {
    el.innerHTML = '<div class="pmhead"><span>Claude · this week</span>'
      + (j.fresh ? '' : '<span class="pmold">last known</span>') + '</div>'
      + '<div class="pmrow"><b class="pmnum">' + pct + '</b><span class="pmunit">% used</span></div>' + bar
      + '<div class="pmfoot">'
      // the reset first, beside the week it belongs to (it read as the five-hour one's)
      + (w && w.resets ? 'Week resets ' + esc(when(w.resets)) : '')
      + (f ? (w && w.resets ? ' · five' : 'Five') + '-hour window ' + Math.round(f.pct) + '%' : '')
      + '</div>';
  }
  el.hidden = false;
}
function meters(){
  var els = document.querySelectorAll('[data-planmeter]');
  if(!els.length || location.protocol === 'file:') return;
  fetch('/api/plan-usage').then(function(r){ return r.json(); })
    .then(function(j){ els.forEach(function(el){ meter(el, j); }); })
    .catch(function(){});
}
meters();
setInterval(function(){ if(!document.hidden) meters(); }, 5 * 60 * 1000);
})();
"""


def button_html():
    """The bar's Talk button: a small live orb in a ring. Tap it and speak."""
    import agents
    return agents.say('<button class="vorbbtn needs-server" data-talk="1" data-state="idle" '
            'title="Talk to the brain, and hear it answer" '
            'aria-label="Talk to the brain">'
            '<span class="vorbring" aria-hidden="true"><canvas class="vorbmini">'
            '</canvas></span><span class="vorbtxt">Talk</span>'
            '<span class="vorbstate" aria-hidden="true">Claude &middot; idle</span>'
            '</button>')


def _e(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _three(today_md):
    """[(text, done)] from today.md's "Do these three", said short: the
    part before a dash, no duration, no markdown."""
    m = re.search(r"##\s*Do these three\n(.*?)(?=\n##|\Z)", today_md or "", re.S)
    out = []
    for ln in (m.group(1) if m else "").split("\n"):
        t = re.match(r"^\s*-\s*\[([ xX])\]\s*(.+)$", ln)
        if not t:
            continue
        text = re.split(r"\s+[—–]\s+", t.group(2))[0]
        text = re.sub(r"\s*~\s?\d+(?:\.\d+)?\s?[mh]\b.*$", "", text)
        text = re.sub(r"\s*\((?:due|waiting|at)\b[^)]*\)", "", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`]", "", text).strip()
        out.append((text, t.group(1) in "xX"))
    return out[:3]


SKILLS = [("today", "Plan today"), ("brief", "Catch me up"),
          ("queue", "Work the queue"), ("wrap", "Wrap up")]


def _next(next_md):
    """[(title, detail)] from next.md's numbered list: the bold title and
    the first clause after the dash, said short."""
    body = (next_md or "").split("\n## ")[0]
    out = []
    for m in re.finditer(r"(?ms)^\d+\.\s+(.*?)(?=^\d+\.\s|^---|\Z)", body):
        item = " ".join(m.group(1).split())
        t = re.match(r"\*\*(.+?)\*\*\s*(?:[—–-]\s*)?(.*)$", item)
        title, rest = (t.group(1), t.group(2)) if t else (item, "")
        rest = re.split(r"(?<=[.;])\s|\s[—–]\s|\s\(", rest)[0].rstrip(" .;")
        if len(rest) > 110:
            rest = rest[:108].rsplit(" ", 1)[0] + "…"
        out.append((re.sub(r"[*_`]", "", title).strip(), re.sub(r"[*_`]", "", rest)))
    return out[:3]


def deck_html(today_md, countdowns, place="", greeting="", next_md="",
              hood="#/hood"):
    """Orbit's deck: the first screen of Today in that skin, and nowhere
    else (`skinx` keeps skin furniture hidden unless a skin shows it). Every
    line on it is real; tapping the orb (or Space) talks; the whole of Today
    goes on underneath. `countdowns` is build.countdown_rows(today)."""
    three = _three(today_md)
    done = sum(1 for _, d in three if d)
    items = "".join(
        f'<li class="{"done" if d else ""}"><i aria-hidden="true"></i>'
        f'<a href="#" data-deckjump="today" title="{_e(t)}">{_e(t)}</a></li>'
        for t, d in three
    ) or '<li class="none">No plan written yet</li>'
    counts = "".join(
        f'<li><b>{n}</b><span>{"day" if n == 1 else "days"} &middot; {_e(lab)}</span></li>'
        for n, lab, _when, _d in (countdowns or [])[:3] if n > 0)
    nxt = _next(next_md)
    nexthtml = ""
    if nxt:
        (t1, d1), more = nxt[0], nxt[1:]
        nexthtml = (
            '<section class="decksec decknext">'
            '<h3 class="decklab" data-decknextlab>Your next hour</h3>'
            f'<p class="decknexttitle">{_e(t1)}</p>'
            + (f'<p class="decknextwhy">{_e(d1)}</p>' if d1 else "")
            + ('<ul class="decknextmore">' + "".join(
                f'<li>{_e(t)}</li>' for t, _d in more) + "</ul>" if more else "")
            + '</section>')
    tiles = "".join(
        f'<button class="decktile" data-skill-run="{job}" data-label="{_e(name)}">'
        f'{_e(name)}<i aria-hidden="true">&rarr;</i></button>' for job, name in SKILLS)
    now = datetime.now()
    # Each fact once (her ask, 29 Sep): the bar already says synced and
    # idle, the day's line says the count, so no status line up here; the
    # place rides under the clock.
    alldone = bool(three) and done == len(three)
    return (
        '<section class="skinx skinx-deck deck" data-state="idle"'
        + (' data-alldone="1"' if alldone else "") + ' aria-label="Deck">'
        '<div class="deckbar">'
        f'<p class="deckclock" data-deckclock data-place="{_e(place)}"><b>{now:%H:%M}</b>'
        f'<small><span class="deckdate">{now:%a} {now:%d} {now:%b}'
        + (' &middot; ' if place else "") + '</span>' + _e(place) + '</small></p>'
        '</div>'
        '<div class="deckgrid">'
        '<aside class="deckside deckleft">'
        '<section class="decksec"><h3 class="decklab">Today <span>top 3</span></h3>'
        f'<ul class="deckthree">{items}</ul></section>'
        '<section class="decksec deckusage"><div class="planmeter slim" data-planmeter '
        'data-full-at="70" hidden></div></section>'
        + (f'<section class="decksec"><h3 class="decklab">Counting down</h3>'
           f'<ul class="deckcount">{counts}</ul></section>' if counts else "")
        + '</aside>'
        '<div class="deckcore">'
        '<button class="deckorbbtn" aria-label="Talk to the brain">'
        '<canvas class="deckorb" aria-hidden="true"></canvas></button>'
        f'<p class="deckgreet">{_e(greeting)}</p>'
        '<p class="decksub" role="status">Tap the orb or press Space to talk</p>'
        '<div class="deckpills" aria-hidden="true">'
        '<span data-s="idle" class="on">Idle</span><span data-s="listening">Listening</span>'
        '<span data-s="thinking">Thinking</span><span data-s="speaking">Speaking</span></div>'
        '<div class="decklog" aria-live="polite"></div>'
        '<button class="deckend" type="button" hidden>End the conversation</button>'
        '</div>'
        '<aside class="deckside deckright">'
        + nexthtml +
        '<section class="decksec"><h3 class="decklab">Skills <span>quick access</span></h3>'
        f'<div class="decktiles">{tiles}</div>'
        f'<a class="deckall" href="{hood}">All jobs <span aria-hidden="true">&nearr;</span></a>'
        '<p class="deckfine" data-deckruns>Runs in the background &middot; reports land in Jobs</p>'
        '</section>'
        '</aside>'
        '</div>'
        '<a class="deckmore" href="#" data-deckjump="today">Today&rsquo;s plan <span aria-hidden="true">&darr;</span></a>'
        '</section>')


def block():
    import agents
    return ("<style>" + CSS + "</style>" + agents.say(HTML)
            + "<script>" + agents.say(JS) + "</script>")
