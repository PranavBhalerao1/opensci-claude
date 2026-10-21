// Hardcoded data for the recorded demo film. Nothing here talks to the backend.
// Paper titles are real; every result, number and cost of the run itself is simulated.
import type {
  BlueprintRun,
  Gap,
  GapsRun,
  LitPaper,
  MasterPlan,
  Message,
  Overview,
  PlanRun,
  Project,
  ReportRun,
  ResearchBrief,
  ResearchPlan,
  ReviewIteration,
  Run,
  TaskState,
} from "@/lib/api";

export const PID = "demo-7f3a";
const T0 = new Date().toISOString();
export const now = () => new Date().toISOString();

export const QUESTION =
  "Can AI weather models like GraphCast be trusted to forecast record-breaking heatwaves — the ones hotter than anything they were trained on?";

export const OLD_PROJECTS = [
  { id: "p2", title: "Do sleep spindles predict next-day recall?", stage: "complete" },
  { id: "p3", title: "Protein language models and stability effects", stage: "complete" },
  { id: "p4", title: "Battery electrode decay from impedance spectra", stage: "executed" },
];

/** Totals for the whole run, shown in the outro and the sidebar. */
export const TOTALS = { total: 84.62, wall: "19h 12m" };

export const BRIEF: ResearchBrief = {
  title: "AI weather models and record-shattering heat",
  core_question:
    "Do machine-learning weather models underpredict heatwaves in proportion to how far they exceed the training-period record — and can tail-aware fine-tuning close the gap without hurting everyday skill?",
  summary:
    "AI forecasters now match or beat the best physics-based model on average scores. But the heatwaves that kill people are often hotter than anything in the training data. This investigation re-forecasts every record-shattering heat event since 2018 with open AI models and the ECMWF physics model, measures how forecast error grows with the size of the record break, tests whether the training record is the cause, and tries to fix it.",
  domain: "Atmospheric science · machine learning",
  subfields: ["Numerical weather prediction", "Extreme events", "Out-of-distribution generalisation"],
  key_concepts: [
    { term: "Record exceedance", definition: "how far an event's peak temperature beats the previous record at that location, in kelvin." },
    { term: "Peak bias", definition: "forecast peak temperature minus observed (ERA5) peak; negative means the forecast was too cold." },
    { term: "Lead time", definition: "how many days ahead the forecast was issued." },
  ],
  scope_in: ["GraphCast and Pangu-Weather (open weights)", "ECMWF IFS HRES as the physics baseline", "Heat events 2018–2023, after every model's training data"],
  scope_out: ["Station-level observations", "Seasonal forecasting", "Operational deployment"],
  result_type: "A benchmark of AI forecasts on record heat, a causal test, and a fine-tuned model",
  data_resources: "ERA5 reanalysis and WeatherBench 2 archives (found automatically)",
  compute_resources: "OpenScientist Cloud (managed for you)",
  user_expertise: "Curious non-specialist",
  constraints: ["Budget: $100", "Every claim must trace to data or a cited paper"],
  search_keywords: [
    "GraphCast extreme heat",
    "machine learning weather prediction extremes",
    "record-shattering heatwave",
    "out-of-distribution weather forecasting",
    "WeatherBench 2",
    "forecast smoothing spectra",
  ],
  assumptions: ["ERA5 is the ground truth for every model", "A “record” is the 1979–2017 ERA5 maximum at that grid cell"],
};

export function baseProject(): Project {
  return {
    id: PID,
    title: "New investigation",
    stage: "clarify",
    autonomous: true,
    settings: { depth: "deep", max_papers: 300, citation_hops: 1, budget: { llm_usd: 100, gpu_hours: 0 } },
    brief: null,
    chosen_gap: null,
    plan: null,
    blueprint: null,
    review: null,
    created_at: T0,
    updated_at: T0,
  };
}

const msg = (id: string, role: "user" | "assistant", content = "") => ({
  id,
  project_id: PID,
  role,
  content,
  created_at: T0,
});

export const USER_MSG: Message = { ...msg("m1", "user", QUESTION), kind: "text", payload: null };

export const QUESTIONS_MSG: Extract<Message, { kind: "questions" }> = {
  ...msg("m2", "assistant"),
  kind: "questions",
  payload: {
    round: 1,
    message: "An important question. Three choices will shape the investigation:",
    questions: [
      {
        id: "q1",
        question: "Which AI models should be tested?",
        why: "Only some models publish their weights, which we need to re-run forecasts.",
        multi: false,
        options: [
          { label: "Leading open models", detail: "GraphCast and Pangu-Weather — weights are public, so every forecast can be re-run." },
          { label: "Every published model", detail: "Broader, but many can only be compared on archived forecasts." },
          { label: "GraphCast only", detail: "Deepest, but says nothing about AI models in general." },
        ],
      },
      {
        id: "q2",
        question: "What should count as “record-breaking”?",
        why: "The definition decides which events are studied.",
        multi: false,
        options: [
          { label: "Beats the prior record at that place", detail: "Objective, and directly tests going beyond the training data." },
          { label: "Top 1% of hot days", detail: "More events, but most are not beyond the training data." },
          { label: "Heatwaves in the news", detail: "Easy to explain, but chosen subjectively." },
        ],
      },
      {
        id: "q3",
        question: "Should it also try to fix the problem?",
        why: "A fix needs extra training and roughly doubles the compute.",
        multi: false,
        options: [
          { label: "Diagnose and attempt a fix", detail: "Fine-tune a model and test it on held-out heatwaves." },
          { label: "Diagnose only", detail: "Cheaper; reports the problem without a remedy." },
        ],
      },
    ],
  },
};

