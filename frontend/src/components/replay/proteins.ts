// A pre-made run: do protein language models understand mutations, or remember evolution?
// Paper titles in the literature are real; the run's own results are simulated.
import type { ResearchPlan } from "@/lib/api";
import { bpTask, minorGap, paper, planTask, score } from "./kit";
import type { ReplayData } from "./types";

const PAPERS = [
  paper("p01", "Language models enable zero-shot prediction of the effects of mutations on protein function", ["Meier", "Rao", "Verkuil"], 2021, "NeurIPS", 900, 0.98),
  paper("p02", "Evolutionary-scale prediction of atomic-level protein structure with a language model", ["Lin", "Akin", "Rao"], 2023, "Science", 3000, 0.95),
  paper("p03", "ProteinGym: Large-scale benchmarks for protein fitness prediction and design", ["Notin", "Kollasch", "Ritter"], 2023, "NeurIPS", 300, 0.97),
  paper("p04", "Mega-scale experimental analysis of protein folding stability in biology and design", ["Tsuboyama", "Dauparas", "Chen"], 2023, "Nature", 500, 0.96),
  paper("p05", "Disease variant prediction with deep generative models of evolutionary data", ["Frazer", "Notin", "Dias"], 2021, "Nature", 900, 0.93),
  paper("p06", "Tranception: protein fitness prediction with autoregressive transformers and inference-time retrieval", ["Notin", "Dias", "Frazer"], 2022, "ICML", 400, 0.92),
  paper("p07", "Accurate proteome-wide missense variant effect prediction with AlphaMissense", ["Cheng", "Novati", "Pan"], 2023, "Science", 900, 0.94),
  paper("p08", "Protein language models learn evolutionary statistics of interacting sequence motifs", ["Zhang", "Wayment-Steele", "Brixi"], 2024, "PNAS", 120, 0.95),
  paper("p09", "SaProt: Protein language modeling with structure-aware vocabulary", ["Su", "Han", "Zhou"], 2024, "ICLR", 200, 0.89),
  paper("p10", "Transfer learning to leverage larger datasets for improved prediction of protein stability changes", ["Dieckhaus", "Brocidiacono", "Randolph"], 2024, "PNAS", 150, 0.91),
  paper("p11", "Robust deep learning–based protein sequence design using ProteinMPNN", ["Dauparas", "Anishchenko", "Bennett"], 2022, "Science", 2000, 0.85, "citation"),
  paper("p12", "Biological structure and function emerge from scaling unsupervised learning to 250 million protein sequences", ["Rives", "Meier", "Sercu"], 2021, "PNAS", 3000, 0.9, "citation"),
  paper("p13", "Deep generative models of genetic variation capture the effects of mutations", ["Riesselman", "Ingraham", "Marks"], 2018, "Nat. Methods", 900, 0.86, "citation"),
  paper("p14", "Learning protein fitness models from evolutionary and assay-labeled data", ["Hsu", "Nisonoff", "Fannjiang"], 2022, "Nat. Biotechnol.", 300, 0.87),
  paper("p15", "Pre-training co-evolutionary protein representations via a pairwise masked language model", ["He", "Zhang", "Mao"], 2021, "arXiv", 60, 0.78),
  paper("p16", "UniRef clusters: a comprehensive and scalable alternative for improving sequence similarity searches", ["Suzek", "Wang", "Huang"], 2015, "Bioinformatics", 2000, 0.8, "citation"),
  paper("p17", "MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets", ["Steinegger", "Söding"], 2017, "Nat. Biotechnol.", 3000, 0.79, "citation"),
  paper("p18", "Protein language models are biased by unequal sequence sampling across the tree of life", ["Ding", "Steinhardt"], 2024, "bioRxiv", 40, 0.93),
];

const GAP_QUESTION =
  "Is a protein language model's zero-shot accuracy on mutation effects explained by how many evolutionary relatives the protein had in training — and does removing those relatives cause the accuracy to collapse?";

