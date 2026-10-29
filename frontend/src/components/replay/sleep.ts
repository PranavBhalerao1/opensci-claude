// A pre-made run: which feature of sleep actually predicts next-day memory?
// Paper titles in the literature are real; the run's own results are simulated.
import type { ResearchPlan } from "@/lib/api";
import { bpTask, minorGap, paper, planTask, score } from "./kit";
import type { ReplayData } from "./types";

const PAPERS = [
  paper("p01", "About sleep's role in memory", ["Rasch", "Born"], 2013, "Physiol. Rev.", 3000, 0.95),
  paper("p02", "Old brains come uncoupled in sleep: slow wave-spindle synchrony, brain atrophy, and forgetting", ["Helfrich", "Mander", "Jagust"], 2018, "Neuron", 500, 0.98),
  paper("p03", "Hierarchical nesting of slow oscillations, spindles and ripples in the human hippocampus during sleep", ["Staresina", "Bergmann", "Bonnefond"], 2015, "Nat. Neurosci.", 800, 0.94),
  paper("p04", "Precise slow oscillation–spindle coupling promotes memory consolidation in younger and older adults", ["Muehlroth", "Sander", "Fandakova"], 2019, "Sci. Rep.", 200, 0.97),
  paper("p05", "Slow oscillation-spindle coupling predicts enhanced memory formation from childhood to adolescence", ["Hahn", "Heib", "Schabus"], 2020, "eLife", 150, 0.95),
  paper("p06", "Auditory closed-loop stimulation of the sleep slow oscillation enhances memory", ["Ngo", "Martinetz", "Born"], 2013, "Neuron", 900, 0.9),
  paper("p07", "The critical role of sleep spindles in hippocampal-dependent memory: a pharmacology study", ["Mednick", "McDevitt", "Walsh"], 2013, "J. Neurosci.", 400, 0.91),
  paper("p08", "Characterizing sleep spindles in 11,630 individuals from the National Sleep Research Resource", ["Purcell", "Manoach", "Demanuele"], 2017, "Nat. Commun.", 400, 0.89),
  paper("p09", "Fast and slow spindles during the sleep slow oscillation: disparate coalescence and engagement in memory processing", ["Mölle", "Bergmann", "Marshall"], 2011, "Sleep", 600, 0.88),
  paper("p10", "Prefrontal atrophy, disrupted NREM slow waves and impaired hippocampal-dependent memory in aging", ["Mander", "Rao", "Lu"], 2013, "Nat. Neurosci.", 900, 0.87),
  paper("p11", "Endogenous memory reactivation during sleep in humans is clocked by slow oscillation-spindle complexes", ["Schreiner", "Petzka", "Staudigl"], 2021, "Nat. Commun.", 200, 0.9),
  paper("p12", "Memory consolidation is linked to spindle-mediated information processing during sleep", ["Cairney", "Guttesen", "El Marj"], 2018, "Curr. Biol.", 300, 0.86),
  paper("p13", "An open-source, high-performance tool for automated sleep staging", ["Vallat", "Walker"], 2021, "eLife", 300, 0.82, "citation"),
  paper("p14", "A sleep spindle detection algorithm that emulates human expert spindle scoring", ["Lacourse", "Delfrate", "Beaudry"], 2019, "J. Neurosci. Methods", 150, 0.8, "citation"),
  paper("p15", "Individual differences in frequency and topography of slow and fast sleep spindles", ["Cox", "Schapiro", "Manoach"], 2017, "Front. Hum. Neurosci.", 200, 0.79),
  paper("p16", "The National Sleep Research Resource: towards a sleep data commons", ["Zhang", "Cui", "Mueller"], 2018, "J. Am. Med. Inform. Assoc.", 600, 0.76, "citation"),
  paper("p17", "Sleep spindles and rapid eye movement sleep as predictors of next morning cognitive performance in healthy middle-aged and older participants", ["Lafortune", "Gagnon", "Martin"], 2014, "J. Sleep Res.", 150, 0.84),
  paper("p18", "Sleep spindle activity is associated with the integration of new memories and existing knowledge", ["Tamminen", "Payne", "Stickgold"], 2010, "J. Neurosci.", 500, 0.83),
];

const GAP_QUESTION =
  "Does the timing precision of spindles relative to slow oscillations — rather than how many spindles occur — predict overnight memory retention, within the same person from night to night, and does it explain why older adults forget more?";