export const AUTO_ANSWERS = [
  { question_id: "q1", selected: ["Leading open models"], other: null, rationale: "Re-running forecasts is the only way to cover heatwaves after 2020." },
  { question_id: "q2", selected: ["Beats the prior record at that place"], other: null, rationale: "It is the definition that actually tests going beyond the training data." },
  { question_id: "q3", selected: ["Diagnose and attempt a fix"], other: null, rationale: "A fix makes the finding actionable, and fits in the $100 budget." },
];

export const BRIEF_MSG: Extract<Message, { kind: "brief" }> = {
  ...msg("m4", "assistant"),
  kind: "brief",
  payload: {
    message: "Here is the research brief I'll work from. Confirming automatically at **deep** depth.",
    brief: BRIEF,
  },
};

// ── Literature ─────────────────────────────────────────────────────────────

const P = (
  id: string,
  title: string,
  authors: string[],
  year: number,
  venue: string,
  citations: number,
  relevance: number,
  origin: "search" | "citation" = "search",
): LitPaper => ({
  id,
  title,
  abstract: null,
  tldr: null,
  year,
  venue,
  authors,
  citation_count: citations,
  doi: null,
  url: null,
  pdf_url: null,
  notes: null,
  relevance,
  reason: null,
  origin,
});

export const PAPERS: LitPaper[] = [
  P("p01", "Learning skillful medium-range global weather forecasting", ["Lam", "Sanchez-Gonzalez", "Battaglia"], 2023, "Science", 900, 0.98),
  P("p02", "Accurate medium-range global weather forecasting with 3D neural networks", ["Bi", "Xie", "Tian"], 2023, "Nature", 900, 0.97),
  P("p03", "WeatherBench 2: A benchmark for the next generation of data-driven global weather models", ["Rasp", "Hoyer", "Sha"], 2024, "JAMES", 300, 0.96),
  P("p04", "Do data-driven models beat numerical models in forecasting weather extremes?", ["Olivetti", "Messori"], 2024, "Geosci. Model Dev.", 80, 0.97),
  P("p05", "Can AI weather models predict out-of-training gray swan tropical cyclones?", ["Sun", "Hassanzadeh"], 2025, "PNAS", 40, 0.93),
  P("p06", "On some limitations of current machine learning weather prediction models", ["Bonavita"], 2024, "Geophys. Res. Lett.", 90, 0.92),
  P("p07", "Increasing probability of record-shattering climate extremes", ["Fischer", "Sippel", "Knutti"], 2021, "Nat. Clim. Change", 400, 0.9),
  P("p08", "Probabilistic weather forecasting with machine learning", ["Price", "Sanchez-Gonzalez", "Willson"], 2025, "Nature", 200, 0.88),
  P("p09", "Neural general circulation models for weather and climate", ["Kochkov", "Yuval", "Hoyer"], 2024, "Nature", 300, 0.86),
  P("p10", "The ERA5 global reanalysis", ["Hersbach", "Bell", "Thépaut"], 2020, "Q. J. R. Meteorol. Soc.", 9000, 0.85, "citation"),
  P("p11", "Global extreme heat forecasting using neural weather models", ["Lopez-Gomez", "McGovern", "Agrawal"], 2023, "AI Earth Syst.", 60, 0.91),
  P("p12", "Rapid attribution analysis of the extraordinary heat wave on the Pacific coast of the US and Canada in June 2021", ["Philip", "Kew", "Otto"], 2022, "Earth Syst. Dynam.", 300, 0.84),
  P("p13", "Can artificial intelligence-based weather prediction models simulate the butterfly effect?", ["Selz", "Craig"], 2023, "Geophys. Res. Lett.", 60, 0.8, "citation"),
  P("p14", "FuXi: a cascade machine learning forecasting system for 15-day global weather forecast", ["Chen", "Zhong", "Li"], 2023, "npj Clim. Atmos. Sci.", 300, 0.83),
  P("p15", "A foundation model for the Earth system", ["Bodnar", "Bruinsma", "Perdikaris"], 2025, "Nature", 100, 0.82),
  P("p16", "The rise of data-driven weather forecasting", ["Ben Bouallègue", "Clare", "Pappenberger"], 2024, "Bull. Am. Meteorol. Soc.", 150, 0.81),
  P("p17", "The most at-risk regions in the world for high-impact heatwaves", ["Thompson", "Mitchell", "Mitchell"], 2023, "Nat. Commun.", 100, 0.78, "citation"),
  P("p18", "An Introduction to Statistical Modeling of Extreme Values", ["Coles"], 2001, "Springer", 9000, 0.74, "citation"),
];