const PLAN: ResearchPlan = {
  title: "Memorised evolution or learned physics? Homolog depth and protein language models",
  research_question: GAP_QUESTION,
  hypothesis:
    "Zero-shot Spearman of ESM-2 rises with log10 homolog count in UniRef50 (slope > 0.05 per decade); removing a family's homologs from pre-training drops its accuracy by ≥ 40% while control families change < 10%; a depth-gated hybrid with a structure-based stability model recovers ≥ 50% of the loss on low-depth proteins.",
  null_hypothesis: "Zero-shot accuracy is independent of homolog depth once assay type and protein length are controlled (slope = 0).",
  objectives: [
    "Score every ProteinGym substitution assay and the mega-scale stability set with four protein language models",
    "Count each protein's homologs in the models' training data",
    "Test causation by pre-training a small model with selected families removed",
    "Build and evaluate a depth-gated hybrid with a structure-based predictor",
  ],
  background: "Protein language models predict mutation effects without labels, but their training data is dominated by deep, well-studied families.",
  study_type: "computational_experiment",
  phases: [
    { id: "P1", name: "Data", goal: "Assays, structures and homolog counts", tasks: [planTask("T1", "ProteinGym & mega-scale stability data", "data", []), planTask("T2", "Set up compute & MCP tools", "infrastructure", []), planTask("T3", "Homolog depth in UniRef50", "analysis", ["T1"])] },
    { id: "P2", name: "Zero-shot scoring", goal: "Score every variant", tasks: [planTask("T4", "ESM-2 (650M, 3B), ESM-1v & SaProt scores", "modeling", ["T1", "T2"], "L"), planTask("T5", "Structure-based ΔΔG baseline", "modeling", ["T1"])] },
    { id: "P3", name: "Mechanism", goal: "Is depth the cause?", tasks: [planTask("T6", "Accuracy vs homolog depth", "analysis", ["T3", "T4"]), planTask("T7", "Attention-contact analysis", "analysis", ["T4"]), planTask("T8", "Counterfactual pre-training (families removed)", "modeling", ["T2", "T3"], "L")] },
    { id: "P4", name: "Fix", goal: "Depth-gated hybrid", tasks: [planTask("T9", "Depth-gated hybrid model", "modeling", ["T5", "T6"]), planTask("T10", "Held-out evaluation", "analysis", ["T9"])] },
    { id: "P5", name: "Analysis", goal: "Statistics and figures", tasks: [planTask("T11", "Bootstrap by protein & tests", "analysis", ["T6", "T8", "T10"]), planTask("T12", "Figures", "writing", ["T7", "T11"], "S")] },
  ],
  datasets: [
    { name: "ProteinGym v1.3", description: "217 deep mutational scanning assays, 2.4M variants", source: "https://proteingym.org", access: "public_download", role: "benchmark" },
    { name: "Mega-scale stability (Tsuboyama 2023)", description: "776k ΔG measurements over 479 domains", source: "https://zenodo.org/records/7992926", access: "public_download", role: "stability ground truth" },
    { name: "UniRef50 (2021_03)", description: "The clustering ESM-2 was trained on", source: "https://www.uniprot.org/help/downloads", access: "public_download", role: "homolog counts" },
  ],
  methods: [
    { name: "Masked-marginal scoring", purpose: "Zero-shot log-likelihood ratio per substitution." },
    { name: "Homolog-depth regression", purpose: "Spearman vs log10 homologs, controlling length and assay type." },
    { name: "Counterfactual pre-training", purpose: "ESM-2 35M re-trained with 40 families removed, plus a matched control run." },
    { name: "Depth-gated hybrid", purpose: "Mix language-model and structure scores by homolog depth." },
  ],
  baselines: ["Site-independent (PSSM)", "EVE", "ThermoMPNN (structure)"],
  metrics: [
    { name: "Spearman ρ", definition: "Rank correlation of score and measured fitness, per assay", success_threshold: "Report mean with 95% CI" },
    { name: "Depth slope", definition: "Change in ρ per decade of homologs", success_threshold: "> 0.05, p < 0.01" },
    { name: "Counterfactual drop", definition: "Relative ρ change for removed vs control families", success_threshold: "≥ 40% vs < 10%" },
  ],
  validation_strategy: "Protein-level cross-validation for the hybrid; bootstrap over proteins (10,000 resamples).",
  success_criteria: ["Depth slope > 0.05 with p < 0.01", "Hybrid recovers ≥ 50% of the low-depth gap"],
  compute_estimate: "≈ 21 h on OpenScientist Cloud",
  duration_estimate: "About a day end to end",
  risks: [
    { risk: "Depth confounded with protein size or assay type", likelihood: "high", mitigation: "Partial correlations and matched subsets" },
    { risk: "35M model too small to reflect large-model behaviour", likelihood: "medium", mitigation: "Report scaling across 8M, 35M and 150M" },
  ],
  deliverables: ["Per-variant score archive", "Homolog depth table", "Counterfactual checkpoints", "Hybrid model", "Paper"],
  open_questions: ["Do structure-aware language models (SaProt) inherit the same dependence?"],
};