const PLAN: ResearchPlan = {
  title: "Timing, not quantity: slow-oscillation–spindle coupling and overnight memory",
  research_question: GAP_QUESTION,
  hypothesis:
    "Across people, coupling precision predicts retention (r ≥ 0.3) while spindle density does not once age is controlled; within people, nights with tighter coupling show better retention; coupling mediates ≥ 40% of the age effect on forgetting.",
  null_hypothesis: "Coupling precision adds no predictive value over spindle density, sleep duration and age (ΔR² = 0).",
  objectives: [
    "Pool open overnight studies that record EEG and test memory before and after sleep",
    "Detect spindles and slow oscillations with one validated pipeline",
    "Compare coupling and density as predictors, between and within people",
    "Test whether coupling mediates age-related forgetting, and validate out of sample",
  ],
  background: "Spindles are linked to memory, but studies are small, use different detectors and rarely separate timing from quantity.",
  study_type: "computational_experiment",
  phases: [
    { id: "P1", name: "Data", goal: "Pool and harmonise studies", tasks: [planTask("T1", "Find and download open sleep-memory studies", "data", []), planTask("T2", "Set up compute & MCP tools", "infrastructure", []), planTask("T3", "Harmonise EEG and memory scores", "analysis", ["T1"])] },
    { id: "P2", name: "Events", goal: "Detect sleep events", tasks: [planTask("T4", "Sleep staging & event detection", "modeling", ["T2", "T3"], "L"), planTask("T5", "Detector validation vs expert scoring", "analysis", ["T4"])] },
    { id: "P3", name: "Mechanism", goal: "Timing vs quantity", tasks: [planTask("T6", "Between-person models", "analysis", ["T4"]), planTask("T7", "Within-person, night-to-night models", "analysis", ["T4"]), planTask("T8", "Age mediation analysis", "analysis", ["T6"])] },
    { id: "P4", name: "Prediction", goal: "Out-of-sample biomarker", tasks: [planTask("T9", "Leave-one-study-out prediction", "modeling", ["T6"]), planTask("T10", "Robustness: detectors and channels", "analysis", ["T5", "T6"])] },
    { id: "P5", name: "Analysis", goal: "Statistics and figures", tasks: [planTask("T11", "Multilevel bootstrap & tests", "analysis", ["T7", "T8", "T9"]), planTask("T12", "Figures", "writing", ["T10", "T11"], "S")] },
  ],
  datasets: [
    { name: "OpenNeuro overnight memory studies", description: "5 studies with overnight PSG and pre/post-sleep word-pair recall", source: "https://openneuro.org", access: "public_download", role: "primary data" },
    { name: "NSRR spindle norms", description: "Age norms for spindle density and frequency", source: "https://sleepdata.org", access: "registration", role: "reference" },
    { name: "Expert-scored spindle set (MASS SS2)", description: "Spindles scored by two experts", source: "http://ceams-carsm.ca/mass", access: "registration", role: "detector validation" },
  ],
  methods: [
    { name: "YASA staging & detection", purpose: "One validated pipeline for every recording." },
    { name: "Phase-locking of spindles to SO up-states", purpose: "Coupling strength and preferred phase per night." },
    { name: "Multilevel models", purpose: "Separate between-person from within-person effects." },
    { name: "Causal mediation", purpose: "How much of age-related forgetting runs through coupling." },
  ],
  baselines: ["Spindle density", "Total sleep time", "Slow-wave sleep minutes"],
  metrics: [
    { name: "Overnight retention", definition: "Post-sleep recall / pre-sleep recall, %", success_threshold: "—" },
    { name: "ΔR²", definition: "Variance in retention explained by coupling beyond baselines", success_threshold: "> 0.05, p < 0.01" },
    { name: "Mediated proportion", definition: "Share of the age effect carried by coupling", success_threshold: "≥ 40%" },
  ],
  validation_strategy: "Leave-one-study-out prediction; multilevel bootstrap over participants and nights (10,000 resamples).",
  success_criteria: ["ΔR² > 0.05 with p < 0.01", "Within-person effect significant", "Mediated proportion ≥ 40%"],
  compute_estimate: "≈ 9 h on OpenScientist Cloud",
  duration_estimate: "About 12 hours end to end",
  risks: [
    { risk: "Studies use different memory tasks", likelihood: "high", mitigation: "Standardise retention within study" },
    { risk: "Few participants have multiple nights", likelihood: "medium", mitigation: "Report within-person effects separately" },
  ],
  deliverables: ["Harmonised dataset", "Event tables", "Coupling biomarker", "Paper"],
  open_questions: ["Would stimulating coupling improve memory in older adults?"],
};