/** Streams through the source-finder scene: relevant and irrelevant hits. */
export const STREAM: { title: string; venue: string; year: number; keep: boolean; score: number; src: "S2" | "OA" | "CIT" }[] = [
  ...PAPERS.slice(0, 9).map((p, i) => ({ title: p.title, venue: p.venue!, year: p.year!, keep: true, score: p.relevance!, src: (i % 3 === 2 ? "OA" : "S2") as "S2" | "OA" })),
  { title: "Heat stress and labour productivity in South Asian agriculture", venue: "Lancet Planet. Health", year: 2021, keep: false, score: 0.12, src: "OA" },
  { title: "Urban heat island mapping from Landsat with deep learning", venue: "Remote Sens. Environ.", year: 2020, keep: false, score: 0.21, src: "S2" },
  { title: "Skilful precipitation nowcasting using deep generative models of radar", venue: "Nature", year: 2021, keep: true, score: 0.56, src: "S2" },
  { title: "Crop yield response to extreme heat in the US Midwest", venue: "PNAS", year: 2019, keep: false, score: 0.17, src: "OA" },
  ...PAPERS.slice(9).map((p) => ({ title: p.title, venue: p.venue!, year: p.year!, keep: true, score: p.relevance!, src: (p.origin === "citation" ? "CIT" : "S2") as "S2" | "CIT" })),
  { title: "Public perception of heatwave warnings in Europe", venue: "Int. J. Disaster Risk Reduct.", year: 2022, keep: false, score: 0.08, src: "OA" },
  { title: "AIFS – ECMWF's data-driven forecasting system", venue: "arXiv", year: 2024, keep: true, score: 0.79, src: "S2" },
  { title: "Spectral bias in neural operators for turbulent flows", venue: "J. Comput. Phys.", year: 2023, keep: true, score: 0.61, src: "CIT" },
  { title: "Air-conditioning demand forecasting for power grids", venue: "Appl. Energy", year: 2020, keep: false, score: 0.05, src: "OA" },
];

export const QUERIES = [
  "machine learning weather prediction extremes",
  "GraphCast heatwave forecast skill",
  "record-shattering heat extremes",
  "out-of-distribution weather model",
  "WeatherBench 2 extremes evaluation",
  "spectral smoothing neural weather models",
  "extreme value theory temperature records",
  "fine-tuning weather foundation models",
];

export const CONCEPTS = [
  "ERA5",
  "GraphCast",
  "Pangu-Weather",
  "IFS HRES",
  "Record-shattering",
  "Extreme value theory",
  "Spectral smoothing",
  "WeatherBench 2",
  "Fine-tuning",
  "Heat domes",
];

/** The paper the "Reading" popup extracts notes from. */
export const READING = {
  title: "WeatherBench 2: A benchmark for the next generation of data-driven global weather models",
  meta: "Rasp et al. · JAMES · 2024",
  notes: [
    ["Contribution", "An open benchmark and archive for scoring global AI and physics forecasts against ERA5."],
    ["Key finding", "Leading AI models match or beat IFS HRES on headline deterministic scores."],
    ["Methods", "RMSE and ACC by lead time · energy spectra · probabilistic scores"],
    ["Datasets", "ERA5 0.25° · archived GraphCast, Pangu-Weather and HRES forecasts"],
    ["Limitation", "Headline scores average over all days; record extremes are not targeted."],
  ],
};

export const OVERVIEW: Overview = {
  summary:
    "Open AI models (**GraphCast, Pangu-Weather**) now match or beat ECMWF's physics model on average scores, and early studies find mixed results on extremes. Separately, climate studies show **record-shattering heat is becoming more likely**. Two threads have not met: no study measures whether AI forecast error grows with *how far* an event exceeds the training record, or tests that the training record is the **cause**.",
  themes: [
    { name: "AI weather models", description: "Graph and transformer models trained on ERA5 reanalysis.", paper_ids: ["p01", "p02", "p14"] },
    { name: "Benchmarks & extremes", description: "How AI forecasts are scored, and early looks at extremes.", paper_ids: ["p03", "p04", "p11"] },
    { name: "Known limitations", description: "Smoothing, lost small scales and out-of-training events.", paper_ids: ["p06", "p13", "p05"] },
    { name: "Record-shattering heat", description: "Why records are broken by ever larger margins.", paper_ids: ["p07", "p12", "p17"] },
  ],
  common_methods: ["RMSE by lead time", "Energy spectra", "Extreme value theory", "Fine-tuning"],
  common_datasets: ["ERA5", "WeatherBench 2", "IFS HRES archive"],
  open_problems: [
    "Does AI error grow with how far an event exceeds the training record?",
    "Is the training record the cause, or just correlated with hard weather?",
    "Can models be fixed for extremes without losing everyday skill?",
  ],
};

export function litRun(over: Partial<Run> = {}): Run {
  return {
    id: "lit1",
    kind: "literature",
    status: "running",
    phase: "searching",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  };
}

// ── Gaps ───────────────────────────────────────────────────────────────────

const score = (s: number, why: string) => ({ score: s, why });