const MASTER: ReplayData["master"] = {
  title: "Homolog depth and zero-shot mutation-effect prediction",
  summary:
    "Six agents score 2.4M variants with four protein language models, count every protein's relatives in the training data, re-train a small model with families removed to test causation, and build a depth-aware hybrid.",
  python_packages: ["torch", "fair-esm", "transformers", "biopython", "mmseqs2", "pandas", "scipy", "statsmodels", "mcp", "matplotlib"],
  system_requirements: [],
  agents: [
    { id: "A1", name: "Data Engineer", model_tier: "standard", tools: ["mcp:proteingym", "http_request", "run_python"], instructions: "Assays, structures and UniRef." },
    { id: "A2", name: "Computational Biologist", model_tier: "reasoning", tools: ["mcp:uniref-search", "run_python"], instructions: "Homolog search and biological analysis." },
    { id: "A3", name: "Infra Engineer", model_tier: "standard", tools: ["web_search", "run_shell"], instructions: "Compute and the project's MCP servers." },
    { id: "A4", name: "ML Engineer", model_tier: "reasoning", tools: ["mcp:plm-scorer", "spawn_subagents", "run_job"], instructions: "Scoring, pre-training and the hybrid." },
    { id: "A5", name: "Statistician", model_tier: "standard", tools: ["run_python"], instructions: "Regression, bootstrap and tests." },
    { id: "A6", name: "Figure Maker", model_tier: "bulk", tools: ["run_python"], instructions: "Publication figures." },
  ],
  datasets: [
    { id: "D1", name: "ProteinGym v1.3 substitutions", url: "https://proteingym.org", access_method: "Download via own MCP server", format: "csv", license: "MIT", notes: "", verified: true },
    { id: "D2", name: "Mega-scale stability", url: "https://zenodo.org/records/7992926", access_method: "Download", format: "csv", license: "CC BY 4.0", notes: "", verified: true },
    { id: "D3", name: "UniRef50 2021_03", url: "https://www.uniprot.org/help/downloads", access_method: "Download + MMseqs2 index", format: "fasta", license: "CC BY 4.0", notes: "", verified: true },
    { id: "D4", name: "ESM-2 / ESM-1v / SaProt weights", url: "https://github.com/facebookresearch/esm", access_method: "Download", format: "pt", license: "MIT", notes: "", verified: true },
  ],
  tasks: [
    bpTask("T1", "Assays & stability data", "A1", [], "Download ProteinGym and mega-scale stability; map every protein to UniProt and a structure."),
    bpTask("T2", "Set up compute & MCP tools", "A3", [], "Allocate cloud workers; write the proteingym, uniref-search and plm-scorer MCP servers."),
    bpTask("T3", "Homolog depth", "A2", ["T1"], "Count UniRef50 homologs (E < 1e-5, ≥ 30% identity) for 696 proteins.", 90, 3),
    bpTask("T4", "Zero-shot scores", "A4", ["T1", "T2"], "Masked-marginal scores for 2.4M variants with four models.", 240, 9),
    bpTask("T5", "Structure ΔΔG baseline", "A4", ["T1"], "ThermoMPNN predictions on predicted structures.", 60, 2),
    bpTask("T6", "Accuracy vs depth", "A5", ["T3", "T4"], "Spearman per assay vs log10 homologs with controls."),
    bpTask("T7", "Attention contacts", "A2", ["T4"], "Contact precision from attention vs depth."),
    bpTask("T8", "Counterfactual pre-training", "A4", ["T2", "T3"], "Re-train ESM-2 35M with 40 families removed, plus a matched control.", 300, 10),
    bpTask("T9", "Depth-gated hybrid", "A4", ["T5", "T6"], "Learn a depth-dependent mix of language-model and structure scores.", 60, 2),
    bpTask("T10", "Held-out evaluation", "A5", ["T9"], "Protein-level 5-fold evaluation."),
    bpTask("T11", "Bootstrap & tests", "A5", ["T6", "T8", "T10"], "Bootstrap over proteins, slope and drop tests."),
    bpTask("T12", "Figures", "A6", ["T7", "T11"], "Depth curves, counterfactual bars, tables."),
  ],
  checkpoints: [{ after_task: "T3", reason: "Confirm homolog counts use the exact UniRef release the models saw." }],
  llm_usd_estimate: 61,
  compute_hours_estimate: 21,
  execution_notes: ["Up to 4 tasks run in parallel", "Heavy work runs on OpenScientist Cloud", "Failed tasks retry on a stronger model"],
};