const MASTER: ReplayData["master"] = {
  title: "Slow-oscillation–spindle coupling and overnight memory",
  summary:
    "Six agents find and pool open overnight sleep-memory studies, detect every spindle and slow oscillation with one pipeline, separate timing from quantity between and within people, test whether coupling explains age-related forgetting, and validate a biomarker out of sample.",
  python_packages: ["mne", "yasa", "numpy", "pandas", "statsmodels", "pingouin", "scikit-learn", "mcp", "matplotlib"],
  system_requirements: [],
  agents: [
    { id: "A1", name: "Data Engineer", model_tier: "standard", tools: ["mcp:openneuro", "http_request", "run_python"], instructions: "Find, download and harmonise studies." },
    { id: "A2", name: "Sleep Neuroscientist", model_tier: "reasoning", tools: ["mcp:eeg-events", "run_python"], instructions: "Staging, event detection and physiology." },
    { id: "A3", name: "Infra Engineer", model_tier: "standard", tools: ["web_search", "run_shell"], instructions: "Compute and the project's MCP servers." },
    { id: "A4", name: "ML Engineer", model_tier: "reasoning", tools: ["spawn_subagents", "run_job"], instructions: "Batch processing and out-of-sample prediction." },
    { id: "A5", name: "Statistician", model_tier: "standard", tools: ["run_python"], instructions: "Multilevel models, mediation and bootstrap." },
    { id: "A6", name: "Figure Maker", model_tier: "bulk", tools: ["run_python"], instructions: "Publication figures." },
  ],
  datasets: [
    { id: "D1", name: "OpenNeuro overnight memory studies (5)", url: "https://openneuro.org", access_method: "Search + download via own MCP server", format: "edf / bids", license: "CC0", notes: "", verified: true },
    { id: "D2", name: "NSRR spindle norms", url: "https://sleepdata.org", access_method: "Published tables", format: "csv", license: "NSRR DUA", notes: "", verified: true },
    { id: "D3", name: "MASS SS2 expert spindles", url: "http://ceams-carsm.ca/mass", access_method: "Registration", format: "edf", license: "Research", notes: "", verified: true },
  ],
  tasks: [
    bpTask("T1", "Find & download studies", "A1", [], "Search OpenNeuro for overnight PSG with pre/post memory tests; download 5 studies."),
    bpTask("T2", "Set up compute & MCP tools", "A3", [], "Allocate cloud workers; write openneuro and eeg-events MCP servers."),
    bpTask("T3", "Harmonise", "A1", ["T1"], "Common montage, sampling rate and retention score.", 40, 2),
    bpTask("T4", "Staging & events", "A4", ["T2", "T3"], "Stage 612 nights; detect spindles and slow oscillations.", 180, 6),
    bpTask("T5", "Detector validation", "A2", ["T4"], "Compare detections with expert scoring on MASS SS2."),
    bpTask("T6", "Between-person models", "A5", ["T4"], "Retention ~ coupling + density + age + TST, per study."),
    bpTask("T7", "Within-person models", "A5", ["T4"], "Night-to-night multilevel models."),
    bpTask("T8", "Age mediation", "A5", ["T6"], "Mediation of age → retention via coupling."),
    bpTask("T9", "Leave-one-study-out", "A4", ["T6"], "Predict retention in an unseen study.", 60, 2),
    bpTask("T10", "Robustness", "A2", ["T5", "T6"], "Alternative detectors, channels and coupling metrics."),
    bpTask("T11", "Bootstrap & tests", "A5", ["T7", "T8", "T9"], "Multilevel bootstrap; corrected tests."),
    bpTask("T12", "Figures", "A6", ["T10", "T11"], "Coupling histograms, scatter plots, mediation diagram."),
  ],
  checkpoints: [{ after_task: "T3", reason: "Confirm every study measured memory before and after the same night." }],
  llm_usd_estimate: 34,
  compute_hours_estimate: 9,
  execution_notes: ["Up to 4 tasks run in parallel", "Heavy work runs on OpenScientist Cloud", "Failed tasks retry on a stronger model"],
};