export const GAPS: Gap[] = [
  {
    id: "g1",
    title: "Do AI forecasts fail in proportion to how far heat beats the training record?",
    question:
      "For heatwaves after 2018, does AI-model peak bias scale with record exceedance more steeply than for the physics model — and does tail-aware fine-tuning remove that scaling?",
    gap_type: "causal_gap",
    why_open: "Extremes studies report average bias; none relate it to exceedance of the training record or test causation.",
    hypothesis: "AI peak bias grows ~3× faster with exceedance than physics-model bias; retraining on a shorter record shifts the failure point.",
    approach: "Re-forecast every record event 2018–2023; regress bias on exceedance; counterfactual retraining; tail-aware fine-tuning.",
    data_needed: "ERA5, WeatherBench 2 HRES archive, GraphCast and Pangu weights",
    compute_needed: "Runs on OpenScientist Cloud",
    risks: ["Few events at the largest exceedances", "Fine-tuning may hurt average skill"],
    supporting_paper_ids: ["p04", "p05", "p07"],
    novelty_queries: ["AI weather model record exceedance bias", "GraphCast out-of-distribution heat", "fine-tuning weather model extremes"],
    scores: {
      novelty: score(5, "No study relates AI heat error to training-record exceedance."),
      feasibility: score(4, "All data and weights are public."),
      impact: score(5, "Heat warnings increasingly rely on AI forecasts."),
      testability: score(5, "Clear regression slope and a causal counterfactual."),
    },
    novelty_check: {
      status: "novel",
      explanation: "Closest work compares extremes without exceedance, or studies cyclones. None tests heat or a fix.",
      closest: [
        { title: "Do data-driven models beat numerical models in forecasting weather extremes?", year: 2024, url: null, in_review: true, overlap: "Compares AI and HRES on extremes — but not by record exceedance, and offers no fix." },
        { title: "Can AI weather models predict out-of-training gray swan tropical cyclones?", year: 2025, url: null, in_review: true, overlap: "Tests out-of-training events — for tropical cyclones, not heat." },
      ],
    },
    overall: 4.7,
  },
  {
    id: "g2",
    title: "Ensemble AI forecasts of heat-extreme probabilities",
    question: "Are GenCast ensembles calibrated for record heat?",
    gap_type: "evaluation_gap",
    why_open: "Probabilistic scores are reported only on average days.",
    hypothesis: "Ensembles are under-dispersive at the tail.",
    approach: "Rank histograms on record events.",
    data_needed: "GenCast forecasts",
    compute_needed: "Cloud",
    risks: ["Limited ensemble archive"],
    supporting_paper_ids: ["p08"],
    novelty_queries: [],
    scores: { novelty: score(4, ""), feasibility: score(3, ""), impact: score(4, ""), testability: score(5, "") },
    novelty_check: { status: "partially_addressed", explanation: "GenCast paper reports some extreme-event scores.", closest: [] },
    overall: 4.05,
  },
  {
    id: "g3",
    title: "Soil-moisture feedbacks in AI heatwave forecasts",
    question: "Do AI models miss heat amplified by dry soils?",
    gap_type: "mechanism",
    why_open: "AI models do not take soil moisture as input.",
    hypothesis: "Bias is largest after droughts.",
    approach: "Condition bias on antecedent soil moisture.",
    data_needed: "ERA5-Land",
    compute_needed: "CPU",
    risks: ["Confounded with exceedance"],
    supporting_paper_ids: ["p12"],
    novelty_queries: [],
    scores: { novelty: score(4, ""), feasibility: score(4, ""), impact: score(3, ""), testability: score(3, "") },
    novelty_check: { status: "partially_addressed", explanation: "Studied for physics models, not AI.", closest: [] },
    overall: 3.6,
  },
  {
    id: "g4",
    title: "Record cold-air outbreaks",
    question: "Is the failure symmetric for record cold?",
    gap_type: "generalisation",
    why_open: "Cold extremes are less studied.",
    hypothesis: "Symmetric underprediction.",
    approach: "Same pipeline for cold records.",
    data_needed: "ERA5",
    compute_needed: "Cloud",
    risks: ["Few post-2018 cold records"],
    supporting_paper_ids: ["p06"],
    novelty_queries: [],
    scores: { novelty: score(3, ""), feasibility: score(4, ""), impact: score(3, ""), testability: score(3, "") },
    novelty_check: { status: "unchecked", explanation: "Too few events to check reliably.", closest: [] },
    overall: 3.35,
  },
  {
    id: "g5",
    title: "Compound heat–drought at sub-seasonal leads",
    question: "Can AI models anticipate compound events weeks ahead?",
    gap_type: "new_question",
    why_open: "AI models are evaluated to 10–15 days.",
    hypothesis: "Skill vanishes beyond two weeks.",
    approach: "Extended rollouts.",
    data_needed: "ERA5",
    compute_needed: "Cloud",
    risks: ["Rollouts become unstable"],
    supporting_paper_ids: ["p09"],
    novelty_queries: [],
    scores: { novelty: score(4, ""), feasibility: score(2, ""), impact: score(4, ""), testability: score(2, "") },
    novelty_check: { status: "unchecked", explanation: "Out of scope for current open models.", closest: [] },
    overall: 3.0,
  },
];

export function gapsRun(over: Partial<GapsRun> = {}): GapsRun {
  return {
    id: "gap1",
    kind: "gaps",
    status: "running",
    phase: "proposing",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  };
}

// ── Plan ───────────────────────────────────────────────────────────────────

const task = (id: string, title: string, kind: string, depends_on: string[], effort: "S" | "M" | "L" = "M") => ({
  id,
  title,
  description: "",
  kind,
  inputs: [],
  outputs: [],
  depends_on,
  effort,
  tools_hint: [],
});

