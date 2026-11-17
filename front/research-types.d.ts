interface ToolTrace {
  id?: string;
  name: string;
  arguments: Record<string, unknown>;
  status: string;
  result_preview?: string;
}
interface MethodMetrics {
  status: string;
  n: number;
  completed: number;
  failed: number;
  correct?: number;
  accuracy?: number;
  agreement?: number;
  metric_label?: string;
  evaluation_kind?: string;
  majority_baseline_accuracy?: number;
  note?: string;
  macro_f1?: number;
  mean_latency_seconds?: number;
  input_tokens?: number;
  output_tokens?: number;
  per_class?: Record<string, { support: number; precision: number; recall: number; f1: number }>;
}
interface ResearchReport {
  sample_count: number;
  anchor_count: number;
  missing_categories: string[];
  anchor_distribution: { category: string; label: string; count: number }[];
  methods: { id: string; name: string; description: string; status: string; result?: MethodMetrics; reported_result?: { status: string; accuracy: number; approximate: boolean; metric_label: string; evaluation_kind: string; source: string; reported_date: string }; target?: { accuracy: number; metric_kind: "design_target"; label: string } }[];
  benchmark: { protocol?: string; comparison_note?: string; time?: string; train_count?: number; test_count?: number; seed?: number; macro_f1_definition?: string; offline_analysis?: {method: string; strength: string; limitation: string}[]; assistant_full_review?: MethodMetrics & { accuracy: number; rows: { gold: string; prediction: string; reason: string; rpid: string }[] } };
  finetune: { base_model: string; status: string; current_approach: string; note: string };
}
interface Window {
  ResearchUI: {
    request(url: string, options?: RequestInit): Promise<unknown>;
    categoryLabel(value: string): string;
    escapeHtml(value: string): string;
    chartsReady(): Promise<void>;
    renderTrace(host: HTMLElement, trace: ToolTrace[]): void;
  };
}