export const proteins: ReplayData = {
  slug: "protein-language-models",
  question:
    "Do protein language models actually understand which mutations will break a protein — or are they just remembering evolution?",
  shortTitle: "Protein language models & mutations",
  brief: {
    title: "Do protein language models understand mutations, or remember evolution?",
    core_question:
      "Is zero-shot mutation-effect accuracy of protein language models explained by the number of evolutionary relatives a protein had in training — and is that dependence causal?",
    summary:
      "Protein language models such as ESM predict which mutations damage a protein without any lab data, and are now used to prioritise disease variants and design enzymes. But their training data is dominated by large, well-studied families. This investigation measures how accuracy depends on a protein's evolutionary depth, tests whether removing relatives from training causes failure, and builds a fix for 'orphan' proteins.",
    domain: "Computational biology · machine learning",
    subfields: ["Protein language models", "Variant effect prediction", "Protein stability"],
    key_concepts: [
      { term: "Zero-shot prediction", definition: "scoring mutations from the model's likelihoods alone, with no lab measurements." },
      { term: "Homolog depth", definition: "how many related sequences of a protein exist in the model's training data." },
      { term: "Deep mutational scan", definition: "an experiment measuring the effect of thousands of single mutations at once." },
    ],
    scope_in: ["ESM-2, ESM-1v and SaProt", "ProteinGym substitution assays", "Mega-scale folding stability data"],
    scope_out: ["Insertions and deletions", "Multi-mutant epistasis", "Wet-lab validation"],
    result_type: "A benchmark analysis, a causal test and a depth-aware hybrid model",
    data_resources: "ProteinGym, mega-scale stability, UniRef50 (found automatically)",
    compute_resources: "OpenScientist Cloud (managed for you)",
    user_expertise: "Curious non-specialist",
    constraints: ["Budget: $100", "Every claim must trace to data or a cited paper"],
    search_keywords: ["protein language model zero-shot mutation", "ESM variant effect", "ProteinGym", "homolog depth MSA", "protein stability prediction", "training data overlap protein"],
    assumptions: ["UniRef50 2021_03 is the training distribution of ESM-2", "Deep mutational scans measure fitness with comparable noise"],
  },
  questions: {
    round: 1,
    message: "A sharp question. Three choices will shape the investigation:",
    questions: [
      {
        id: "q1",
        question: "Which models should be put to the test?",
        why: "We need open weights to re-score every mutation.",
        multi: false,
        options: [
          { label: "ESM-2, ESM-1v and SaProt", detail: "The most used open models, sequence-only and structure-aware." },
          { label: "Every model on ProteinGym", detail: "Broadest, but several are closed or MSA-dependent." },
          { label: "ESM-2 only", detail: "Deepest, but says less about language models in general." },
        ],
      },
      {
        id: "q2",
        question: "What should count as 'breaking' a protein?",
        why: "Function and stability are measured differently.",
        multi: false,
        options: [
          { label: "Both fitness and folding stability", detail: "ProteinGym fitness plus 776k stability measurements." },
          { label: "Fitness only", detail: "Simpler, but mixes many mechanisms." },
          { label: "Disease variants only", detail: "Clinically relevant, but labels are sparse." },
        ],
      },
      {
        id: "q3",
        question: "Should it test whether evolution is the cause?",
        why: "A causal test means re-training a model, which adds compute.",
        multi: false,
        options: [
          { label: "Yes — re-train with families removed", detail: "The only way to show causation, not correlation." },
          { label: "Correlation only", detail: "Cheaper, but cannot separate depth from protein type." },
        ],
      },
    ],
  },
  answers: [
    { question_id: "q1", selected: ["ESM-2, ESM-1v and SaProt"], other: null, rationale: "Open weights cover sequence-only and structure-aware models." },
    { question_id: "q2", selected: ["Both fitness and folding stability"], other: null, rationale: "Stability isolates physics from function." },
    { question_id: "q3", selected: ["Yes — re-train with families removed"], other: null, rationale: "Correlation alone would leave the main question open." },
  ],
  papers: PAPERS,
  lit: { queries: 8, found: 1874, screened: 512, included: 104, citations: 266, links: 1408 },
  overview: {
    summary:
      "Protein language models (**ESM-1v, ESM-2, SaProt**) predict mutation effects zero-shot about as well as alignment-based models, and are used for **disease variant** interpretation and design. Recent work shows they learn **co-evolutionary statistics**, and that their likelihoods are biased by uneven sampling of the tree of life. No study has tested whether accuracy is *caused* by a protein's evolutionary depth in training, or how to fix low-depth 'orphan' proteins.",
    themes: [
      { name: "Language models of proteins", description: "Masked and autoregressive models trained on UniRef.", paper_ids: ["p01", "p02", "p12"] },
      { name: "Benchmarks", description: "Deep mutational scans and stability at scale.", paper_ids: ["p03", "p04", "p14"] },
      { name: "What models learn", description: "Co-evolution, contacts and training overlap.", paper_ids: ["p08", "p18", "p15"] },
      { name: "Structure & stability", description: "Structure-aware and physics-informed predictors.", paper_ids: ["p09", "p10", "p11"] },
    ],
    common_methods: ["Masked-marginal scoring", "Spearman on DMS assays", "MSA depth", "Fine-tuning on stability"],
    common_datasets: ["ProteinGym", "Mega-scale stability", "UniRef50", "ClinVar"],
    open_problems: [
      "Is zero-shot accuracy caused by evolutionary depth in training?",
      "Do models fail on proteins with few relatives (orphans, designs)?",
      "Can structure fill the gap where evolution is silent?",
    ],
  },
  gaps: [
    {
      id: "g1",
      title: "Are protein language models only as good as a protein's evolutionary family?",
      question: GAP_QUESTION,
      gap_type: "causal_gap",
      why_open: "Overlap studies are correlational; none removes families from pre-training or tests a fix for low-depth proteins.",
      hypothesis: "Accuracy rises ~0.07 ρ per decade of homologs; removing homologs collapses accuracy; structure recovers it.",
      approach: "Score 2.4M variants; regress on homolog depth; counterfactual pre-training; depth-gated hybrid.",
      data_needed: "ProteinGym, mega-scale stability, UniRef50, model weights",
      compute_needed: "Runs on OpenScientist Cloud",
      risks: ["Depth correlates with protein size", "Small counterfactual model"],
      supporting_paper_ids: ["p08", "p18", "p03"],
      novelty_queries: ["protein language model homolog depth causal", "ESM pretraining family removal", "orphan protein mutation prediction"],
      scores: {
        novelty: score(5, "No causal test of homolog depth exists."),
        feasibility: score(4, "All data and weights are public; a 35M model trains in hours."),
        impact: score(5, "Clinical variant tools rely on these models."),
        testability: score(5, "Clear slope, a counterfactual and a held-out fix."),
      },
      novelty_check: {
        status: "novel",
        explanation: "Closest work reports correlations with overlap; none intervenes on training data or targets orphans.",
        closest: [
          { title: "Protein language models are biased by unequal sequence sampling across the tree of life", year: 2024, url: null, in_review: true, overlap: "Shows likelihoods track how well a species is sampled — but no intervention on training data and no fix." },
          { title: "Protein language models learn evolutionary statistics of interacting sequence motifs", year: 2024, url: null, in_review: true, overlap: "Explains what is learned, not when it fails." },
        ],
      },
      overall: 4.75,
    },
    minorGap("g2", "Epistasis in double mutants from zero-shot likelihoods", "evaluation_gap", [4, 3, 4, 4], "partially_addressed", "A few assays report double mutants."),
    minorGap("g3", "Calibration of variant scores for clinical thresholds", "methodological", [3, 4, 4, 3], "partially_addressed", "AlphaMissense provides calibrated scores."),
    minorGap("g4", "Mutation effects in de novo designed proteins", "generalisation", [4, 3, 3, 3], "unchecked", "Few published scans of designed proteins."),
    minorGap("g5", "Language-model scores for insertions and deletions", "new_question", [4, 2, 3, 3], "unchecked", "Indel assays remain scarce."),
  ],
  plan: PLAN,
  planAudit: {
    revised: true,
    first: {
      field: "Computational biology",
      established_theory: ["Co-evolution predicts contacts", "DMS assays vary widely in noise"],
      contribution: "",
      problems: [
        { severity: "FATAL", kind: "confounding", problem: "Homolog depth was compared across assays without controlling for protein length and assay type, which both correlate with depth.", fix: "Partial correlations plus length- and assay-matched subsets." },
        { severity: "MAJOR", kind: "wrong_reference", problem: "Homologs were counted in UniRef50 2023, not the 2021_03 release ESM-2 was trained on.", fix: "Use the exact training release." },
      ],
    },
    final: {
      field: "Computational biology",
      established_theory: ["Co-evolution predicts contacts", "DMS assays vary widely in noise"],
      contribution: "The first causal test of whether protein language models depend on evolutionary depth — with a fix for orphan proteins.",
      problems: [],
    },
  },
  planLog: [
    "Drafting hypotheses, data, methods and metrics",
    "Expert audit: checking confounders of homolog depth",
    "FATAL: depth confounded with protein length and assay type",
    "MAJOR: homologs counted in the wrong UniRef release",
    "Revising: matched subsets, UniRef50 2021_03",
    "Validating task graph: 12 tasks, 5 phases, no cycles",
  ],
  master: MASTER,
  bpLog: ["Locating ProteinGym, mega-scale stability, UniRef50 and weights", "Verified 4/4 data sources", "Compiling 6 agents · 12 tasks", "Validating data flow, tools and budget"],
  taskCost: { T1: 0.94, T2: 0.71, T3: 3.2, T4: 21.8, T5: 2.1, T6: 1.48, T7: 1.12, T8: 24.3, T9: 2.6, T10: 1.9, T11: 1.31, T12: 0.82 },
  toolScript: {
    T1: [
      { tool: "mcp:proteingym", args: "list_assays → 217 substitution assays · 2,428,519 variants" },
      { tool: "http_request", args: "zenodo 7992926 → Tsuboyama_dataset.csv (776,298 rows)" },
      { tool: "run_python", args: "mapped 696/696 proteins to UniProt · 41 structures predicted" },
    ],
    T2: [
      { tool: "run_shell", args: "cloud workers allocated · accelerated · ready" },
      { tool: "mcp", args: "registered proteingym · uniref-search · plm-scorer ✓" },
    ],
    T3: [
      { tool: "mcp:uniref-search", args: "mmseqs search 696 queries vs UniRef50 2021_03 (49.9M seqs)" },
      { tool: "skill+", args: "learned depth_by_identity (dedups hits ≥ 90% identical)" },
      { tool: "run_python", args: "homologs: median 1,840 · 63 proteins < 100 · 9 orphans < 10" },
    ],
    T4: [
      { tool: "spawn_subagents", args: "4 sub-agents: esm2-650m · esm2-3b · esm1v · saprot" },
      { tool: "mcp:plm-scorer", args: "masked-marginal 2.4M variants", sub: "esm2-3b" },
      { tool: "error", args: "out of memory on 1,920-residue protein (worker memory limit)", sub: "esm2-3b" },
      { tool: "skill+", args: "wrote windowed_scoring: 1,022-token windows, 256 overlap, averaged" },
      { tool: "mcp:plm-scorer", args: "9.7M scores written", sub: "saprot" },
    ],
    T5: [{ tool: "run_python", args: "ThermoMPNN ΔΔG for 776k stability variants ✓" }],
    T6: [
      { tool: "run_python", args: "rho_per_assay ~ log10(homologs) + log(length) + assay_type" },
      { tool: "verifier", args: "✕ 14 assays score the reversed sign (higher = less fit)" },
      { tool: "skill+", args: "wrote align_assay_direction from ProteinGym metadata · retry on OS-Reasoner" },
      { tool: "run_python", args: "slope +0.071 ρ/decade (ESM-2 3B) · +0.064 ESM-1v · +0.038 SaProt" },
    ],
    T7: [{ tool: "run_python", args: "attention contact P@L: 0.61 (deep) vs 0.18 (< 100 homologs)" }],
    T8: [
      { tool: "run_job", args: "pretrain esm2_35m --exclude 40 families --steps 150k", sub: "counterfactual" },
      { tool: "run_job", args: "pretrain esm2_35m --exclude 40 matched random --steps 150k", sub: "control" },
      { tool: "check_process", args: "step 132k / 150k · loss 2.214", sub: "counterfactual" },
      { tool: "post_note", args: "held-out families: ρ 0.44 → 0.19 · controls 0.43 → 0.41" },
    ],
    T9: [
      { tool: "run_python", args: "w(depth) = σ(a·log10 h + b) · fit by protein-level CV" },
      { tool: "skill", args: "reused windowed_scoring for long proteins" },
    ],
    T10: [{ tool: "run_python", args: "low-depth ρ 0.21 → 0.39 (+86%) · all proteins 0.452 → 0.488" }],
    T11: [
      { tool: "skill+", args: "wrote bootstrap_by_protein (10,000 resamples)" },
      { tool: "run_python", args: "slope 95% CI [0.052, 0.090] · p < 0.001 · drop −57% vs −5%" },
    ],
    T12: [{ tool: "run_python", args: "fig1_depth · fig2_counterfactual · fig3_hybrid · fig4_contacts" }],
  },
  budget: 100,
  report: {
    scaffold: {
      title: "Remembering Evolution: Protein Language Models Fail Where Homologs Are Scarce",
      one_sentence_summary:
        "Across 217 assays and 776k stability measurements, protein language model accuracy rises with a protein's number of training-set relatives; removing those relatives halves accuracy, and a depth-gated hybrid with a structure model recovers most of the loss on orphan proteins.",
      hypothesis_verdict: "supported",
      verdict_explanation:
        "ESM-2 3B's Spearman rises 0.071 per decade of homologs (95% CI 0.052–0.090, p < 0.001) after controlling length and assay type. Removing 40 families from pre-training cut their accuracy by 57% versus 5% for matched controls.",
      findings: [
        { claim: "Mean zero-shot ρ is 0.47 for proteins with > 1,000 homologs but 0.21 for those with < 100.", evidence: ["T6", "table1.csv"], strength: "strong", relation: "motivates" },
        { claim: "Accuracy rises 0.071 ρ per decade of homologs for ESM-2 3B and 0.064 for ESM-1v; structure-aware SaProt is less dependent (0.038).", evidence: ["T6", "T11", "fig1_depth.pdf"], strength: "strong", relation: "supports H₁" },
        { claim: "Counterfactual: removing 40 families from pre-training drops their ρ from 0.44 to 0.19, while matched controls change from 0.43 to 0.41.", evidence: ["T8", "fig2_counterfactual.pdf"], strength: "strong", relation: "causal" },
        { claim: "Attention-derived contacts collapse with depth (P@L 0.61 → 0.18), consistent with models storing co-evolution rather than physics.", evidence: ["T7", "fig4_contacts.pdf"], strength: "moderate", relation: "mechanism" },
        { claim: "A depth-gated hybrid with ThermoMPNN raises low-depth ρ from 0.21 to 0.39 (+86%) and overall ρ from 0.452 to 0.488.", evidence: ["T9", "T10"], strength: "strong", relation: "fix" },
      ],
      success_criteria: [
        { criterion: "Depth slope > 0.05 with p < 0.01", status: "met", evidence: "0.071, p < 0.001" },
        { criterion: "Hybrid recovers ≥ 50% of the low-depth gap", status: "met", evidence: "69% recovered" },
      ],
      figures: [],
      limitations: ["Counterfactual uses a 35M model", "Only single substitutions", "63 low-depth proteins"],
      deviations: ["Aligned assay sign conventions after the verifier caught 14 reversed assays"],
    },
    agent: { status: "done", summary: "", cost: 2.06, issues: [] },
    files: { tex: true, pdf: true, bib: true },
    citations: { used: Array.from({ length: 47 }, (_, i) => `ref${i}`), unknown: [], available: 104 },
    audit: [],
  },
  iterations: [
    { n: 1, session: 1, review_run_id: "r1", verdict: "major_revision", judged: true, decision: "repair", reason: "", score: 5.8, score_rationale: "Strong question, but the hybrid's weights were tuned on proteins that also appear in its test folds, and Table 2 disagrees with results.csv for ESM-1v.", blocking: { FATAL: 0, MAJOR: 2 }, open_concerns: 1, issues: [], cost_usd: 1.2, level: "execution", rerun_tasks: ["T9", "T10"], carried_over: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T11", "T12"] },
    { n: 2, session: 1, review_run_id: "r2", verdict: "minor_revision", judged: true, decision: "improve", reason: "", score: 8.4, score_rationale: "Causal design is convincing. Discuss scale: does the 3B model's dependence shrink?", blocking: { FATAL: 0, MAJOR: 0 }, open_concerns: 1, issues: [], cost_usd: 1.1, level: "report" },
    { n: 3, session: 1, review_run_id: "r3", verdict: "accept", judged: true, decision: "approved", reason: "", score: 9.3, score_rationale: "Claims match the evidence, the counterfactual is clean, and limitations are explicit.", blocking: { FATAL: 0, MAJOR: 0 }, open_concerns: 0, issues: [], cost_usd: 0.9, level: "report" },
  ],
  round1Issues: [
    { id: "i1", track_id: "k1", severity: "MAJOR", category: "leakage", title: "Hybrid weights were fit on proteins that reappear in test folds; refit with protein-level folds only.", blocking: true, open_concern: false, verification: "verified", grounding: "splits/hybrid_cv.json", tracking: { status: "new", previous_ids: [] }, referee: "methods" },
    { id: "i2", track_id: "k2", severity: "MAJOR", category: "table_mismatch", title: "Table 2 reports ESM-1v slope 0.068; results.csv says 0.064.", blocking: true, open_concern: false, verification: "verified", grounding: "table2.tex", tracking: { status: "new", previous_ids: [] }, referee: "lead" },
    { id: "i3", track_id: "k3", severity: "MINOR", category: "context", title: "Discuss whether larger models depend less on depth.", blocking: false, open_concern: true, verification: "verified", grounding: "paper.tex §6", tracking: { status: "new", previous_ids: [] }, referee: "theory" },
  ],
  reviewLog: {
    round1: ["Reviewer panel assembled: lead, methods, theory", "Recomputed Table 2 from results/results.csv", "ESM-1v slope: table 0.068, data 0.064 — mismatch"],
    repair: ["Round 1 · score 5.8 · 2 major issues", "Re-running T9, T10 with protein-level folds; reusing 10 finished tasks", "Hybrid holds: low-depth ρ 0.39 with clean folds. Rewriting §5 and Table 2"],
    round2: ["Round 2 · score 8.4 · adding scaling discussion"],
    round3: ["Round 3 · score 9.3 · accept"],
  },
  spend: { literature: 1.04, gaps: 3.1, plan: 4.9, blueprint: 6.8, execution: 69.1, report: 71.2, review: 74.4 },
  paper: {
    title: "Remembering Evolution: Protein Language Models Fail Where Homologs Are Scarce",
    authors: "Anonymous Author(s)",
    affiliation: "Affiliation · Address",
    abstract:
      "Protein language models (PLMs) predict the effects of mutations without labelled data and are increasingly used to interpret disease variants and guide design. We ask whether this ability reflects learned biophysics or memorised evolution. Scoring 2.4M variants from 217 deep mutational scans and 776k stability measurements with ESM-2, ESM-1v and SaProt, we find that zero-shot accuracy rises by 0.071 Spearman per decade of training-set homologs (95% CI [0.052, 0.090]) after controlling for length and assay type. Re-training a model with 40 families removed cuts their accuracy by 57%, versus 5% for matched controls, establishing homolog depth as causal. A depth-gated hybrid with a structure-based stability model raises accuracy on low-depth proteins by 86%.",
    sections: [
      {
        heading: "Introduction",
        paragraphs: [
          "Masked protein language models trained on hundreds of millions of sequences [1, 2] assign higher likelihood to amino acids that are compatible with a protein's fold and function. The log-likelihood ratio between mutant and wild type is a strong zero-shot predictor of mutation effects [1], competitive with alignment-based generative models [5, 13] on ProteinGym [3].",
          "Yet PLM training data is dominated by large, well-studied families. Recent analyses show that PLMs largely learn co-evolutionary statistics [8] and that their likelihoods are biased by how well each lineage is sampled in training [18]. Whether this dependence is *causal*, and what to do for proteins with few relatives — orphan proteins, fast-evolving viral proteins and de novo designs — remains open.",
          "We make three contributions: (i) a controlled analysis of zero-shot accuracy against homolog depth across four models and two data types; (ii) a counterfactual pre-training experiment that removes families from training; and (iii) a depth-gated hybrid that recovers most of the lost accuracy from structure.",
        ],
      },
      {
        heading: "Related Work",
        paragraphs: [
          "**Protein language models.** ESM-1b and ESM-1v [12, 1] showed that masked language modelling on UniRef yields zero-shot variant effect predictors; ESM-2 [2] scaled this to 15B parameters. Structure-aware vocabularies (SaProt) [9] and retrieval (Tranception) [6] improve accuracy, and AlphaMissense [7] fine-tunes on population data for clinical use.",
          "**What PLMs learn.** Zhang et al. [8] showed that PLMs store pairwise co-evolutionary motifs, and Ding & Steinhardt [18] showed that likelihoods are biased by uneven sampling across the tree of life. Neither intervened on training data. Alignment-based models such as EVE [5] depend on MSA depth by construction; we test whether PLMs inherit this dependence implicitly.",
          "**Stability prediction.** The mega-scale dataset of Tsuboyama et al. [4] enabled supervised stability models such as ThermoMPNN [10], built on ProteinMPNN [11], which use structure rather than evolution.",
        ],
      },
      {
        heading: "Methods",
        paragraphs: [
          "**Data.** We use all 217 ProteinGym substitution assays (2.43M variants) [3] and the mega-scale stability dataset (776k ΔG values, 479 domains) [4]. Homolog depth *h* is the number of UniRef50 2021_03 clusters [16] with a hit at E < 10⁻⁵ and ≥ 30% identity using MMseqs2 [17] — the release ESM-2 was trained on.",
          "**Scoring.** Each substitution receives the masked-marginal score log p(x_mut) − log p(x_wt) at its position [1]. Proteins longer than the context are scored in overlapping 1,022-token windows.",
          "**Counterfactual pre-training.** We re-train ESM-2 35M for 150k steps on UniRef50 with all clusters homologous to 40 target families removed, and a control run with 40 depth-matched random families removed. Both share data order, seed and hyperparameters.",
          "**Depth-gated hybrid.** The hybrid score is w(h)·z_PLM + (1 − w(h))·z_struct with w(h) = σ(a log₁₀ h + b), fit by protein-level cross-validation.",
        ],
        table: {
          caption: "Table 1: Data used in this study.",
          head: ["Dataset", "Proteins", "Variants", "Measure"],
          rows: [["ProteinGym v1.3", "217", "2,428,519", "Fitness (DMS)"], ["Mega-scale", "479", "776,298", "ΔG folding"], ["UniRef50 2021_03", "—", "49.9M seqs", "Homolog depth"]],
        },
      },
      {
        heading: "Accuracy Tracks Evolutionary Depth",
        paragraphs: [
          "Zero-shot Spearman correlation rises steadily with homolog depth for every model (Figure 1). For ESM-2 3B, mean ρ is **0.47** for proteins with more than 1,000 homologs and **0.21** for those with fewer than 100. Controlling for length and assay type, the slope is **0.071 per decade** (95% CI [0.052, 0.090], p < 0.001).",
          "The dependence is weaker but present for the structure-aware SaProt (0.038), and similar on stability data, where evolution is less informative about function and more about folding.",
        ],
        figure: { caption: "Figure 1: (left) Per-assay Spearman ρ against log₁₀ homologs for ESM-2 3B; dashed line: fit. (right) Mean ρ by depth bin for four models.", kind: "scatter" },
        table: {
          caption: "Table 2: Zero-shot Spearman ρ by homolog depth (mean over assays).",
          head: ["Model", "< 100", "100–1k", "> 1k", "Slope / decade"],
          rows: [
            ["PSSM", "0.12", "0.29", "0.38", "0.091"],
            ["EVE", "0.19", "0.39", "0.47", "0.082"],
            ["ESM-1v", "0.20", "0.38", "0.46", "0.064"],
            ["ESM-2 3B", "0.21", "0.40", "0.47", "0.071"],
            ["SaProt", "0.30", "0.42", "0.48", "**0.038**"],
            ["Hybrid (ours)", "**0.39**", "**0.45**", "**0.49**", "0.029"],
          ],
        },
      },
      {
        heading: "Removing Relatives Causes Failure",
        paragraphs: [
          "When 40 families are removed from pre-training, the re-trained model's accuracy on them falls from ρ = 0.44 to **0.19** (−57%), while matched control families removed at random fall only from 0.43 to 0.41 (−5%). The difference is significant (bootstrap p < 0.001).",
          "Attention-derived contact maps degrade in parallel: precision at L falls from 0.61 to 0.18, consistent with the model having stored co-evolutionary couplings for these families rather than inferring structure.",
        ],
        figure: { caption: "Figure 2: (left) Accuracy before and after removing families from pre-training, against matched controls. (right) Contact precision against depth.", kind: "bars" },
      },
      {
        heading: "A Depth-Gated Hybrid",
        paragraphs: [
          "Because structure-based stability predictors do not rely on evolution, they complement PLMs where homologs are scarce. Our depth-gated hybrid learns to trust the PLM for deep families and structure for shallow ones. On held-out proteins it raises low-depth ρ from 0.21 to **0.39** (+86%) and overall ρ from 0.452 to **0.488**, recovering 69% of the depth gap.",
        ],
        figure: { caption: "Figure 3: (left) Learned weight on the language model against depth. (right) Accuracy of PLM, structure and hybrid by depth.", kind: "lines" },
      },
      {
        heading: "Discussion",
        paragraphs: [
          "Our results suggest that much of what PLMs know about mutation effects is retrieved evolution. This matters most where predictions are most needed: rare-disease genes with few relatives, fast-evolving pathogen proteins and designed proteins. Practitioners should report homolog depth alongside PLM scores, and prefer structure-informed models when depth is low.",
          "**Limitations.** The counterfactual uses a 35M-parameter model; larger models may depend less on depth. We study single substitutions only. Low-depth proteins are few (63), and their assays are noisier on average.",
        ],
      },
      {
        heading: "Conclusion",
        paragraphs: [
          "Protein language models fail where evolution is silent, and the failure is caused by missing relatives in training. Combining them with structure in a depth-aware way closes most of the gap. All code, scores and checkpoints are released.",
        ],
      },
    ],
    references: [
      "J. Meier, R. Rao, R. Verkuil et al. Language models enable zero-shot prediction of the effects of mutations on protein function. *NeurIPS*, 2021.",
      "Z. Lin, H. Akin, R. Rao et al. Evolutionary-scale prediction of atomic-level protein structure with a language model. *Science*, 2023.",
      "P. Notin, A. Kollasch, D. Ritter et al. ProteinGym: Large-scale benchmarks for protein fitness prediction and design. *NeurIPS*, 2023.",
      "K. Tsuboyama, J. Dauparas, J. Chen et al. Mega-scale experimental analysis of protein folding stability in biology and design. *Nature*, 2023.",
      "J. Frazer, P. Notin, M. Dias et al. Disease variant prediction with deep generative models of evolutionary data. *Nature*, 2021.",
      "P. Notin, M. Dias, J. Frazer et al. Tranception: protein fitness prediction with autoregressive transformers and inference-time retrieval. *ICML*, 2022.",
      "J. Cheng, G. Novati, J. Pan et al. Accurate proteome-wide missense variant effect prediction with AlphaMissense. *Science*, 2023.",
      "Z. Zhang, H. Wayment-Steele, G. Brixi et al. Protein language models learn evolutionary statistics of interacting sequence motifs. *PNAS*, 2024.",
      "J. Su, C. Han, Y. Zhou et al. SaProt: Protein language modeling with structure-aware vocabulary. *ICLR*, 2024.",
      "H. Dieckhaus, M. Brocidiacono, N. Randolph et al. Transfer learning to leverage larger datasets for improved prediction of protein stability changes. *PNAS*, 2024.",
      "J. Dauparas, I. Anishchenko, N. Bennett et al. Robust deep learning–based protein sequence design using ProteinMPNN. *Science*, 2022.",
      "A. Rives, J. Meier, T. Sercu et al. Biological structure and function emerge from scaling unsupervised learning to 250 million protein sequences. *PNAS*, 2021.",
      "A. Riesselman, J. Ingraham, D. Marks. Deep generative models of genetic variation capture the effects of mutations. *Nat. Methods*, 2018.",
      "C. Hsu, H. Nisonoff, C. Fannjiang et al. Learning protein fitness models from evolutionary and assay-labeled data. *Nat. Biotechnol.*, 2022.",
      "L. He, S. Zhang, L. Mao et al. Pre-training co-evolutionary protein representations via a pairwise masked language model. *arXiv*, 2021.",
      "B. Suzek, Y. Wang, H. Huang et al. UniRef clusters: a comprehensive and scalable alternative for improving sequence similarity searches. *Bioinformatics*, 2015.",
      "M. Steinegger, J. Söding. MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets. *Nat. Biotechnol.*, 2017.",
      "F. Ding, J. Steinhardt. Protein language models are biased by unequal sequence sampling across the tree of life. *bioRxiv*, 2024.",
    ],
  },
};