export const PLAN: ResearchPlan = {
  title: "Out of distribution, out of reach? AI forecasts of record-shattering heat",
  research_question: GAPS[0].question,
  hypothesis:
    "Day-5 peak bias of AI models scales with record exceedance at least 2× more steeply than IFS HRES; tail-aware fine-tuning halves that slope with < 1% loss in everyday RMSE.",
  null_hypothesis: "Bias–exceedance slopes do not differ between AI models and HRES (Δslope = 0).",
  objectives: [
    "Detect every record-shattering heat event 2018–2023 in ERA5",
    "Re-forecast each event with GraphCast and Pangu-Weather; collect HRES forecasts",
    "Relate peak bias to record exceedance and test causation by counterfactual retraining",
    "Fine-tune with a tail-aware loss and evaluate on held-out events",
  ],
  background: "AI models match physics models on average, but record heat lies outside their training data by construction.",
  study_type: "computational_experiment",
  phases: [
    { id: "P1", name: "Data & events", goal: "Data access, compute and event catalogue", tasks: [task("T1", "Stand up ERA5 & WeatherBench 2 access", "data", []), task("T2", "Set up compute & MCP tools", "infrastructure", []), task("T3", "Detect record-shattering events", "analysis", ["T1"])] },
    { id: "P2", name: "Hindcasts", goal: "Re-forecast every event", tasks: [task("T4", "GraphCast & Pangu hindcasts", "modeling", ["T2", "T3"], "L"), task("T5", "Collect HRES forecasts", "data", ["T3"])] },
    { id: "P3", name: "Mechanism", goal: "Why do forecasts fail?", tasks: [task("T6", "Score peak bias vs exceedance", "analysis", ["T4", "T5"]), task("T7", "Spectral smoothing analysis", "analysis", ["T4"]), task("T8", "Counterfactual retraining (1979–2005)", "modeling", ["T2"], "L")] },
    { id: "P4", name: "Fix", goal: "Tail-aware fine-tuning", tasks: [task("T9", "Tail-aware fine-tuning", "modeling", ["T6"], "L"), task("T10", "Evaluate on held-out events", "analysis", ["T9"])] },
    { id: "P5", name: "Analysis", goal: "Statistics and figures", tasks: [task("T11", "Event-block bootstrap & tests", "analysis", ["T6", "T8", "T10"]), task("T12", "Figures", "writing", ["T7", "T11"], "S")] },
  ],
  datasets: [
    { name: "ARCO-ERA5", description: "Hourly ERA5 at 0.25°, analysis-ready Zarr on Google Cloud", source: "https://github.com/google-research/arco-era5", access: "public_bucket", role: "ground truth & inputs" },
    { name: "WeatherBench 2", description: "Archived IFS HRES and AI forecasts", source: "https://weatherbench2.readthedocs.io", access: "public_bucket", role: "physics baseline" },
    { name: "GraphCast & Pangu-Weather weights", description: "Open model checkpoints", source: "https://github.com/google-deepmind/graphcast", access: "public_download", role: "models under test" },
  ],
  methods: [
    { name: "Peak bias regression", purpose: "Slope of bias on record exceedance, per model." },
    { name: "Counterfactual retraining", purpose: "Train on 1979–2005 to move the record and test causation." },
    { name: "Tail-aware fine-tuning", purpose: "Quantile loss on the hottest 1% of days." },
  ],
  baselines: ["IFS HRES (physics)", "Persistence", "Climatology"],
  metrics: [
    { name: "Peak bias", definition: "Forecast minus ERA5 event peak at day-5 lead (K)", success_threshold: "Report with 95% CI" },
    { name: "Δslope", definition: "AI minus HRES slope of bias on exceedance", success_threshold: "< 0, p < 0.01" },
    { name: "Everyday RMSE", definition: "T2m RMSE on all 2020 days", success_threshold: "Fine-tuned ≤ +1%" },
  ],
  validation_strategy: "Leave-one-event-cluster-out evaluation; event-block bootstrap with 10,000 resamples.",
  success_criteria: ["Δslope < 0 with p < 0.01", "Fine-tuning reduces peak bias ≥ 30% with ≤ 1% RMSE cost"],
  compute_estimate: "≈ 17 h on OpenScientist Cloud",
  duration_estimate: "About 20 hours end to end",
  risks: [
    { risk: "Few events at large exceedance", likelihood: "medium", mitigation: "Report CIs; pool across models" },
    { risk: "Fine-tuning overfits to heat", likelihood: "medium", mitigation: "Evaluate everyday RMSE on 2020" },
  ],
  deliverables: ["Event catalogue", "Hindcast archive", "Fine-tuned model", "Paper"],
  open_questions: ["Does the effect hold for ensembles?"],
};

export const PLAN_AUDIT = {
  revised: true,
  first: {
    field: "Atmospheric science",
    established_theory: ["Reanalysis underestimates station extremes", "MSE training favours smooth forecasts"],
    contribution: "",
    problems: [
      { severity: "FATAL" as const, kind: "training_leakage", problem: "The first draft included 2016–2017 events, which are inside the models' training period.", fix: "Use only events after every model's training cutoff." },
      { severity: "MAJOR" as const, kind: "unfair_comparison", problem: "HRES was scored against its own analysis, the AI models against ERA5.", fix: "Score every model against ERA5 on the same grid." },
    ],
  },
  final: {
    field: "Atmospheric science",
    established_theory: ["Reanalysis underestimates station extremes", "MSE training favours smooth forecasts"],
    contribution: "The first causal test of whether AI weather models fail in proportion to how far heat exceeds their training record — with a fix.",
    problems: [],
  },
};

