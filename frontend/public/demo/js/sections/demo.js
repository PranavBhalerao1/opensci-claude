(function(){
  "use strict";
  var app = window.OpenScientist = window.OpenScientist || {};

  var ACCEL = 1000;          // simulated-compute-time multiplier
  var TICK_MS = 100;         // run-loop cadence
  var WORKERS_PER_TEAM = 5;
  var SPLIT_DURATION = 2600;
  var FOCUS_DURATION = 850;
  var MARCH_STEPS = 60;

  var RING_R = [2.05, 1.9, 2.15, 1.95, 2.1];
  var RING_Y = [0.55, -0.46, 0.32, -0.6, 0.08];
  var K_MERGED = 0.6;
  var K_SPLIT = 0.15;
  var RAD_LEAD_MERGED = 0.34; var RAD_LEAD_SPLIT = 0.26;
  var RAD_WORKER_MERGED = 0.26; var RAD_WORKER_SPLIT = 0.13;
  var RADIAL_C = 2 * Math.PI * 24;
  var RING_C = 2 * Math.PI * 44;

  var LIT_TERMS = ['posture AND cognitive load', 'standing desk attention', 'sit-stand workstation focus', 'ergonomics field study', 'afternoon vigilance decline'];
  var SOURCES = ['PubMed', 'bioRxiv', 'Google Scholar', 'Semantic Scholar'];
  var SECTIONS = ['Introduction', 'Methods', 'Results', 'Discussion', 'Limitations'];

  var TEAMS = [
    {
      id:'lit', name:'Literature Agent', hex:'#3ad0d6', rgb:[0.227,0.816,0.839],
      task:'Surveying prior work on posture and cognition',
      start:0, duration:6500,
      findings:[
        '18 papers screened across PubMed and Google Scholar',
        '3 relevant meta-analyses retained',
        'Gap found: no field study during real workdays'
      ],
      logs:[
        function(n){ return 'query "' + LIT_TERMS[n % LIT_TERMS.length] + '" → ' + (140 + (n * 53) % 380) + ' hits'; },
        function(n){ return 'fetching ' + SOURCES[(n + 1) % SOURCES.length] + ' index shard ' + (n % 12); },
        function(n){ return 'embedding abstract batch ' + (n % 40) + '/40'; },
        function(n){ return 'dedup pass: ' + (2 + (n * 7) % 14) + ' near-duplicates removed'; },
        function(n){ return 'relevance score updated for ' + (10 + (n * 11) % 90) + ' candidates'; }
      ]
    },
    {
      id:'data', name:'Data Agent', hex:'#5a93ea', rgb:[0.353,0.576,0.918],
      task:'Assembling the pilot cohort dataset',
      start:1800, duration:7200,
      findings:[
        '24 participants across 10 workdays',
        'Wearable focus-timer logs merged with desk-position sensors',
        '1,880 focus intervals compiled'
      ],
      logs:[
        function(n){ return 'parsing wearable export ' + (n % 24 + 1) + '/24'; },
        function(n){ return 'sensor stream desk-' + (n % 24 + 1) + ' resampled @ 1Hz'; },
        function(){ return 'merging focus-timer log with desk-position log'; },
        function(n){ return 'imputing ' + (1 + (n * 3) % 9) + ' missing samples, participant P' + ((n % 24) + 1); },
        function(n){ return (1200 + (n * 97) % 600) + ' focus intervals compiled'; }
      ]
    },
    {
      id:'analysis', name:'Analysis Agent', hex:'#a78bfa', rgb:[0.655,0.545,0.980],
      task:'Comparing standing vs. seated focus sessions',
      start:8200, duration:9200,
      findings:[
        'Paired t-test run across matched afternoons',
        'Standing sessions ran 9% longer before a break',
        'Effect holds after controlling for caffeine intake'
      ],
      logs:[
        function(n){ return 'bootstrap iter ' + ((n * 37) % 5000) + '/5000'; },
        function(n){ return 'fitting mixed-effects model, fold ' + (n % 10 + 1) + '/10'; },
        function(){ return 'residual check: within tolerance'; },
        function(n){ return 'computing 95% CI, effect size d=' + (0.3 + (n % 40) * 0.01).toFixed(2); },
        function(){ return 'controlling for covariate: caffeine intake'; }
      ]
    },
    {
      id:'writer', name:'Writer Agent', hex:'#f2b13f', rgb:[0.949,0.694,0.247],
      task:'Writing up the findings',
      start:15500, duration:6800,
      findings:[
        'Outline generated from the analysis results',
        'Brief drafted, 640 words',
        'Charts embedded from the analysis run'
      ],
      logs:[
        function(n){ return 'drafting section "' + SECTIONS[n % SECTIONS.length] + '"'; },
        function(n){ return 'expanding outline node ' + (n % 18 + 1); },
        function(n){ return 'inserting figure reference [' + (n % 6 + 1) + ']'; },
        function(n){ return 'style pass: ' + (3 + (n * 5) % 22) + ' sentences revised'; },
        function(n){ return (420 + (n * 29) % 420) + ' words drafted'; }
      ]
    },
    {
      id:'verify', name:'Verification Agent', hex:'#4fd08a', rgb:[0.310,0.816,0.541],
      task:'Verifying claims against sources',
      start:19800, duration:4600,
      findings:[
        '6 claims checked against raw data',
        '1 claim softened after re-check',
        'references.bib created, 9 citations verified'
      ],
      logs:[
        function(n){ return 'cross-checking claim #' + (n % 9 + 1) + ' against source'; },
        function(n){ return 'recomputing statistic for citation [' + (n % 9 + 1) + ']'; },
        function(n){ return 'citation graph updated: ' + (30 + (n * 3) % 80) + ' edges'; },
        function(n){ return 'confidence check passed for claim #' + (n % 9 + 1); },
        function(n){ return 'references.bib entry ' + (n % 9 + 1) + '/9 verified'; }
      ]
    }
  ];

  var AGENTS = [];
  TEAMS.forEach(function(team, ti){
    AGENTS.push({
      index: AGENTS.length, kind:'lead', teamIndex:ti, teamName:team.name,
      id: team.id.toUpperCase(), name: team.name, hex: team.hex, rgb: team.rgb,
      task: team.task, findings: team.findings, logTemplates: team.logs,
      start: team.start, duration: team.duration
    });
    for(var w = 0; w < WORKERS_PER_TEAM; w++){
      var wDuration = Math.round(team.duration * (0.55 + 0.09 * w));
      AGENTS.push({
        index: AGENTS.length, kind:'worker', teamIndex:ti, teamName:team.name, workerSlot:w,
        id: team.id + '-' + (w + 1), name: team.id.toUpperCase() + '-' + (w + 1),
        hex: team.hex, rgb: team.rgb, logTemplates: team.logs,
        start: team.start + w * 350, duration: wDuration
      });
    }
  });
  var BALL_COUNT = AGENTS.length; // 30
  var leadAgents = AGENTS.filter(function(a){ return a.kind === 'lead'; });
  var RUN_DURATION = AGENTS.reduce(function(m, a){ return Math.max(m, a.start + a.duration); }, 0);

  function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, t){ return a + (b - a) * t; }
  function easeInOutCubic(t){ return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function sub(a, b){ return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]; }
  function dot3(a, b){ return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
  function length3(a){ return Math.sqrt(dot3(a, a)); }
  function normalize3(a){ var l = length3(a) || 1; return [a[0]/l, a[1]/l, a[2]/l]; }
  function cross3(a, b){ return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]; }
  function lerp3(a, b, t){ return [lerp(a[0],b[0],t), lerp(a[1],b[1],t), lerp(a[2],b[2],t)]; }
  function pad2(n){ return (n < 10 ? '0' : '') + n; }
  function formatClock(ms){
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    return pad2(h) + ':' + pad2(m) + ':' + pad2(s);
  }
  function formatNumber(n){ return Math.floor(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  function radiusFor(agent, spreadEased){
    var merged = agent.kind === 'lead' ? RAD_LEAD_MERGED : RAD_WORKER_MERGED;
    var split = agent.kind === 'lead' ? RAD_LEAD_SPLIT : RAD_WORKER_SPLIT;
    return lerp(merged, split, spreadEased);
  }

  function ballCenter(agent, t, spreadEased){
    var i = agent.index;
    var clustAng = t * 0.4 * (0.6 + i * 0.04) + i * 1.1;
    var clustR = 0.4 + 0.08 * Math.sin(t * 0.6 + i * 0.8);
    var cx0 = Math.cos(clustAng) * clustR;
    var cy0 = Math.sin(clustAng * 1.3 + i) * 0.24;
    var cz0 = Math.sin(clustAng) * clustR;

    var leadAng = agent.teamIndex * (Math.PI * 2 / 5) + 0.4;
    var leadX = Math.cos(leadAng) * RING_R[agent.teamIndex];
    var leadY = RING_Y[agent.teamIndex];
    var leadZ = Math.sin(leadAng) * RING_R[agent.teamIndex];

    var cx1, cy1, cz1;
    if(agent.kind === 'lead'){
      var wob = 0.1;
      cx1 = leadX + Math.cos(t * 0.5 + i) * wob;
      cy1 = leadY + Math.sin(t * 0.6 + i * 1.7) * wob;
      cz1 = leadZ + Math.sin(t * 0.45 + i * 2.2) * wob;
    } else {
      var orbitAng = agent.workerSlot * (Math.PI * 2 / 5) + agent.teamIndex * 0.7 + t * 0.3;
      var orbitR = 0.62;
      cx1 = leadX + Math.cos(orbitAng) * orbitR;
      cy1 = leadY + Math.sin(orbitAng * 1.4) * orbitR * 0.55;
      cz1 = leadZ + Math.sin(orbitAng) * orbitR;
    }

    return [
      lerp(cx0, cx1, spreadEased),
      lerp(cy0, cy1, spreadEased),
      lerp(cz0, cz1, spreadEased)
    ];
  }

  function computeCamera(elapsed, mouse, focusT, focusCenter, focusRadius){
    var az = elapsed * 0.11 + mouse.x * 0.5;
    var el = 0.3 + mouse.y * 0.2;
    var dist = 4.3;
    var ro = [Math.sin(az) * dist, el * 2.0, Math.cos(az) * dist];
    var ta = [0, 0, 0];
    var zoom = 1.75;

    if(focusT > 0){
      var dir = normalize3(ro);
      var focusDist = 0.55 + (focusRadius || 0.26) * 4.2;
      var focusRo = [
        focusCenter[0] + dir[0] * focusDist,
        focusCenter[1] + dir[1] * focusDist + 0.15,
        focusCenter[2] + dir[2] * focusDist
      ];
      ro = lerp3(ro, focusRo, focusT);
      ta = lerp3(ta, focusCenter, focusT);
      zoom = lerp(zoom, 2.55, focusT);
    }

    var fwd = normalize3(sub(ta, ro));
    var right = normalize3(cross3(fwd, [0, 1, 0]));
    var up = cross3(right, fwd);
    return {ro:ro, right:right, up:up, fwd:fwd, zoom:zoom};
  }

  function projectToScreen(camera, center, cssW, cssH){
    var dir = normalize3(sub(center, camera.ro));
    var a = dot3(dir, camera.right);
    var b = dot3(dir, camera.up);
    var c = dot3(dir, camera.fwd);
    if(c < 0.05) return null;
    var uvx = (camera.zoom / c) * a;
    var uvy = (camera.zoom / c) * b;
    var dist = length3(sub(center, camera.ro));
    return {
      x: cssW / 2 + uvx * cssH,
      y: cssH / 2 - uvy * cssH,
      scale: clamp(4.2 / dist, 0.7, 1.4)
    };
  }

  var vertexSource = 'attribute vec2 aPos;void main(){gl_Position=vec4(aPos,0.0,1.0);}';
  var fragmentSource = [
    'precision highp float;',
    'uniform vec2 uRes;',
    'uniform vec3 uRo;', 'uniform vec3 uRight;', 'uniform vec3 uUp;', 'uniform vec3 uFwd;', 'uniform float uZoom;',
    'uniform float uK;',
    'uniform vec3 uCenters[30];',
    'uniform float uRadii[30];',
    'uniform vec3 uColors[30];',
    'uniform float uFocusIdx;',
    'uniform float uFocusGlow;',
    'float smin(float a, float b, float k){',
    '  float h = clamp(0.5+0.5*(b-a)/k, 0.0, 1.0);',
    '  return mix(b,a,h) - k*h*(1.0-h);',
    '}',
    'float mapDist(vec3 p){',
    '  float d = 1000.0;',
    '  for(int i=0;i<30;i++){',
    '    float dd = length(p-uCenters[i]) - uRadii[i];',
    '    d = smin(d, dd, uK);',
    '  }',
    '  return d;',
    '}',
    'vec3 mapColor(vec3 p, out float glowBoost){',
    '  float best = 1000.0; vec3 col = uColors[0]; float bestIdx = 0.0;',
    '  for(int i=0;i<30;i++){',
    '    float dd = length(p-uCenters[i]) - uRadii[i];',
    '    if(dd < best){ best = dd; col = uColors[i]; bestIdx = float(i); }',
    '  }',
    '  float dim = 1.0;',
    '  glowBoost = 0.0;',
    '  if(uFocusIdx > -0.5){',
    '    if(abs(bestIdx-uFocusIdx) < 0.5){ glowBoost = uFocusGlow; } else { dim = 0.28; }',
    '  }',
    '  return col*dim;',
    '}',
    'vec3 calcNormal(vec3 p){',
    '  vec2 e = vec2(0.0015,0.0);',
    '  return normalize(vec3(',
    '    mapDist(p+e.xyy)-mapDist(p-e.xyy),',
    '    mapDist(p+e.yxy)-mapDist(p-e.yxy),',
    '    mapDist(p+e.yyx)-mapDist(p-e.yyx)',
    '  ));',
    '}',
    'void main(){',
    '  vec2 uv = (gl_FragCoord.xy - 0.5*uRes) / uRes.y;',
    '  vec3 ro = uRo;',
    '  vec3 rd = normalize(uv.x*uRight + uv.y*uUp + uZoom*uFwd);',
    '  float t = 0.0; bool hit = false; vec3 p; float glowAcc = 0.0; int steps = 0;',
    '  for(int i=0;i<' + MARCH_STEPS + ';i++){',
    '    p = ro + rd*t;',
    '    float d = mapDist(p);',
    '    glowAcc += 0.001/(0.02+d*d*4.0);',
    '    if(d < 0.0015){ hit = true; steps = i; break; }',
    '    t += d*0.9; steps = i;',
    '    if(t > 15.0) break;',
    '  }',
    '  vec3 col = vec3(0.0);',
    '  float vgn = smoothstep(1.35, 0.1, length(uv));',
    '  if(hit){',
    '    vec3 n = calcNormal(p);',
    '    vec3 lightDir = normalize(vec3(0.55,0.85,0.4));',
    '    float diff = max(dot(n,lightDir), 0.0);',
    '    float rim = pow(1.0-max(dot(n,-rd),0.0), 4.0);',
    '    float ao = 1.0 - float(steps)/' + MARCH_STEPS + '.0;',
    '    float glowBoost;',
    '    vec3 base = mapColor(p, glowBoost);',
    '    float shade = diff*0.55 + rim*0.3 + ao*0.08 + 0.08;',
    '    col = base*shade + vec3(rim*0.5) + base*glowBoost*0.9;',
    '  } else {',
    '    col = vec3(glowAcc*0.016, glowAcc*0.019, glowAcc*0.025);',
    '  }',
    '  col *= vgn;',
    '  col += vec3(glowAcc*0.004,glowAcc*0.0045,glowAcc*0.006);',
    '  gl_FragColor = vec4(col, 1.0);',
    '}'
  ].join('\n');

  app.initDemo = function initDemo(){
    var stage = document.getElementById('demoStage');
    if(!stage) return;
    var canvas = document.getElementById('demoGL');
    var hotspotsWrap = document.getElementById('demoHotspots');
    var hint = document.getElementById('demoHint');
    var hintText = document.getElementById('demoHintText');
    var replayBtn = document.getElementById('demoReplay');
    var gate = document.getElementById('demoGate');
    var initiateBtn = document.getElementById('demoInitiate');
    var consoleEl = document.getElementById('demoConsole');
    var consoleBody = document.getElementById('demoConsoleBody');
    var clockEl = document.getElementById('demoClock');
    var eventCountEl = document.getElementById('demoEventCount');
    var sparkEl = document.getElementById('demoSpark');
    var panel = document.getElementById('demoPanel');
    var panelInner = document.getElementById('demoPanelInner');
    var backBtn = document.getElementById('demoBack');
    var fallbackList = document.getElementById('demoFallbackList');
    var progressGrid = document.getElementById('demoProgressGrid');
    var overallRing = document.getElementById('demoOverallRing');
    var overallPct = document.getElementById('demoOverallPct');
    var timelineEl = document.getElementById('demoTimeline');
    var timelineClockEl = document.getElementById('demoTimelineClock');
    var resultsSection = document.getElementById('demoResultsSection');
    var chart3dEl = document.getElementById('demoChart3d');
    var lineChartEl = document.getElementById('demoLineChart');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var focusIndex = null;
    var runState = 'idle'; // idle -> running -> complete
    var runStartedAt = 0;
    var tickTimer = null;
    var tickCounter = 0;
    var eventCount = 0;
    var sparkHistory = [];
    var spread = 0, splitting = false, splitStart = 0;

    // Placeholders reassigned once (if) the WebGL scene initializes successfully.
    var renderSceneStatic = function(){};
    var triggerSplit = function(){};
    var setFocusCamera = null;

    function setFocus(idx){
      if(setFocusCamera){ setFocusCamera(idx); return; }
      if(idx === null) closePanel(); else openPanel(idx);
    }

    function currentElapsed(){
      if(runState === 'idle') return 0;
      return clamp(performance.now() - runStartedAt, 0, RUN_DURATION);
    }

    /* ---------------- Panel content ---------------- */

    function openPanel(idx){
      focusIndex = idx;
      fillPanel(AGENTS[idx]);
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      stage.classList.add('is-focused');
    }
    function closePanel(){
      focusIndex = null;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
      stage.classList.remove('is-focused');
    }
    backBtn.addEventListener('click', function(){ setFocus(null); });
    document.addEventListener('keydown', function(e){
      if(e.key === 'Escape' && focusIndex !== null) setFocus(null);
    });

    function fillPanel(agent){
      var elapsed = currentElapsed();
      var t = clamp((elapsed - agent.start) / agent.duration, 0, 1);
      var done = t >= 1;
      var html = '<div class="demo-panel-eyebrow" style="--dot-color:' + agent.hex + '"><span class="dot"></span>' + (agent.kind === 'lead' ? 'Agent workspace' : 'Worker agent') + '</div>';
      html += '<div class="demo-panel-name">' + agent.name + '</div>';
      html += '<div class="demo-panel-task">' + (agent.kind === 'lead' ? agent.task : 'Part of the ' + agent.teamName + ' team') + '</div>';
      html += '<div class="demo-panel-clock"><span>Elapsed compute time</span><b>' + formatClock(elapsed * ACCEL) + '</b></div>';
      if(agent.kind === 'lead' && !done){
        html += '<div class="demo-panel-chart">' + chartShellHtml(agent) + '</div>';
      }
      if(done){
        if(agent.kind === 'lead'){
          html += '<div class="demo-panel-lines">' + agent.findings.map(function(line, i){
            return '<div class="demo-panel-line" style="--d:' + (i * 0.1) + 's;--dot-color:' + agent.hex + '">' + line + '</div>';
          }).join('') + '</div>';
        }
        html += '<div class="demo-panel-status"><span class="chk"></span>Completed</div>';
      } else {
        html += '<div class="demo-panel-log"></div>';
      }
      html += '<div class="demo-panel-foot"><span>Recorded run</span><span>Standing desks &amp; focus</span></div>';
      panelInner.innerHTML = html;
      if(agent.kind === 'lead' && !done){
        renderMiniChart(agent, panelInner.querySelector('.demo-panel-chart'), t, tickCounter);
      }
    }

    function chartShellHtml(agent){
      switch(agent.id){
        case 'LIT':
          return '<div class="demo-mini-funnel">' +
            '<div class="demo-mini-funnel-row"><span>Screened</span><div class="demo-mini-funnel-track"><i data-bar="screened" style="width:0%;background:' + agent.hex + '"></i></div></div>' +
            '<div class="demo-mini-funnel-row"><span>Retained</span><div class="demo-mini-funnel-track"><i data-bar="retained" style="width:0%;background:' + agent.hex + '"></i></div></div>' +
            '<div class="demo-mini-funnel-row"><span>Gap found</span><div class="demo-mini-funnel-track"><i data-bar="gap" style="width:0%;background:' + agent.hex + '"></i></div></div>' +
            '</div>';
        case 'DATA':
          return '<svg class="demo-mini-spark" viewBox="0 0 100 40" preserveAspectRatio="none"><polyline points="" style="stroke:' + agent.hex + '"></polyline></svg>';
        case 'ANALYSIS': {
          var bars = '';
          for(var i = 0; i < 9; i++){ bars += '<i style="height:2px;background:' + agent.hex + '"></i>'; }
          return '<div class="demo-mini-bars">' + bars + '</div>';
        }
        case 'WRITER':
          return '<div class="demo-mini-wordbar-track"><i style="width:0%;background:' + agent.hex + '"></i></div><div class="demo-mini-wordbar-label">0 / 640 words</div>';
        case 'VERIFY':
          return '<div class="demo-mini-radial"><svg viewBox="0 0 56 56"><circle class="bg" cx="28" cy="28" r="24"></circle><circle class="fg" cx="28" cy="28" r="24" style="stroke:' + agent.hex + ';stroke-dasharray:' + RADIAL_C.toFixed(1) + ';stroke-dashoffset:' + RADIAL_C.toFixed(1) + '"></circle></svg><div><b>0/9</b><span>claims verified</span></div></div>';
        default:
          return '';
      }
    }

    function renderMiniChart(agent, container, t, tick){
      if(!container) return;
      switch(agent.id){
        case 'LIT': renderFunnel(container, t); break;
        case 'DATA': renderSparkline(container, pushSparkValue(agent, t, tick)); break;
        case 'ANALYSIS': renderHistogram(container, t, tick); break;
        case 'WRITER': renderWordBar(container, t); break;
        case 'VERIFY': renderRadial(container, t); break;
      }
    }
    function renderFunnel(container, t){
      var screened = clamp(t * 2.2, 0, 1);
      var retained = clamp(t * 1.6 - 0.15, 0, 1);
      var gap = t >= 0.88 ? 1 : clamp((t - 0.6) / 0.28, 0, 1);
      var vals = {screened:screened, retained:retained, gap:gap};
      var bars = container.querySelectorAll('[data-bar]');
      for(var i = 0; i < bars.length; i++){
        var key = bars[i].getAttribute('data-bar');
        bars[i].style.width = (vals[key] * 100) + '%';
      }
    }
    function pushSparkValue(agent, t, tick){
      var noise = 0.5 + 0.5 * Math.sin(tick * 0.7 + agent.index);
      var val = clamp(t * 1.3, 0, 1) * (0.35 + 0.65 * noise);
      agent._spark = agent._spark || [];
      agent._spark.push(val);
      if(agent._spark.length > 24) agent._spark.shift();
      return agent._spark;
    }
    function renderSparkline(container, values){
      var poly = container.querySelector('polyline');
      if(!poly || !values.length) return;
      var w = 100, h = 40;
      var pts = values.map(function(v, i){
        var x = values.length > 1 ? (i / (values.length - 1)) * w : 0;
        return x.toFixed(1) + ',' + ((1 - v) * h).toFixed(1);
      }).join(' ');
      poly.setAttribute('points', pts);
    }
    var BOOTSTRAP_BELL = [0.2, 0.4, 0.62, 0.82, 1, 0.82, 0.62, 0.4, 0.2];
    function renderHistogram(container, t, tick){
      var bars = container.querySelectorAll('.demo-mini-bars i');
      for(var i = 0; i < bars.length; i++){
        var noise = 0.3 + 0.4 * Math.sin(tick * 0.5 + i * 1.7);
        var val = lerp(noise, BOOTSTRAP_BELL[i], clamp(t * 1.15, 0, 1));
        bars[i].style.height = Math.max(2, val * 56) + 'px';
      }
    }
    function renderWordBar(container, t){
      var words = Math.round(t * 640);
      var track = container.querySelector('.demo-mini-wordbar-track i');
      if(track) track.style.width = (t * 100) + '%';
      var label = container.querySelector('.demo-mini-wordbar-label');
      if(label) label.textContent = words + ' / 640 words';
    }
    function renderRadial(container, t){
      var fg = container.querySelector('.fg');
      if(fg) fg.style.strokeDashoffset = (RADIAL_C * (1 - t)).toFixed(1);
      var num = container.querySelector('b');
      if(num) num.textContent = Math.round(t * 9) + '/9';
    }

    function renderPanelDone(agent){
      var live = panelInner.querySelector('.demo-panel-log') || panelInner.querySelector('.demo-panel-chart');
      var html = '';
      if(agent.kind === 'lead'){
        html += '<div class="demo-panel-lines">' + agent.findings.map(function(line, i){
          return '<div class="demo-panel-line" style="--d:' + (i * 0.1) + 's;--dot-color:' + agent.hex + '">' + line + '</div>';
        }).join('') + '</div>';
      }
      html += '<div class="demo-panel-status"><span class="chk"></span>Completed</div>';
      var wrap = document.createElement('div');
      wrap.innerHTML = html;
      var foot = panelInner.querySelector('.demo-panel-foot');
      while(wrap.firstChild){ panelInner.insertBefore(wrap.firstChild, foot); }
      if(live) live.remove();
    }

    function appendPanelLog(agent, logEl){
      agent.panelLogCounter = (agent.panelLogCounter || 0) + 1;
      var text = agent.logTemplates[agent.panelLogCounter % agent.logTemplates.length](agent.panelLogCounter + 50);
      var el = document.createElement('div');
      el.className = 'demo-panel-log-line';
      el.textContent = text;
      logEl.appendChild(el);
      while(logEl.children.length > 7) logEl.removeChild(logEl.firstChild);
      logEl.scrollTop = logEl.scrollHeight;
    }

    function updateOpenPanel(elapsed){
      if(focusIndex === null) return;
      var agent = AGENTS[focusIndex];
      var clockB = panelInner.querySelector('.demo-panel-clock b');
      if(clockB) clockB.textContent = formatClock(elapsed * ACCEL);
      var t = clamp((elapsed - agent.start) / agent.duration, 0, 1);
      var done = t >= 1;
      if(agent.kind === 'lead'){
        var chartEl = panelInner.querySelector('.demo-panel-chart');
        if(chartEl && !done) renderMiniChart(agent, chartEl, t, tickCounter);
        if(done && !panelInner.querySelector('.demo-panel-lines')) renderPanelDone(agent);
      } else if(done){
        if(!panelInner.querySelector('.demo-panel-status')) renderPanelDone(agent);
      } else {
        var logEl = panelInner.querySelector('.demo-panel-log');
        if(logEl) appendPanelLog(agent, logEl);
      }
    }

    /* ---------------- Fallback list (no WebGL) ---------------- */
    leadAgents.forEach(function(agent){
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'demo-fallback-row';
      row.innerHTML =
        '<span class="demo-fallback-dot" style="--dot-color:' + agent.hex + ';--dot-glow:' + agent.hex + '33"></span>' +
        '<span class="demo-fallback-name">' + agent.name + '</span>' +
        '<span class="demo-fallback-task">' + agent.task + '</span>';
      row.addEventListener('click', function(){
        if(runState === 'idle') return;
        setFocus(agent.index);
      });
      fallbackList.appendChild(row);
    });

    /* ---------------- Progress grid ---------------- */
    var progressEls = [];
    AGENTS.forEach(function(agent){
      if(agent.kind === 'lead'){
        var label = document.createElement('div');
        label.className = 'demo-progress-team-label';
        label.textContent = agent.teamName + ' team';
        progressGrid.appendChild(label);
      }
      var row = document.createElement('div');
      row.className = 'demo-progress-row';
      var dot = document.createElement('span');
      dot.className = 'demo-progress-dot';
      dot.style.background = agent.hex;
      var name = document.createElement('span');
      name.className = 'demo-progress-name';
      name.textContent = agent.kind === 'lead' ? agent.id : agent.id;
      var track = document.createElement('div');
      track.className = 'demo-progress-bar-track';
      var fill = document.createElement('span');
      fill.className = 'demo-progress-bar-fill';
      fill.style.background = agent.hex;
      track.appendChild(fill);
      var status = document.createElement('span');
      status.className = 'demo-progress-status';
      status.textContent = 'queued';
      row.appendChild(dot); row.appendChild(name); row.appendChild(track); row.appendChild(status);
      progressGrid.appendChild(row);
      progressEls[agent.index] = {fill:fill, status:status};
    });

    /* ---------------- Timeline (Gantt) ---------------- */
    TEAMS.forEach(function(team){
      var row = document.createElement('div');
      row.className = 'demo-timeline-row';
      var name = document.createElement('div');
      name.className = 'demo-timeline-name';
      name.textContent = team.name.replace(' Agent', '');
      var track = document.createElement('div');
      track.className = 'demo-timeline-track';
      var bar = document.createElement('div');
      bar.className = 'demo-timeline-bar';
      bar.style.left = (team.start / RUN_DURATION * 100) + '%';
      bar.style.width = (team.duration / RUN_DURATION * 100) + '%';
      bar.style.background = team.hex;
      track.appendChild(bar);
      row.appendChild(name); row.appendChild(track);
      timelineEl.appendChild(row);
    });
    var playheadEl = document.createElement('div');
    playheadEl.className = 'demo-timeline-playhead';
    timelineEl.appendChild(playheadEl);

    function updateProgressAndTimeline(elapsed){
      AGENTS.forEach(function(agent){
        var t = clamp((elapsed - agent.start) / agent.duration, 0, 1);
        var els = progressEls[agent.index];
        els.fill.style.width = (t * 100) + '%';
        els.status.textContent = elapsed < agent.start ? 'queued' : (t >= 1 ? 'done' : 'running');
      });
      var overallT = clamp(elapsed / RUN_DURATION, 0, 1);
      overallRing.style.strokeDashoffset = (RING_C * (1 - overallT)).toFixed(1);
      overallPct.textContent = Math.round(overallT * 100) + '%';
      playheadEl.style.left = (overallT * 100) + '%';
      var clockStr = formatClock(elapsed * ACCEL);
      timelineClockEl.textContent = clockStr;
    }

    /* ---------------- Results charts (built once, revealed on completion) ---------------- */
    function renderResultsCharts(){
      var scene = document.createElement('div');
      scene.className = 'd3-scene';
      var floor = document.createElement('div');
      floor.className = 'd3-floor';
      scene.appendChild(floor);
      var sit = [23, 20, 14, 12], stand = [24, 22, 19, 18], max = 24;
      for(var x = 0; x < 4; x++){
        var b1 = document.createElement('div');
        b1.className = 'd3-bar';
        b1.style.setProperty('--x', x);
        b1.style.setProperty('--z', 0);
        b1.style.setProperty('--h', (sit[x] / max).toFixed(2));
        b1.style.setProperty('--c', '#8f8c81');
        scene.appendChild(b1);
        var b2 = document.createElement('div');
        b2.className = 'd3-bar';
        b2.style.setProperty('--x', x);
        b2.style.setProperty('--z', 1.15);
        b2.style.setProperty('--h', (stand[x] / max).toFixed(2));
        b2.style.setProperty('--c', '#4fd08a');
        scene.appendChild(b2);
      }
      chart3dEl.appendChild(scene);
      var axis = document.createElement('div');
      axis.className = 'demo-chart-3d-axis';
      ['10am', '12pm', '2pm', '4pm'].forEach(function(l){
        var s = document.createElement('span');
        s.textContent = l;
        axis.appendChild(s);
      });
      var legend = document.createElement('div');
      legend.className = 'demo-chart-3d-legend';
      legend.innerHTML = '<span><i class="sw sit"></i>Seated</span><span><i class="sw stand"></i>Standing</span>';
      chart3dEl.parentNode.insertBefore(axis, chart3dEl.nextSibling);
      chart3dEl.parentNode.insertBefore(legend, axis.nextSibling);

      var seated = [8.2, 8.0, 8.4, 8.1, 8.6, 8.3, 8.7, 8.5, 8.9, 8.6];
      var standing = [7.9, 7.5, 7.0, 6.6, 6.2, 6.0, 5.7, 5.6, 5.4, 5.3];
      var w = 300, h = 140, padL = 24, padB = 18, padT = 10, padR = 10, vmax = 9, vmin = 5;
      function xAt(i){ return padL + i / (seated.length - 1) * (w - padL - padR); }
      function yAt(v){ return padT + (1 - (v - vmin) / (vmax - vmin)) * (h - padT - padB); }
      var seatedPts = seated.map(function(v, i){ return xAt(i).toFixed(1) + ',' + yAt(v).toFixed(1); }).join(' ');
      var standingPts = standing.map(function(v, i){ return xAt(i).toFixed(1) + ',' + yAt(v).toFixed(1); }).join(' ');
      var gridLines = '';
      [5, 6, 7, 8, 9].forEach(function(v){
        var y = yAt(v).toFixed(1);
        gridLines += '<line class="dlc-grid" x1="' + padL + '" y1="' + y + '" x2="' + (w - padR) + '" y2="' + y + '"></line>';
      });
      lineChartEl.innerHTML = gridLines +
        '<polyline class="dlc-seated" points="' + seatedPts + '"></polyline>' +
        '<polyline class="dlc-standing" points="' + standingPts + '"></polyline>' +
        '<text x="' + padL + '" y="' + (h - 4) + '">Day 1</text>' +
        '<text x="' + (w - padR - 34) + '" y="' + (h - 4) + '">Day 10</text>';
    }
    renderResultsCharts();

    /* ---------------- Combined console ---------------- */
    function pushConsoleLine(agent, text, elapsedMs){
      var el = document.createElement('div');
      el.className = 'demo-console-line';
      el.innerHTML = '<time>' + formatClock(elapsedMs * ACCEL) + '</time><b style="color:' + agent.hex + '">' + agent.id + '</b><span>' + text + '</span>';
      consoleBody.appendChild(el);
      if(consoleBody.children.length > 50) consoleBody.removeChild(consoleBody.firstChild);
      consoleBody.scrollTop = consoleBody.scrollHeight;
    }
    function pushSparkHistory(delta){
      sparkHistory.push(delta);
      if(sparkHistory.length > 30) sparkHistory.shift();
      var max = Math.max.apply(null, sparkHistory.concat([1]));
      var w = 120, h = 28;
      var pts = sparkHistory.map(function(v, i){
        var x = sparkHistory.length > 1 ? (i / (sparkHistory.length - 1)) * w : 0;
        var y = h - (v / max) * h;
        return x.toFixed(1) + ',' + y.toFixed(1);
      }).join(' ');
      var poly = sparkEl.querySelector('polyline');
      if(poly) poly.setAttribute('points', pts);
    }
    function updateConsoleTick(elapsed){
      var delta = 300 + ((tickCounter * 47) % 700);
      eventCount += delta;
      eventCountEl.textContent = formatNumber(eventCount);
      pushSparkHistory(delta);
      var active = AGENTS.filter(function(a){ return elapsed >= a.start && elapsed < a.start + a.duration; });
      if(active.length){
        var chosen = active[tickCounter % active.length];
        chosen.logCounter = (chosen.logCounter || 0) + 1;
        var text = chosen.logTemplates[chosen.logCounter % chosen.logTemplates.length](chosen.logCounter);
        pushConsoleLine(chosen, text, elapsed);
      }
    }

    /* ---------------- Run loop ---------------- */
    function startRunLoop(){
      if(tickTimer) return;
      tickTimer = setInterval(runTick, TICK_MS);
    }
    function stopRunLoop(){
      if(tickTimer){ clearInterval(tickTimer); tickTimer = null; }
    }
    function runTick(){
      if(runState !== 'running') return;
      tickCounter++;
      var real = performance.now() - runStartedAt;
      var elapsed = Math.min(real, RUN_DURATION);
      updateProgressAndTimeline(elapsed);
      clockEl.textContent = formatClock(elapsed * ACCEL);
      updateConsoleTick(elapsed);
      if(focusIndex !== null) updateOpenPanel(elapsed);
      if(real >= RUN_DURATION) completeRun();
    }
    function completeRun(){
      runState = 'complete';
      resultsSection.classList.add('complete');
      stopRunLoop();
    }
    function resetRunState(){
      eventCount = 0; tickCounter = 0; sparkHistory = [];
      consoleBody.innerHTML = '';
      AGENTS.forEach(function(a){ a.logCounter = 0; a.panelLogCounter = 0; a._spark = []; });
      resultsSection.classList.remove('complete');
      updateProgressAndTimeline(0);
      eventCountEl.textContent = '0';
      clockEl.textContent = '00:00:00';
    }
    function beginRun(){
      runState = 'running';
      runStartedAt = performance.now();
      gate.classList.add('dismissed');
      consoleEl.classList.add('active');
      consoleEl.setAttribute('aria-hidden', 'false');
      startRunLoop();
      triggerSplit();
    }
    function instantCompleteRun(){
      runState = 'complete';
      runStartedAt = performance.now() - RUN_DURATION;
      eventCount = 300 * Math.round(RUN_DURATION / TICK_MS);
      eventCountEl.textContent = formatNumber(eventCount);
      clockEl.textContent = formatClock(RUN_DURATION * ACCEL);
      timelineClockEl.textContent = formatClock(RUN_DURATION * ACCEL);
      gate.classList.add('dismissed');
      consoleEl.classList.add('active');
      consoleEl.setAttribute('aria-hidden', 'false');
      consoleBody.innerHTML = '';
      leadAgents.forEach(function(agent){ pushConsoleLine(agent, agent.logTemplates[4](9), RUN_DURATION); });
      updateProgressAndTimeline(RUN_DURATION);
      resultsSection.classList.add('complete');
      renderSceneStatic(1, null);
    }

    initiateBtn.addEventListener('click', function(){
      if(runState !== 'idle') return;
      if(reduce) instantCompleteRun(); else beginRun();
    });
    replayBtn.addEventListener('click', function(){
      if(runState === 'idle') return;
      setFocus(null);
      resetRunState();
      if(reduce) instantCompleteRun(); else beginRun();
    });
    if(reduce) replayBtn.style.display = 'none';

    /* ---------------- WebGL scene ---------------- */
    if(!canvas){ return; }
    var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if(!gl){ stage.classList.add('no-webgl'); return; }

    function compile(type, source){
      var shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if(!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return null;
      return shader;
    }
    var vertex = compile(gl.VERTEX_SHADER, vertexSource);
    var fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    if(!vertex || !fragment){ stage.classList.add('no-webgl'); return; }
    var program = gl.createProgram();
    gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
    if(!gl.getProgramParameter(program, gl.LINK_STATUS)){ stage.classList.add('no-webgl'); return; }
    gl.useProgram(program);

    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    var positionLoc = gl.getAttribLocation(program, 'aPos');
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    var uRes = gl.getUniformLocation(program, 'uRes');
    var uRo = gl.getUniformLocation(program, 'uRo');
    var uRight = gl.getUniformLocation(program, 'uRight');
    var uUp = gl.getUniformLocation(program, 'uUp');
    var uFwd = gl.getUniformLocation(program, 'uFwd');
    var uZoom = gl.getUniformLocation(program, 'uZoom');
    var uK = gl.getUniformLocation(program, 'uK');
    var uFocusIdx = gl.getUniformLocation(program, 'uFocusIdx');
    var uFocusGlow = gl.getUniformLocation(program, 'uFocusGlow');
    var uCentersLoc = gl.getUniformLocation(program, 'uCenters');
    var uRadiiLoc = gl.getUniformLocation(program, 'uRadii');
    var uColorsLoc = gl.getUniformLocation(program, 'uColors');

    var colorsFlat = new Float32Array(BALL_COUNT * 3);
    AGENTS.forEach(function(a, i){ colorsFlat[i*3] = a.rgb[0]; colorsFlat[i*3+1] = a.rgb[1]; colorsFlat[i*3+2] = a.rgb[2]; });
    gl.uniform3fv(uColorsLoc, colorsFlat);
    var centersFlat = new Float32Array(BALL_COUNT * 3);
    var radiiFlat = new Float32Array(BALL_COUNT);

    var hotspots = AGENTS.map(function(agent){
      var el = document.createElement('button');
      el.type = 'button';
      el.className = 'demo-hotspot ' + (agent.kind === 'lead' ? 'demo-hotspot--lead' : 'demo-hotspot--worker');
      el.style.setProperty('--dot-color', agent.hex);
      el.style.setProperty('--dot-glow', agent.hex + '33');
      el.innerHTML = '<span class="demo-hotspot-dot"></span><span class="demo-hotspot-label">' + agent.name + '</span>' +
        (agent.kind === 'lead' ? '<span class="demo-hotspot-sub">' + agent.task + '</span>' : '');
      el.addEventListener('click', function(){ setFocus(agent.index); });
      hotspotsWrap.appendChild(el);
      return el;
    });

    function resize(){
      var dpr = Math.min(window.devicePixelRatio || 1, 1.6);
      canvas.width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      canvas.height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    window.addEventListener('resize', resize);
    resize();

    var mouse = {x:0, y:0};
    var mouseTarget = {x:0, y:0};
    window.addEventListener('mousemove', function(e){
      mouseTarget.x = e.clientX / window.innerWidth * 2 - 1;
      mouseTarget.y = e.clientY / window.innerHeight * 2 - 1;
    }, {passive:true});

    var started = performance.now();
    var focusAnimating = false, focusStart = 0, focusFrom = 0, focusTo = 0, focusT = 0, frozenTime = 0;

    function drawFrame(camera, centersArr, spreadEased){
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform3f(uRo, camera.ro[0], camera.ro[1], camera.ro[2]);
      gl.uniform3f(uRight, camera.right[0], camera.right[1], camera.right[2]);
      gl.uniform3f(uUp, camera.up[0], camera.up[1], camera.up[2]);
      gl.uniform3f(uFwd, camera.fwd[0], camera.fwd[1], camera.fwd[2]);
      gl.uniform1f(uZoom, camera.zoom);
      gl.uniform1f(uK, lerp(K_MERGED, K_SPLIT, spreadEased));
      gl.uniform1f(uFocusIdx, focusIndex === null ? -1.0 : focusIndex);
      gl.uniform1f(uFocusGlow, focusT > 0 ? focusT * 0.6 : 0.0);
      for(var i = 0; i < BALL_COUNT; i++){
        centersFlat[i*3] = centersArr[i][0]; centersFlat[i*3+1] = centersArr[i][1]; centersFlat[i*3+2] = centersArr[i][2];
        radiiFlat[i] = radiusFor(AGENTS[i], spreadEased);
      }
      gl.uniform3fv(uCentersLoc, centersFlat);
      gl.uniform1fv(uRadiiLoc, radiiFlat);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function updateHotspots(camera, centers, spreadVal){
      var cssW = canvas.clientWidth, cssH = canvas.clientHeight;
      var show = spreadVal > 0.4 && focusIndex === null;
      for(var i = 0; i < BALL_COUNT; i++){
        var el = hotspots[i];
        var proj = projectToScreen(camera, centers[i], cssW, cssH);
        var onCanvas = proj && proj.x > -10 && proj.x < cssW + 10 && proj.y > -10 && proj.y < cssH + 10;
        var wantShow = onCanvas && (show || focusIndex === i);
        el.hidden = !wantShow;
        if(!wantShow) continue;
        el.style.transform = 'translate(-50%,-50%) translate(' + proj.x.toFixed(1) + 'px,' + proj.y.toFixed(1) + 'px) scale(' + proj.scale.toFixed(2) + ')';
        el.classList.add('visible');
        el.classList.toggle('demo-hotspot--active', focusIndex === i);
      }
    }

    renderSceneStatic = function(spreadVal, idx){
      var centers = AGENTS.map(function(a){ return ballCenter(a, 0, spreadVal); });
      var focusCenter = idx !== null ? centers[idx] : [0, 0, 0];
      var focusRadius = idx !== null ? radiusFor(AGENTS[idx], spreadVal) : 0.3;
      var camera = computeCamera(0, {x:0, y:0}, idx !== null ? 1 : 0, focusCenter, focusRadius);
      drawFrame(camera, centers, spreadVal);
      updateHotspots(camera, centers, spreadVal);
    };
    triggerSplit = function(){
      splitting = true;
      splitStart = performance.now();
    };
    setFocusCamera = function(idx){
      if(reduce){
        focusIndex = idx;
        focusT = idx === null ? 0 : 1;
        if(idx !== null) openPanel(idx); else closePanel();
        renderSceneStatic(spread, idx);
        return;
      }
      if(idx === null){ focusFrom = focusT; focusTo = 0; }
      else { frozenTime = (performance.now() - started) / 1000; focusFrom = focusT; focusTo = 1; }
      focusAnimating = true; focusStart = performance.now();
      if(idx !== null) openPanel(idx); else closePanel();
    };

    if(reduce){
      renderSceneStatic(0, null);
      return;
    }

    var visible = false;
    var frameId = 0;
    function schedule(){ if(!frameId && visible && !document.hidden) frameId = requestAnimationFrame(frame); }

    function frame(now){
      frameId = 0;
      if(!visible || document.hidden) return;
      var elapsed = (now - started) / 1000;

      if(splitting){
        var sp = clamp((now - splitStart) / SPLIT_DURATION, 0, 1);
        spread = easeInOutCubic(sp);
        if(sp >= 1) splitting = false;
      }
      if(focusAnimating){
        var ft = clamp((now - focusStart) / FOCUS_DURATION, 0, 1);
        focusT = lerp(focusFrom, focusTo, easeInOutCubic(ft));
        if(ft >= 1){ focusAnimating = false; focusT = focusTo; }
      }

      mouse.x += (mouseTarget.x - mouse.x) * 0.04;
      mouse.y += (mouseTarget.y - mouse.y) * 0.04;

      var camTime = focusIndex !== null ? frozenTime : elapsed;
      var centers = AGENTS.map(function(a){ return ballCenter(a, camTime, spread); });
      var focusCenter = focusIndex !== null ? centers[focusIndex] : [0, 0, 0];
      var focusRadius = focusIndex !== null ? radiusFor(AGENTS[focusIndex], spread) : 0.3;
      var camera = computeCamera(elapsed, mouse, focusT, focusCenter, focusRadius);

      drawFrame(camera, centers, spread);
      updateHotspots(camera, centers, spread);

      hintText.textContent = 'Click a ball to step inside that agent';
      hint.classList.toggle('visible', spread > 0.55 && focusIndex === null);

      schedule();
    }

    if('IntersectionObserver' in window){
      new IntersectionObserver(function(entries){
        visible = entries[0].isIntersecting;
        schedule();
      }, {threshold:0.1}).observe(stage);
    } else {
      visible = true;
    }
    document.addEventListener('visibilitychange', schedule);
    schedule();
  };
})();