export const sleep: ReplayData = {
  slug: "sleep-spindles",
  question: "Can the rhythm of your brain during sleep predict what you'll remember tomorrow?",
  shortTitle: "Sleep rhythms and next-day memory",
  brief: {
    title: "Sleep spindle timing and overnight memory",
    core_question:
      "Does the precise timing of sleep spindles relative to slow oscillations predict how much people remember overnight — better than how many spindles they have — and does it explain age-related forgetting?",
    summary:
      "During deep sleep the brain produces slow waves and short bursts called spindles, both linked to memory. Small studies disagree on whether spindle *number* or spindle *timing* matters. This investigation pools open overnight studies, measures both with one pipeline, separates differences between people from night-to-night changes within a person, and tests whether timing explains why older adults forget more.",
    domain: "Neuroscience · sleep · memory",
    subfields: ["Sleep physiology", "Memory consolidation", "EEG signal processing"],
    key_concepts: [
      { term: "Sleep spindle", definition: "a 0.5–2 s burst of 11–16 Hz brain activity during non-REM sleep." },
      { term: "Slow oscillation", definition: "a large, slow (< 1 Hz) wave of deep sleep." },
      { term: "Coupling", definition: "how consistently spindles arrive at the peak of a slow oscillation." },
    ],
    scope_in: ["Open overnight EEG studies with memory tests", "Healthy adults 18–80", "Declarative (word-pair) memory"],
    scope_out: ["Clinical populations", "Naps", "Stimulation experiments"],
    result_type: "A pooled analysis, a within-person test, a mediation analysis and a validated biomarker",
    data_resources: "OpenNeuro and NSRR (found automatically)",
    compute_resources: "OpenScientist Cloud (managed for you)",
    user_expertise: "Curious non-specialist",
    constraints: ["Budget: $60", "Every claim must trace to data or a cited paper"],
    search_keywords: ["sleep spindle memory consolidation", "slow oscillation spindle coupling", "aging sleep memory", "spindle density recall", "overnight retention EEG", "open sleep EEG dataset"],
    assumptions: ["Word-pair recall measures declarative memory comparably across studies", "Frontal and central channels are available in every study"],
  },
  questions: {
    round: 1,
    message: "Great question. Three choices will shape the investigation:",
    questions: [
      {
        id: "q1",
        question: "Which kind of memory?",
        why: "Sleep helps some kinds of memory more than others.",
        multi: false,
        options: [
          { label: "Facts and word pairs", detail: "Declarative memory — the most studied and most often shared." },
          { label: "Motor skills", detail: "Finger-tapping tasks; fewer open datasets." },
          { label: "Both", detail: "Broader, but harder to compare across studies." },
        ],
      },
      {
        id: "q2",
        question: "Where should the data come from?",
        why: "No single open study is large enough.",
        multi: false,
        options: [
          { label: "Pool every open overnight study", detail: "Larger and more general; needs careful harmonising." },
          { label: "One large study", detail: "Cleaner, but small and specific." },
        ],
      },
      {
        id: "q3",
        question: "Should it test the effect within the same person?",
        why: "Differences between people can be confounded by age, health or habits.",
        multi: false,
        options: [
          { label: "Yes — compare nights within each person", detail: "Rules out stable traits as the explanation." },
          { label: "Between people only", detail: "Simpler, but weaker evidence." },
        ],
      },
    ],
  },
  answers: [
    { question_id: "q1", selected: ["Facts and word pairs"], other: null, rationale: "Most open datasets test declarative memory." },
    { question_id: "q2", selected: ["Pool every open overnight study"], other: null, rationale: "Single studies are too small to separate timing from quantity." },
    { question_id: "q3", selected: ["Yes — compare nights within each person"], other: null, rationale: "It is the strongest test available without stimulation." },
  ],
  papers: PAPERS,
  lit: { queries: 8, found: 1312, screened: 398, included: 92, citations: 214, links: 1126 },
  overview: {
    summary:
      "Sleep supports memory through **slow oscillations, spindles and ripples** that nest in time. Several studies link **spindle–slow-oscillation coupling** to retention and show it weakens with **age**; others link retention to spindle **density**. Studies are small (median n = 24), use different detectors, and compare people rather than nights — so whether *timing* or *quantity* matters, and whether timing explains age-related forgetting, is unresolved.",
    themes: [
      { name: "Sleep and memory", description: "Active systems consolidation during non-REM sleep.", paper_ids: ["p01", "p03", "p11"] },
      { name: "Coupling", description: "Spindles locked to slow-oscillation up-states.", paper_ids: ["p02", "p04", "p05"] },
      { name: "Spindle quantity", description: "Density, power and individual differences.", paper_ids: ["p07", "p08", "p15"] },
      { name: "Aging", description: "Atrophy, slow waves and forgetting.", paper_ids: ["p10", "p02", "p17"] },
    ],
    common_methods: ["Spindle detection", "Phase-amplitude coupling", "Word-pair recall", "Closed-loop stimulation"],
    common_datasets: ["OpenNeuro", "NSRR", "MASS"],
    open_problems: [
      "Does timing predict memory better than spindle quantity?",
      "Does the effect hold within the same person across nights?",
      "Does coupling explain age-related forgetting?",
    ],
  },
  gaps: [
    {
      id: "g1",
      title: "Is it the timing of sleep spindles, not their number, that makes memories stick?",
      question: GAP_QUESTION,
      gap_type: "causal_gap",
      why_open: "Studies are small, use different detectors and compare people, not nights; none pools data to separate timing from quantity.",
      hypothesis: "Coupling precision predicts retention between and within people, and mediates the age effect.",
      approach: "Pool 5 open studies; one detection pipeline; multilevel and mediation models; leave-one-study-out validation.",
      data_needed: "OpenNeuro overnight memory studies, NSRR norms, MASS expert spindles",
      compute_needed: "Runs on OpenScientist Cloud",
      risks: ["Heterogeneous memory tasks", "Few multi-night participants"],
      supporting_paper_ids: ["p02", "p04", "p07"],
      novelty_queries: ["pooled analysis spindle coupling memory", "within-person sleep spindle retention", "coupling mediates age memory"],
      scores: {
        novelty: score(5, "No pooled, within-person comparison of timing and quantity exists."),
        feasibility: score(4, "Open data and validated tools exist."),
        impact: score(4, "Targets for sleep stimulation in older adults."),
        testability: score(5, "Clear ΔR², a within-person test and mediation."),
      },
      novelty_check: {
        status: "novel",
        explanation: "Closest work tests coupling in single studies of 20–60 people, between people only.",
        closest: [
          { title: "Old brains come uncoupled in sleep: slow wave-spindle synchrony, brain atrophy, and forgetting", year: 2018, url: null, in_review: true, overlap: "Coupling and aging in 32 people — one study, between people." },
          { title: "Precise slow oscillation–spindle coupling promotes memory consolidation in younger and older adults", year: 2019, url: null, in_review: true, overlap: "Coupling vs memory in two age groups — no within-person test or pooled data." },
        ],
      },
      overall: 4.55,
    },
    minorGap("g2", "Spindles and memory in shift workers", "generalisation", [4, 2, 4, 3], "unchecked", "No open data from shift workers."),
    minorGap("g3", "Home EEG headbands as spindle biomarkers", "methodological", [3, 4, 4, 3], "partially_addressed", "Validation studies exist for staging only."),
    minorGap("g4", "Spindle topography and emotional memory", "mechanism", [3, 3, 3, 3], "partially_addressed", "Small studies with mixed results."),
    minorGap("g5", "Night-to-night variability as an early marker of decline", "new_question", [4, 2, 4, 2], "unchecked", "Needs longitudinal data."),
  ],
  plan: PLAN,
  planAudit: {
    revised: true,
    first: {
      field: "Sleep neuroscience",
      established_theory: ["Coupling weakens with age", "Spindle density is trait-like"],
      contribution: "",
      problems: [
        { severity: "FATAL", kind: "measurement", problem: "The first draft computed retention as post-sleep recall alone, ignoring how much was learned before sleep.", fix: "Use post / pre recall, standardised within study." },
        { severity: "MAJOR", kind: "pooling", problem: "Pooling raw coupling values across studies with different reference montages.", fix: "Re-reference to a common montage and include study as a random effect." },
      ],
    },
    final: {
      field: "Sleep neuroscience",
      established_theory: ["Coupling weakens with age", "Spindle density is trait-like"],
      contribution: "The first pooled, within-person test separating spindle timing from spindle quantity — with an age mediation analysis.",
      problems: [],
    },
  },
  planLog: [
    "Drafting hypotheses, data, methods and metrics",
    "Expert audit: checking how retention is measured",
    "FATAL: retention ignored pre-sleep learning",
    "MAJOR: coupling pooled across different montages",
    "Revising: post/pre retention, common montage, study random effect",
    "Validating task graph: 12 tasks, 5 phases, no cycles",
  ],
  master: MASTER,
  bpLog: ["Searching OpenNeuro for overnight studies with memory tests", "Verified 3/3 data sources · 5 studies qualify", "Compiling 6 agents · 12 tasks", "Validating data flow, tools and budget"],
  taskCost: { T1: 1.21, T2: 0.58, T3: 1.94, T4: 12.6, T5: 1.12, T6: 1.48, T7: 1.37, T8: 0.96, T9: 3.4, T10: 2.1, T11: 1.18, T12: 0.71 },
  toolScript: {
    T1: [
      { tool: "mcp:openneuro", args: "search 'overnight polysomnography memory recall' → 23 candidates" },
      { tool: "run_python", args: "5 studies qualify · 386 participants · 612 nights · 1.4 TB" },
    ],
    T2: [
      { tool: "run_shell", args: "cloud workers allocated · ready" },
      { tool: "mcp", args: "registered openneuro · eeg-events ✓" },
    ],
    T3: [
      { tool: "run_python", args: "re-referenced to linked mastoids · resampled to 256 Hz" },
      { tool: "skill+", args: "learned bids_channel_mapper (7 naming schemes → 10-20)" },
    ],
    T4: [
      { tool: "spawn_subagents", args: "4 sub-agents: studies 1–2 · 3 · 4 · 5" },
      { tool: "mcp:eeg-events", args: "yasa staging + spindles + slow oscillations", sub: "study-3" },
      { tool: "error", args: "artifact bursts flagged as spindles in 41 nights", sub: "study-3" },
      { tool: "skill+", args: "wrote artifact_gate: reject events with EMG > 3 SD or amplitude > 150 µV" },
      { tool: "mcp:eeg-events", args: "412,806 spindles · 1,093,412 slow oscillations", sub: "study-5" },
    ],
    T5: [{ tool: "run_python", args: "F1 vs experts 0.76 (inter-expert 0.74) ✓" }],
    T6: [
      { tool: "run_python", args: "retention ~ coupling + density + age + TST + (1|study)" },
      { tool: "verifier", args: "✕ coupling computed on all spindles, including those outside slow oscillations" },
      { tool: "skill+", args: "wrote so_locked_coupling (spindles within ±1.2 s of an SO peak) · retry on OS-Reasoner" },
      { tool: "run_python", args: "coupling r = 0.41 · density r = 0.14 (n.s. after age) · ΔR² = 0.12" },
    ],
    T7: [{ tool: "run_python", args: "within-person: +1 SD coupling → +4.8% retention (p = 0.002, 141 people)" }],
    T8: [{ tool: "run_python", args: "age → retention mediated by coupling: 58% [37%, 81%]" }],
    T9: [
      { tool: "run_job", args: "leave-one-study-out ridge · 5 folds" },
      { tool: "skill", args: "reused so_locked_coupling for unseen studies" },
      { tool: "run_python", args: "out-of-sample R² 0.19 (coupling) vs 0.03 (density)" },
    ],
    T10: [{ tool: "run_python", args: "robust across 3 detectors, 4 channels and 2 coupling metrics" }],
    T11: [
      { tool: "skill+", args: "wrote multilevel_bootstrap (participants within studies)" },
      { tool: "run_python", args: "ΔR² 95% CI [0.07, 0.17] · p < 0.001 (Holm-corrected)" },
    ],
    T12: [{ tool: "run_python", args: "fig1_events · fig2_between · fig3_within · fig4_mediation" }],
  },
  budget: 60,
  report: {
    scaffold: {
      title: "Timing, Not Quantity: Slow-Oscillation–Spindle Coupling Predicts Overnight Memory Within and Across People",
      one_sentence_summary:
        "Pooling 612 nights from 386 people, the precision with which spindles lock to slow oscillations predicts overnight memory retention far better than spindle number, holds from night to night within the same person, and carries 58% of the age-related decline in memory.",
      hypothesis_verdict: "supported",
      verdict_explanation:
        "Coupling explained 12% more variance in retention than density, sleep time and age combined (ΔR² 95% CI 0.07–0.17, p < 0.001); within people, nights with 1 SD tighter coupling showed 4.8% better retention (p = 0.002).",
      findings: [
        { claim: "Coupling precision correlates with retention (r = 0.41), spindle density only weakly (r = 0.14), and not after controlling age.", evidence: ["T6", "table1.csv"], strength: "strong", relation: "supports H₁" },
        { claim: "Within the same person, nights with 1 SD tighter coupling show 4.8% better retention (141 people with ≥ 2 nights).", evidence: ["T7", "fig3_within.pdf"], strength: "moderate", relation: "causal" },
        { claim: "Coupling mediates 58% (95% CI 37–81%) of the effect of age on forgetting.", evidence: ["T8", "fig4_mediation.pdf"], strength: "moderate", relation: "mechanism" },
        { claim: "In unseen studies, coupling predicts retention out of sample (R² = 0.19 vs 0.03 for density).", evidence: ["T9"], strength: "strong", relation: "generalises" },
        { claim: "Results are robust across three spindle detectors, four channels and two coupling metrics.", evidence: ["T5", "T10"], strength: "strong", relation: "robustness" },
      ],
      success_criteria: [
        { criterion: "ΔR² > 0.05 with p < 0.01", status: "met", evidence: "0.12, p < 0.001" },
        { criterion: "Within-person effect significant", status: "met", evidence: "p = 0.002" },
        { criterion: "Mediated proportion ≥ 40%", status: "met", evidence: "58%" },
      ],
      figures: [],
      limitations: ["Observational: within-person effects can still reflect night-level confounders", "Declarative memory only", "Five studies, all from Europe and North America"],
      deviations: ["Restricted coupling to slow-oscillation-locked spindles after the verifier caught a definition error"],
    },
    agent: { status: "done", summary: "", cost: 1.54, issues: [] },
    files: { tex: true, pdf: true, bib: true },
    citations: { used: Array.from({ length: 41 }, (_, i) => `ref${i}`), unknown: [], available: 92 },
    audit: [],
  },
  iterations: [
    { n: 1, session: 1, review_run_id: "r1", verdict: "major_revision", judged: true, decision: "repair", reason: "", score: 6.4, score_rationale: "Convincing pooled result, but the within-person model mixes nights recorded months apart with different memory lists, and Table 1 misreports one study's n.", blocking: { FATAL: 0, MAJOR: 2 }, open_concerns: 1, issues: [], cost_usd: 0.9, level: "execution", rerun_tasks: ["T7", "T11"], carried_over: ["T1", "T2", "T3", "T4", "T5", "T6", "T8", "T9", "T10", "T12"] },
    { n: 2, session: 1, review_run_id: "r2", verdict: "minor_revision", judged: true, decision: "improve", reason: "", score: 8.5, score_rationale: "Sound and well controlled. Temper the causal language for the within-person result.", blocking: { FATAL: 0, MAJOR: 0 }, open_concerns: 1, issues: [], cost_usd: 0.8, level: "report" },
    { n: 3, session: 1, review_run_id: "r3", verdict: "accept", judged: true, decision: "approved", reason: "", score: 9.1, score_rationale: "Claims are calibrated to the evidence; robustness analyses are thorough.", blocking: { FATAL: 0, MAJOR: 0 }, open_concerns: 0, issues: [], cost_usd: 0.6, level: "report" },
  ],
  round1Issues: [
    { id: "i1", track_id: "k1", severity: "MAJOR", category: "design", title: "Within-person model pools nights months apart with different word lists; restrict to paired nights with matched lists.", blocking: true, open_concern: false, verification: "verified", grounding: "results/within.csv", tracking: { status: "new", previous_ids: [] }, referee: "methods" },
    { id: "i2", track_id: "k2", severity: "MAJOR", category: "table_mismatch", title: "Table 1 lists study 4 with n = 92; the data has 88 participants after exclusions.", blocking: true, open_concern: false, verification: "verified", grounding: "table1.tex", tracking: { status: "new", previous_ids: [] }, referee: "lead" },
    { id: "i3", track_id: "k3", severity: "MINOR", category: "claims", title: "Soften causal wording for the within-person effect.", blocking: false, open_concern: true, verification: "verified", grounding: "paper.tex §5", tracking: { status: "new", previous_ids: [] }, referee: "theory" },
  ],
  reviewLog: {
    round1: ["Reviewer panel assembled: lead, methods, theory", "Recomputed Table 1 from data/participants.csv", "Study 4: table n = 92, data n = 88 — mismatch"],
    repair: ["Round 1 · score 6.4 · 2 major issues", "Re-running T7, T11 on matched-list paired nights; reusing 10 finished tasks", "Within-person effect holds (+4.8%, p = 0.002). Rewriting §5 and Table 1"],
    round2: ["Round 2 · score 8.5 · softening causal language"],
    round3: ["Round 3 · score 9.1 · accept"],
  },
  spend: { literature: 0.86, gaps: 2.4, plan: 3.7, blueprint: 5.1, execution: 33.9, report: 35.5, review: 37.8 },
  paper: {
    title: "Timing, Not Quantity: Slow-Oscillation–Spindle Coupling Predicts Overnight Memory Within and Across People",
    authors: "Anonymous Author(s)",
    affiliation: "Affiliation · Address",
    abstract:
      "Sleep spindles are thought to support memory consolidation, but small studies disagree on whether their number or their timing matters. We pooled five open overnight studies (386 participants, 612 nights) and detected 412,806 spindles and 1.09M slow oscillations with one validated pipeline. The precision with which spindles lock to slow-oscillation up-states predicted overnight retention (r = 0.41), adding 12% explained variance beyond spindle density, sleep duration and age (95% CI [7%, 17%]), whereas density did not predict retention once age was controlled. The effect held within people across nights (+4.8% retention per SD, p = 0.002) and in unseen studies (R² = 0.19 vs 0.03). Coupling mediated 58% of age-related forgetting.",
    sections: [
      {
        heading: "Introduction",
        paragraphs: [
          "Non-REM sleep supports the consolidation of newly learned facts [1]. In the leading account, hippocampal ripples nest in thalamocortical spindles, which in turn nest in neocortical slow oscillations (SOs) [3], creating windows in which memories are reactivated [11].",
          "Two kinds of evidence link spindles to memory. One relates retention to spindle *quantity* — density or power [7, 18]. The other relates it to *timing*: how precisely spindles arrive at the SO up-state [2, 4, 5]. Because studies are small (median n = 24), use different detectors and compare people rather than nights, the two accounts have never been tested against each other.",
          "We pool every open overnight study with a memory test before and after sleep, apply one pipeline to all of them, and ask (i) whether timing predicts retention beyond quantity; (ii) whether the effect holds within the same person across nights; and (iii) whether timing explains age-related forgetting [2, 10].",
        ],
      },
      {
        heading: "Related Work",
        paragraphs: [
          "**Spindles and memory.** Pharmacologically increasing spindles improves declarative memory [7], and spindle activity predicts integration of new memories [18]. Large-scale characterisations of spindles in 11,630 individuals [8] establish age norms but lack memory measures.",
          "**Coupling.** Helfrich et al. [2] showed that SO–spindle coupling degrades with age and prefrontal atrophy and predicts forgetting; Muehlroth et al. [4] and Hahn et al. [5] related coupling precision to memory across the lifespan. Closed-loop auditory stimulation of SOs enhances memory [6], suggesting timing can be manipulated.",
          "**Tools.** We use YASA for staging and event detection [13], validated against expert spindle scoring [14].",
        ],
      },
      {
        heading: "Methods",
        paragraphs: [
          "**Data.** Five open studies met our criteria: overnight polysomnography and word-pair recall before and after the same night. After harmonising montages (linked mastoids, 256 Hz) and exclusions, 386 participants (age 18–79) contributed 612 nights.",
          "**Events.** Sleep was staged with YASA [13]. Spindles (11–16 Hz) and SOs were detected at C3/C4. An artifact gate rejected events during muscle activity. Detector F1 against expert scoring was 0.76, comparable to inter-expert agreement (0.74).",
          "**Coupling.** For spindles peaking within ±1.2 s of an SO trough, we computed the SO phase at spindle peak; coupling strength is the mean resultant length of these phases per night.",
          "**Models.** Retention (post/pre recall, z-scored within study) was modelled with multilevel regressions including study as a random effect; within-person effects use person-centred predictors. Mediation used 10,000 multilevel bootstrap resamples.",
        ],
        table: {
          caption: "Table 1: Studies pooled in this analysis.",
          head: ["Study", "n", "Nights", "Age", "Memory task"],
          rows: [["S1", "64", "128", "19–31", "Word pairs (120)"], ["S2", "71", "71", "20–78", "Word pairs (80)"], ["S3", "58", "116", "18–35", "Word pairs (60)"], ["S4", "88", "176", "55–79", "Word pairs (100)"], ["S5", "105", "121", "21–74", "Word pairs (90)"]],
        },
      },
      {
        heading: "Timing Beats Quantity",
        paragraphs: [
          "Coupling strength correlated with overnight retention (r = **0.41**), whereas spindle density correlated weakly (r = 0.14) and not at all once age was controlled. In multilevel models, coupling added **ΔR² = 0.12** (95% CI [0.07, 0.17], p < 0.001) beyond density, total sleep time, slow-wave sleep and age.",
        ],
        figure: { caption: "Figure 1: (left) Retention against coupling strength, one point per participant. (right) Variance explained by each predictor.", kind: "scatter" },
        table: {
          caption: "Table 2: Multilevel models of overnight retention (standardised β).",
          head: ["Predictor", "Model 1", "Model 2", "Model 3"],
          rows: [["Age", "−0.31", "−0.18", "−0.13"], ["Spindle density", "0.14", "0.05", "0.04"], ["Total sleep time", "0.08", "0.06", "0.06"], ["Coupling strength", "—", "**0.36**", "**0.33**"], ["ΔR²", "—", "**0.12**", "0.11"]],
        },
      },
      {
        heading: "Within People, Night to Night",
        paragraphs: [
          "Among 141 participants with at least two nights, nights with 1 SD tighter coupling than that person's average showed **4.8%** better retention (p = 0.002). Spindle density showed no within-person effect (p = 0.41). Because each person serves as their own control, stable traits such as age, intelligence or habits cannot explain this association.",
        ],
        figure: { caption: "Figure 2: (left) Within-person change in retention against change in coupling. (right) Preferred SO phase of spindles by age group.", kind: "lines" },
      },
      {
        heading: "Coupling Explains Age-Related Forgetting",
        paragraphs: [
          "Older participants forgot more (β = −0.31) and had weaker coupling. Coupling mediated **58%** (95% CI [37%, 81%]) of the age effect on retention; spindle density mediated 9% (n.s.). In leave-one-study-out prediction, coupling predicted retention in unseen studies with R² = 0.19, versus 0.03 for density.",
        ],
        figure: { caption: "Figure 3: (left) Mediation of age → retention via coupling. (right) Out-of-sample R² by predictor set.", kind: "bars" },
      },
      {
        heading: "Discussion",
        paragraphs: [
          "Across five studies and within individuals, *when* spindles occur matters more than *how many* occur. This reconciles conflicting small studies and points to coupling, not spindle count, as the target for sleep interventions such as closed-loop stimulation [6], especially in older adults.",
          "**Limitations.** Within-person effects are observational and could reflect night-level factors such as stress. We study declarative memory in healthy adults only, and all studies come from Europe and North America.",
        ],
      },
      {
        heading: "Conclusion",
        paragraphs: [
          "Spindle timing, not spindle number, predicts what people remember overnight, and it carries most of the memory cost of aging. Harmonised data, event tables and code are released.",
        ],
      },
    ],
    references: PAPERS.map((p) => `${p.authors.join(", ")}. ${p.title}. *${p.venue}*, ${p.year}.`),
  },
};