export function planRun(over: Partial<PlanRun> = {}): PlanRun {
  return {
    id: "plan1",
    kind: "plan",
    status: "running",
    phase: "drafting",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  };
}

// ── Blueprint ──────────────────────────────────────────────────────────────

const bpTask = (id: string, title: string, agent: string, depends_on: string[], objective: string, est = 30, cost = 2) => ({
  id,
  title,
  agent,
  objective,
  steps: [] as string[],
  inputs: [] as { path: string; source: string }[],
  outputs: [] as { path: string; format: string; description: string }[],
  acceptance_checks: [] as string[],
  depends_on,
  tools: ["run_python"],
  resources: [],
  compute: { kind: "cpu" as const, est_minutes: est, timeout_minutes: est * 3 },
  max_cost_usd: cost,
  retries: 2,
  human_required: false,
});

export const MASTER: MasterPlan = {
  title: "Record-shattering heat benchmark for AI weather models",
  summary:
    "Six agents build their own data and compute tooling, catalogue every record heat event since 2018, re-forecast them, test causation with a counterfactual model, fine-tune a fix and evaluate it.",
  python_packages: ["xarray", "zarr", "gcsfs", "jax", "graphcast", "onnxruntime", "xesmf", "scipy", "mcp", "matplotlib"],
  system_requirements: [],
  agents: [
    { id: "A1", name: "Data Engineer", model_tier: "standard", tools: ["mcp:era5-arco", "mcp:hres-archive", "run_python"], instructions: "Data access, mirroring and validation." },
    { id: "A2", name: "Climate Scientist", model_tier: "reasoning", tools: ["mcp:era5-arco", "run_python"], instructions: "Event detection and physical analysis." },
    { id: "A3", name: "Infra Engineer", model_tier: "standard", tools: ["web_search", "http_request", "run_shell"], instructions: "Set up compute and write the project's MCP servers." },
    { id: "A4", name: "ML Engineer", model_tier: "reasoning", tools: ["mcp:forecast-runner", "spawn_subagents", "run_job"], instructions: "Hindcasts, retraining and fine-tuning." },
    { id: "A5", name: "Statistician", model_tier: "standard", tools: ["run_python"], instructions: "Bias regression, bootstrap and tests." },
    { id: "A6", name: "Figure Maker", model_tier: "bulk", tools: ["run_python"], instructions: "Publication figures." },
  ],
  datasets: [
    { id: "D1", name: "ARCO-ERA5 (0.25°, hourly)", url: "https://github.com/google-research/arco-era5", access_method: "Public GCS Zarr via own MCP server", format: "zarr", license: "Copernicus licence", notes: "", verified: true },
    { id: "D2", name: "WeatherBench 2 forecasts", url: "https://weatherbench2.readthedocs.io", access_method: "Public GCS Zarr", format: "zarr", license: "Open", notes: "", verified: true },
    { id: "D3", name: "GraphCast checkpoints", url: "https://github.com/google-deepmind/graphcast", access_method: "Download", format: "npz", license: "CC BY-NC-SA 4.0", notes: "", verified: true },
    { id: "D4", name: "Pangu-Weather ONNX", url: "https://github.com/198808xc/Pangu-Weather", access_method: "Download", format: "onnx", license: "BY-NC-SA 4.0", notes: "", verified: true },
  ],
  tasks: [
    bpTask("T1", "ERA5 & WeatherBench 2 access", "A1", [], "Stand up the era5-arco MCP server and mirror needed fields."),
    bpTask("T2", "Set up compute & MCP tools", "A3", [], "Allocate cloud workers and register MCP servers."),
    bpTask("T3", "Detect record events", "A2", ["T1"], "Find every 2018–2023 event beating the 1979–2017 record."),
    bpTask("T4", "GraphCast & Pangu hindcasts", "A4", ["T2", "T3"], "10-day forecasts from 5 start dates per event.", 240, 6),
    bpTask("T5", "Collect HRES forecasts", "A1", ["T3"], "Matching HRES forecasts from WeatherBench 2."),
    bpTask("T6", "Peak bias vs exceedance", "A5", ["T4", "T5"], "Score every forecast against ERA5 on one grid."),
    bpTask("T7", "Spectral smoothing", "A2", ["T4"], "Energy spectra of forecasts vs ERA5."),
    bpTask("T8", "Counterfactual retraining", "A4", ["T2"], "Train GraphCast-small on 1979–2005 only.", 300, 8),
    bpTask("T9", "Tail-aware fine-tuning", "A4", ["T6"], "Fine-tune with a quantile loss on the hottest 1% of days.", 180, 6),
    bpTask("T10", "Held-out evaluation", "A5", ["T9"], "Leave-one-event-cluster-out evaluation."),
    bpTask("T11", "Bootstrap & tests", "A5", ["T6", "T8", "T10"], "Event-block bootstrap, slope tests."),
    bpTask("T12", "Figures", "A6", ["T7", "T11"], "Maps, scatter plots, spectra, tables."),
  ],
  checkpoints: [{ after_task: "T3", reason: "Confirm every event is after the models' training data." }],
  llm_usd_estimate: 58,
  compute_hours_estimate: 17,
  execution_notes: ["Up to 4 tasks run in parallel", "Heavy work runs on OpenScientist Cloud", "Failed tasks retry on a stronger model"],
};

