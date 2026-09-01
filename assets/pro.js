/* Licentia Pro — decides whether a page wears the paid surface.

   Entitlement comes from the account, not from the browser. The order is:

     1. app_metadata.tier   — set server side, users cannot touch it. When
                              billing exists, the payment webhook writes here
                              and this is the only branch that should remain.
     2. user_metadata.tier  — writable by the account holder, so it is a label
                              rather than a lock. Fine while Pro is being
                              fitted out; delete this branch once (1) is live.
     3. ?pro=1              — a preview for one tab only. Deliberately kept in
                              sessionStorage so it dies with the tab and can
                              never leak into a normal signed-in session.

   Anything else gets Ember. No account, no tier, no gold.  */
(function(){
  var PREVIEW = 'LICENTIA_PRO_PREVIEW';
  var URL_ = 'https://sopzbiuwakowbuqgwpmg.supabase.co';
  var KEY = 'sb_publishable_x-g6QbE71nKThHN66Mz1kQ_16NXoj5j';

  // the old persistent flag let gold stick to accounts that never paid
  try { localStorage.removeItem('LICENTIA_PRO'); } catch (e) {}

  function previewOn(){
    var q = window.location.search;
    try {
      if (/[?&]pro=1/.test(q)) { sessionStorage.setItem(PREVIEW, '1'); return true; }
      if (/[?&]pro=0/.test(q)) { sessionStorage.removeItem(PREVIEW); return false; }
      return sessionStorage.getItem(PREVIEW) === '1';
    } catch (e) { return /[?&]pro=1/.test(q); }
  }

  function apply(on){
    if (!document.body) return;
    document.body.classList.toggle('pro', !!on);
  }

  // Read the tier straight off the stored session so the page can dress itself
  // before any module finishes loading; no flash of the wrong theme.
  function tierFromStoredSession(){
    try {
      for (var i = 0; i < localStorage.length; i++){
        var k = localStorage.key(i);
        if (k.indexOf('sb-') !== 0 || k.indexOf('-auth-token') === -1) continue;
        var raw = JSON.parse(localStorage.getItem(k));
        var u = raw && (raw.user || (raw.currentSession && raw.currentSession.user));
        if (!u) continue;
        return (u.app_metadata && u.app_metadata.tier) ||
               (u.user_metadata && u.user_metadata.tier) || null;
      }
    } catch (e) {}
    return null;
  }

  function decide(){
    if (previewOn()) { apply(true); return; }
    apply(tierFromStoredSession() === 'pro');
  }

  if (document.body) decide();
  else document.addEventListener('DOMContentLoaded', decide);

  // confirm against the server, in case the stored session is stale
  window.addEventListener('load', function(){
    if (previewOn()) return;
    fetch(URL_ + '/auth/v1/user', {
      headers: { apikey: KEY, Authorization: 'Bearer ' + (function(){
        try {
          for (var i = 0; i < localStorage.length; i++){
            var k = localStorage.key(i);
            if (k.indexOf('sb-') === 0 && k.indexOf('-auth-token') > -1){
              var raw = JSON.parse(localStorage.getItem(k));
              return (raw && (raw.access_token || (raw.currentSession && raw.currentSession.access_token))) || '';
            }
          }
        } catch (e) {}
        return '';
      })() }
    }).then(function(r){ return r.ok ? r.json() : null; })
      .then(function(u){
        if (!u) { apply(false); return; }
        var tier = (u.app_metadata && u.app_metadata.tier) ||
                   (u.user_metadata && u.user_metadata.tier) || null;
        apply(tier === 'pro');
      })
      .catch(function(){});
  });
})();

