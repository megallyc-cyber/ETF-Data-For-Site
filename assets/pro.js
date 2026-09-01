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


/* The strip on a handset. The logo box inside each chip was pinned to 132px
   while the chip shrank below that, so marks hung outside their cards. The
   box now flexes and the chips are big enough to read. */
(function(){
  if (document.getElementById("licentia-phone-3")) return;
  var s = document.createElement("style");
  s.id = "licentia-phone-3";
  s.textContent = "@media (max-width:640px){\n  .mq-item{width:176px; height:94px; padding:0 14px; gap:10px; overflow:hidden;}\n  .mq-logo{width:auto; max-width:104px; height:34px; flex:0 1 auto;}\n  .mq-logo svg, .mq-logo img{max-width:104px; max-height:34px;}\n  .mq-name{font-size:15px; max-width:104px;}\n  .mq-n{font-size:12px;}\n  .mq-track{gap:10px;}\n}\n@media (max-width:430px){\n  .mq-item{width:162px; height:88px; padding:0 12px;}\n  .mq-logo{max-width:94px; height:31px;}\n  .mq-logo svg, .mq-logo img{max-width:94px; max-height:31px;}\n  .mq-name{font-size:14px; max-width:94px;}\n}";
  (document.head || document.documentElement).appendChild(s);
})();












/* Reduce Motion freezes the strip by design, so make it swipeable there.
   Learn drawings set their own height; the last slide is given room so its
   sum stops spilling over the text above and the dots below. */
(function(){
  if (document.getElementById("licentia-phone-4")) return;
  var s = document.createElement("style");
  s.id = "licentia-phone-4";
  s.textContent = ".mq-logo{display:flex; align-items:center; justify-content:center; overflow:hidden;}\n.mq-logo svg{width:100%; height:100%; max-width:100%; max-height:100%;}\n.mq-logo img{width:auto; height:100%; max-width:100%; object-fit:contain;}\n.fam-logo svg{width:100%; height:100%; max-width:100%; max-height:100%;}\n.fam-logo img{width:auto; height:100%; max-width:100%; object-fit:contain;}\n.issuer-logo svg{width:100%; height:100%; max-width:100%; max-height:100%;}\n.mq-track{will-change:transform; -webkit-backface-visibility:hidden; backface-visibility:hidden;}\n@media (prefers-reduced-motion: reduce){\n  .marquee{overflow-x:auto; -webkit-overflow-scrolling:touch;\n    scroll-snap-type:x proximity; -webkit-mask-image:none; mask-image:none;}\n  .mq-track{animation:none !important; width:max-content;}\n  .mq-item{scroll-snap-align:center;}\n}\n@media (max-width:900px){\n  .marquee{-webkit-mask-image:none !important; mask-image:none !important;}\n  .stop-num, .stop h3, .stop .lead, .stop .foot, .stop-art, .stop-text{\n    opacity:1 !important; transform:none !important;}\n  .draw, .fade, .grow{opacity:1 !important; transform:none !important;}\n  .stop-inner{grid-template-columns:1fr !important; grid-template-rows:auto auto !important; gap:18px;}\n  .stop .stop-text{grid-row:1 !important; grid-column:1 !important;}\n  .stop .stop-art{grid-row:2 !important; grid-column:1 !important;\n    position:relative; width:100%; height:auto !important; min-height:0; display:block;}\n  .stop .stop-art svg{width:100% !important; height:auto !important;\n    max-width:100%; max-height:none !important; display:block; margin:0 auto;}\n  .stop.right .stop-art, .stop.left .stop-art{order:0;}\n  .stop{padding:30px 16px;}\n  .ex-track{padding:0 8px;}\n  .ex-stage{width:100% !important; max-width:100% !important; padding:0 0 8px;}\n  .ex-head{padding:18px 12px 0;}\n  .ex-arrow{width:42px !important; height:42px !important;\n    top:auto !important; bottom:4px !important; z-index:3;}\n  .ex-arrow.prev{left:6px !important;} .ex-arrow.next{right:6px !important;}\n  .ex-body{height:272px !important; padding-bottom:6px; overflow:hidden;}\n  .scene{padding:0 6px;}\n  .calc-row{flex-wrap:nowrap; gap:6px; align-items:stretch; width:100%;}\n  .calc-cell{padding:10px 8px; min-width:0;}\n  .calc-num{font-size:23px !important; line-height:1.1;}\n  .mono-label{font-size:8.5px !important; letter-spacing:0.08em; line-height:1.3;}\n  .calc-total{padding:12px 10px !important; margin-top:8px;}\n  .calc-total .calc-num{font-size:27px !important;}\n  .basket-wrap{width:min(200px,66vw) !important;}\n}\n@media (max-width:640px){\n  .marquee{border-radius:0;}\n  .mq-item{width:186px; height:96px; padding:0 14px; gap:10px; overflow:hidden;}\n  .mq-logo{width:112px; max-width:112px; height:38px; flex:0 0 auto;}\n  .mq-name{font-size:15px; max-width:112px;}\n}\n@media (max-width:430px){\n  .mq-item{width:170px; height:90px;}\n  .mq-logo{width:100px; max-width:100px; height:34px;}\n  .mq-name{font-size:14px; max-width:100px;}\n  .ex-body{height:264px !important;}\n  .calc-num{font-size:21px !important;}\n  .calc-total .calc-num{font-size:25px !important;}\n  .basket-wrap{width:min(180px,62vw) !important;}\n}";
  (document.head || document.documentElement).appendChild(s);
})();




/* ---------------------------------------------------------------------------
   Round of fixes from testing on a handset.
--------------------------------------------------------------------------- */
(function(){
  /* The strip is animated on a track sized with width:max-content. iOS Safari
     resolves that inconsistently inside a flex row, and a short track makes the
     translate barely move. Measure the chips and set real pixels instead, then
     set the duration from that width so the speed is the same on every screen
     rather than crawling on a long track. */
  function sizeTrack(){
    var track = document.getElementById('mqTrack') || document.querySelector('.mq-track');
    if (!track || !track.children.length) return;
    var kids = track.children, total = 0;
    for (var i = 0; i < kids.length; i++) total += kids[i].getBoundingClientRect().width;
    var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || 0) || 0;
    total += gap * (kids.length - 1);
    if (!(total > 0)) return;
    track.style.width = Math.round(total) + 'px';
    // roughly 95 pixels a second: moving plainly within a second of landing
    var seconds = Math.max(14, Math.round((total / 2) / 95));
    track.style.animationDuration = seconds + 's';
  }
  function start(){
    sizeTrack();
    setTimeout(sizeTrack, 1200);
    setTimeout(sizeTrack, 3000);
    var t;
    window.addEventListener('resize', function(){ clearTimeout(t); t = setTimeout(sizeTrack, 200); }, {passive:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();

  if (document.getElementById('licentia-fixups')) return;
  var s = document.createElement('style');
  s.id = 'licentia-fixups';
  s.textContent = [
    /* letter spacing is added after the last character too, so a centred mono
       string sits half a space left of true centre */
    '.basket span{text-indent:2.2px;}',
    /* nothing on the site should scroll sideways */
    'html, body{max-width:100%; overflow-x:hidden;}',
    '@media (max-width:900px){',
    /* the bird already sits in the bar; a second one under it is a repeat */
    '  .home-bird{display:none;}',
    /* the coloured edge on each chip was a tell, not a signal */
    '  .mq-item{border-left:1px solid var(--line) !important;}',
    '}',
    '.mq-item{border-left:1px solid var(--line) !important;}'
  ].join('\n');
  (document.head || document.documentElement).appendChild(s);
})();