export function bpRun(over: Partial<BlueprintRun> = {}): BlueprintRun {
  return {
    id: "bp1",
    kind: "blueprint",
    status: "running",
    phase: "resolving",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  };
}

export const BP_RESULT = {
  master_plan: MASTER,
  warnings: [],
  capabilities: [],
  budget: { llm_usd: 100, gpu_hours: 0 },
};

// ── Execution ──────────────────────────────────────────────────────────────

export function taskState(id: string, agent: string, over: Partial<TaskState> = {}): TaskState {
  return {
    id: `ts-${id}`,
    task_id: id,
    agent,
    status: "pending",
    attempts: 0,
    cost: 0,
    summary: null,
    artifacts: [],
    checks: [],
    issues: [],
    events: [],
    note: null,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

/** Cost of each task in the final execution card. */
export const TASK_COST: Record<string, number> = {
  T1: 1.12, T2: 0.64, T3: 1.8, T4: 19.4, T5: 0.42, T6: 1.36, T7: 0.98, T8: 23.6, T9: 18.2, T10: 2.9, T11: 1.24, T12: 0.74,
};

/** Agent tool calls shown streaming in the mission-control scene, per task. */
export const TOOL_SCRIPT: Record<string, { tool: string; args: string; sub?: string }[]> = {
  T1: [
    { tool: "mcp:era5-arco", args: "list_variables → 273 fields · 1940–2024 · 0.25°" },
    { tool: "mcp:era5-arco", args: "get_field 2m_temperature 1979–2023 → mirrored 1.9 TB" },
    { tool: "skill+", args: "learned nan_safe_zarr_reader (12 missing chunks repaired)" },
  ],
  T2: [
    { tool: "run_shell", args: "cloud workers allocated · accelerated · ready" },
    { tool: "mcp", args: "registered era5-arco · forecast-runner · hres-archive ✓" },
  ],
  T3: [
    { tool: "run_python", args: "record_1979_2017 = t2m.max('time')  # per grid cell" },
    { tool: "run_python", args: "47 events beat the record by ≥ 1 K · largest +6.1 K (Jun 2021, BC)" },
  ],
  T4: [
    { tool: "spawn_subagents", args: "4 sub-agents: graphcast-a · graphcast-b · pangu-a · pangu-b" },
    { tool: "mcp:forecast-runner", args: "rollout graphcast 0.25° 10 d × 235 starts", sub: "graphcast-a" },
    { tool: "error", args: "out of memory at step 31 (worker memory limit)", sub: "graphcast-a" },
    { tool: "skill+", args: "wrote sharded_rollout: split across workers, checkpoint every 8 steps" },
    { tool: "mcp:forecast-runner", args: "2,350 forecasts done", sub: "pangu-b" },
  ],
  T5: [{ tool: "mcp:hres-archive", args: "fetch hres t2m for 47 events × 5 starts ✓" }],
  T6: [
    { tool: "run_python", args: "peak_bias = fc.max('time') - era5.max('time')" },
    { tool: "verifier", args: "✕ forecasts at 0.25° compared with ERA5 at 1.5° — regrid mismatch" },
    { tool: "skill+", args: "wrote regrid_to_era5 (conservative, xesmf) · retry on OS-Reasoner" },
    { tool: "run_python", args: "slope: GraphCast −0.52 · Pangu −0.61 · HRES −0.14 K/K" },
  ],
  T7: [{ tool: "run_python", args: "day-5 spectra: −23% energy at wavenumbers > 40 (GraphCast)" }],
  T8: [
    { tool: "run_job", args: "train graphcast_small --years 1979-2005 --steps 120k", sub: "counterfactual" },
    { tool: "check_process", args: "step 96k / 120k · loss 0.0421", sub: "counterfactual" },
    { tool: "post_note", args: "events beyond the 2005 record now fail like true record breakers" },
  ],
  T9: [
    { tool: "run_job", args: "finetune graphcast --loss mse+pinball(q=0.99) --λ 0.3" },
    { tool: "skill", args: "reused sharded_rollout for validation rollouts" },
  ],
  T10: [{ tool: "run_python", args: "held-out peak bias −2.6 → −1.5 K (−42%) · RMSE +0.6%" }],
  T11: [
    { tool: "skill+", args: "wrote bootstrap_by_event (10,000 event-block resamples)" },
    { tool: "run_python", args: "Δslope GraphCast−HRES = −0.38 K/K · 95% CI [−0.52, −0.25] · p < 0.001" },
  ],
  T12: [{ tool: "run_python", args: "fig1_events · fig2_exceedance · fig3_counterfactual · fig4_spectra" }],
};

// ── Report & review ────────────────────────────────────────────────────────

export function reportRun(over: Partial<ReportRun> = {}): ReportRun {
  return {
    id: "rep1",
    kind: "report",
    status: "running",
    phase: "consolidating",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  };
}

export const PAPER_TITLE = "Out of Distribution, Out of Reach: AI Weather Models Underpredict Record-Shattering Heatwaves";

export const REPORT_RESULT: NonNullable<ReportRun["result"]> = {
  scaffold: {
    title: PAPER_TITLE,
    one_sentence_summary:
      "Across 47 record-shattering heat events since 2018, AI weather models underpredict the peak in proportion to how far it beats the training record — 3.7× more steeply than the physics model — and a tail-aware fine-tune removes 42% of the error.",
    hypothesis_verdict: "supported",
    verdict_explanation:
      "GraphCast's bias–exceedance slope was −0.52 K/K vs −0.14 for IFS HRES (Δ = −0.38, 95% CI −0.52 to −0.25, p < 0.001). Moving the training record by retraining on 1979–2005 moved the failure point with it.",
    findings: [
      { claim: "On ordinary days AI models beat HRES (day-5 T2m RMSE 1.71 vs 1.92 K); on record events they are 2.4× more biased (−2.6 vs −1.1 K).", evidence: ["T6", "table1.csv"], strength: "strong", relation: "motivates" },
      { claim: "AI peak bias grows with record exceedance at −0.52 K/K (GraphCast) and −0.61 K/K (Pangu), vs −0.14 K/K for HRES.", evidence: ["T6", "T11", "fig2_exceedance.pdf"], strength: "strong", relation: "supports H₁" },
      { claim: "Counterfactual: a model trained to 2005 fails on events above the 2005 record that the full model handles (−2.4 vs −1.3 K) — the training record is causal.", evidence: ["T8", "fig3_counterfactual.pdf"], strength: "moderate", relation: "causal" },
      { claim: "Day-5 AI forecasts lose 23% of small-scale energy, consistent with smoothing toward climatology.", evidence: ["T7", "fig4_spectra.pdf"], strength: "moderate", relation: "mechanism" },
      { claim: "Tail-aware fine-tuning cuts held-out peak bias by 42% (−2.6 → −1.5 K) at +0.6% everyday RMSE.", evidence: ["T9", "T10"], strength: "strong", relation: "fix" },
    ],
    success_criteria: [
      { criterion: "Δslope < 0 with p < 0.01", status: "met", evidence: "−0.38 K/K, p < 0.001" },
      { criterion: "Fine-tuning reduces peak bias ≥ 30% with ≤ 1% RMSE cost", status: "met", evidence: "−42%, +0.6% RMSE" },
    ],
    figures: [],
    limitations: ["ERA5 underestimates station-level extremes", "Ensemble models (GenCast) not tested", "47 events; few beyond +5 K"],
    deviations: ["Added a regridding step after the verifier caught a grid mismatch"],
  },
  agent: { status: "done", summary: "", cost: 1.92, issues: [] },
  files: { tex: true, pdf: true, bib: true },
  citations: { used: Array.from({ length: 52 }, (_, i) => `ref${i}`), unknown: [], available: 118 },
  audit: [],
};

export const ITERATIONS: ReviewIteration[] = [
  {
    n: 1,
    session: 1,
    review_run_id: "r1",
    verdict: "major_revision",
    judged: true,
    decision: "repair",
    reason: "",
    score: 6.1,
    score_rationale: "Important result, but fine-tuning and test events may share the same heatwaves, and Table 1 disagrees with metrics.csv for Pangu.",
    blocking: { FATAL: 0, MAJOR: 2 },
    open_concerns: 1,
    issues: [],
    cost_usd: 1.1,
    level: "execution",
    rerun_tasks: ["T10", "T11"],
    carried_over: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T12"],
  },
  {
    n: 2,
    session: 1,
    review_run_id: "r2",
    verdict: "minor_revision",
    judged: true,
    decision: "improve",
    reason: "",
    score: 8.2,
    score_rationale: "Sound and well controlled. Discuss ERA5's own underestimation of station extremes.",
    blocking: { FATAL: 0, MAJOR: 0 },
    open_concerns: 1,
    issues: [],
    cost_usd: 1.2,
    level: "report",
  },
  {
    n: 3,
    session: 1,
    review_run_id: "r3",
    verdict: "accept",
    judged: true,
    decision: "approved",
    reason: "",
    score: 9.2,
    score_rationale: "Claims match the evidence, causal design is convincing, limitations are disclosed. Ready for submission.",
    blocking: { FATAL: 0, MAJOR: 0 },
    open_concerns: 0,
    issues: [],
    cost_usd: 0.8,
    level: "report",
  },
];

export const ROUND1_ISSUES = [
  { id: "i1", track_id: "k1", severity: "MAJOR" as const, category: "leakage", title: "Some test days come from heatwaves used in fine-tuning; evaluate on held-out heatwave clusters only.", blocking: true, open_concern: false, verification: "verified", grounding: "splits/finetune.json", tracking: { status: "new" as const, previous_ids: [] }, referee: "methods" },
  { id: "i2", track_id: "k2", severity: "MAJOR" as const, category: "table_mismatch", title: "Table 1 reports Pangu bias −3.0 K; metrics.csv says −2.8 K.", blocking: true, open_concern: false, verification: "verified", grounding: "table1.tex", tracking: { status: "new" as const, previous_ids: [] }, referee: "lead" },
  { id: "i3", track_id: "k3", severity: "MINOR" as const, category: "context", title: "Discuss that ERA5 underestimates station-level extremes.", blocking: false, open_concern: true, verification: "verified", grounding: "paper.tex §5", tracking: { status: "new" as const, previous_ids: [] }, referee: "theory" },
];