/* ---------------------------------------------------------------------------
   Mobile navigation.

   Eight links wrap into three rows on a phone, so the bar was eating 191px of
   a 844px screen before anything else appeared. Below 820px the links collapse
   behind a button and open as a sheet.

   This lives here because every page already loads this file; the alternative
   was editing eight pages and keeping eight copies in step.
--------------------------------------------------------------------------- */
(function(){
  var BREAK = 820;

  function css(){
    if (document.getElementById('licentia-mobile-nav')) return;
    var s = document.createElement('style');
    s.id = 'licentia-mobile-nav';
    s.textContent = [
      '.navtoggle{display:none;}',
      '@media (max-width:' + BREAK + 'px){',
      '  nav{flex-wrap:nowrap; gap:12px; padding:11px 16px; position:sticky; top:0;}',
      '  .navtoggle{display:inline-flex; flex-direction:column; justify-content:center;',
      '    gap:5px; width:42px; height:38px; padding:0 9px; cursor:pointer;',
      '    background:none; border:1px solid var(--line-strong); border-radius:10px;}',
      '  .navtoggle span{display:block; height:2px; border-radius:2px; background:var(--ink);',
      '    transition:transform .22s ease, opacity .18s ease;}',
      '  .navtoggle[aria-expanded="true"] span:nth-child(1){transform:translateY(7px) rotate(45deg);}',
      '  .navtoggle[aria-expanded="true"] span:nth-child(2){opacity:0;}',
      '  .navtoggle[aria-expanded="true"] span:nth-child(3){transform:translateY(-7px) rotate(-45deg);}',
      '  .navlinks{position:absolute; left:0; right:0; top:100%;',
      '    flex-direction:column; align-items:stretch; gap:0; padding:6px 10px 12px;',
      '    background:var(--paper); border-bottom:1px solid var(--line);',
      '    box-shadow:0 18px 40px -26px rgba(28,34,48,0.8);',
      '    max-height:0; overflow:hidden; opacity:0; pointer-events:none;',
      '    transition:max-height .26s ease, opacity .2s ease;}',
      '  nav.open .navlinks{max-height:78vh; overflow-y:auto; opacity:1; pointer-events:auto;}',
      '  .navlinks a{padding:13px 12px; font-size:15.5px; border-radius:9px;}',
      '  .navlinks a::after{display:none;}',
      '  .navlinks a.active{background:rgba(255,107,53,0.10); color:var(--ember-deep);}',
      '  body.pro .navlinks a.active{background:rgba(201,162,39,0.16); color:var(--gold-deep);}',
      '}',
      '@media (min-width:' + (BREAK + 1) + 'px){ nav .navlinks{max-height:none; opacity:1;} }'
    ].join('\n');
    document.head.appendChild(s);
  }

  function build(){
    var nav = document.querySelector('nav');
    var links = nav && nav.querySelector('.navlinks');
    if (!nav || !links || nav.querySelector('.navtoggle')) return;

    var btn = document.createElement('button');
    btn.className = 'navtoggle';
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Menu');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<span></span><span></span><span></span>';
    // sits after the wordmark so the tap target is where a thumb expects it
    nav.insertBefore(btn, links);

    function setOpen(on){
      nav.classList.toggle('open', on);
      btn.setAttribute('aria-expanded', on ? 'true' : 'false');
    }
    btn.addEventListener('click', function(e){
      e.stopPropagation();
      setOpen(!nav.classList.contains('open'));
    });
    // choosing a destination closes the sheet
    links.addEventListener('click', function(e){
      if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('click', function(e){
      if (nav.classList.contains('open') && !nav.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') setOpen(false);
    });
    window.addEventListener('resize', function(){
      if (window.innerWidth > BREAK) setOpen(false);
    });
  }

  function start(){ css(); build(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();


/* Phone polish. Layouts that hold up on a laptop go thin at 390px: figures
   split across uneven rows, four column grids squeezing three words per
   line, chips sized for a wide strip. */
(function(){
  if (document.getElementById("licentia-phone")) return;
  var s = document.createElement("style");
  s.id = "licentia-phone";
  s.textContent = "@media (max-width:640px){\n  .home-stats{display:grid; grid-template-columns:1fr 1fr; row-gap:18px; max-width:340px;}\n  .home-stat{padding:0 10px;}\n  .home-stat + .home-stat::before{display:none;}\n  .home-doors{grid-template-columns:1fr; gap:10px;}\n  .door{padding:15px 17px;}\n  .mq-item{width:150px; height:78px; padding:0 12px;}\n  .cmp{grid-template-columns:1fr 1fr; gap:10px;}\n  .cc .then{font-size:26px;}\n  .totals{grid-template-columns:1fr 1fr;}\n  .recs{grid-template-columns:1fr;}\n  .opts{grid-template-columns:1fr;}\n  .miniadd, .addform{grid-template-columns:1fr; gap:10px;}\n  .miniadd .primary, .addform .primary{width:100%;}\n  .sbtn{padding:8px 12px; font-size:12px;}\n  .legend{flex-direction:column; gap:10px;}\n  .chartwrap{overflow-x:auto;}\n  #chart{min-width:520px;}\n  table{display:block; overflow-x:auto;}\n  .split{grid-template-columns:1fr;}\n  .pitch{padding:26px 20px;}\n  .card{max-width:100%;}\n  .idcard{gap:14px; padding:18px;}\n  .avatar{width:60px; height:60px; font-size:24px;}\n  .foot-in{flex-direction:column; align-items:flex-start; gap:22px;}\n}\n@media (max-width:430px){\n  .cmp{grid-template-columns:1fr;}\n  .totals{grid-template-columns:1fr;}\n}";
  (document.head || document.documentElement).appendChild(s);
})();


/* Second phone pass: the provider strip needs the full width of the screen,
   the footer reads better centred, and the Learn artwork was drawn for a
   laptop and collided with its own captions on a handset. */
(function(){
  if (document.getElementById("licentia-phone-2")) return;
  var s = document.createElement("style");
  s.id = "licentia-phone-2";
  s.textContent = "@media (max-width:640px){\n  .marquee{width:100vw; max-width:100vw; margin-left:calc(50% - 50vw); margin-right:calc(50% - 50vw);\n    border-radius:0;\n    -webkit-mask-image:linear-gradient(90deg,transparent,#000 10%,#000 90%,transparent);\n    mask-image:linear-gradient(90deg,transparent,#000 10%,#000 90%,transparent);}\n  .mq-item{width:142px; height:74px; padding:0 12px;}\n  .mq-track{gap:10px;}\n  .site-foot{padding:28px 20px 24px;}\n  .foot-in{flex-direction:column; align-items:center; text-align:center; gap:24px;}\n  .foot-word{align-items:center; max-width:32ch;}\n  .foot-stats{justify-content:center; gap:20px 26px;}\n  .fs{min-width:88px;}\n  .foot-small{text-align:center;}\n}\n@media (max-width:640px){\n  .stop{padding:34px 16px;}\n  .stop-inner{gap:20px;}\n  .stop h3{font-size:clamp(22px,6.4vw,30px); line-height:1.15;}\n  .lead{font-size:15px; line-height:1.6;}\n  .stop-art{height:250px;}\n  .stop-art svg{max-height:250px; max-width:100%;}\n  .ex-body{height:290px;}\n  .ex-head{font-size:15px;}\n  .basket-wrap{width:min(258px,84vw);}\n  .scene{padding:0 10px;}\n  .calc-row{flex-wrap:wrap; gap:8px;}\n  .calc-cell{flex:1 1 40%;}\n  .ex-dots-wrap{transform:scale(0.82); transform-origin:center;}\n  .price, .premium, .buyer{font-size:13px;}\n  .intro{padding:26px 18px;}\n}\n@media (max-width:430px){\n  .stop-art{height:214px;}\n  .stop-art svg{max-height:214px;}\n  .ex-body{height:262px;}\n  .basket-wrap{width:min(228px,82vw);}\n  .mq-item{width:128px; height:66px;}\n}";
  (document.head || document.documentElement).appendChild(s);
})();
