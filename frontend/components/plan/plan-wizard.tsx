"use client";

import { Check, ChevronDown, Sparkles, Square } from "lucide-react";
import * as React from "react";

import { DocumentSelector } from "@/components/chat/document-selector";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  DocumentRecord,
  PlanCatalogSection,
  PlanGenerateInput,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface PlanWizardProps {
  catalog: PlanCatalogSection[];
  documents: DocumentRecord[];
  onSubmit: (payload: PlanGenerateInput) => void;
  busy?: boolean;
  configured?: boolean;
  className?: string;
}

interface FormState {
  businessName: string;
  industry: string;
  product: string;
  targetMarket: string;
  problem: string;
  businessModel: string;
  fundingAmount: string;
  notes: string;
  sectionKeys: string[];
  model: string;
  temperature: string;
  maxTokens: string;
}

export function PlanWizard({
  catalog,
  documents,
  onSubmit,
  busy,
  configured = true,
  className,
}: PlanWizardProps) {
  const defaults = React.useMemo(
    () => catalog.filter((section) => section.default).map((section) => section.key),
    [catalog],
  );

  const [form, setForm] = React.useState<FormState>({
    businessName: "",
    industry: "",
    product: "",
    targetMarket: "",
    problem: "",
    businessModel: "",
    fundingAmount: "",
    notes: "",
    sectionKeys: [],
    model: "",
    temperature: "",
    maxTokens: "",
  });
  const [documentIds, setDocumentIds] = React.useState<string[]>([]);
  const [sectionsTouched, setSectionsTouched] = React.useState(false);
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const businessNameRef = React.useRef<HTMLInputElement>(null);

  // Default the selection to the catalogue defaults until the user edits it.
  const selectedSections = sectionsTouched ? form.sectionKeys : defaults;
  const hasCatalog = catalog.length > 0;

  const update = (patch: Partial<FormState>) =>
    setForm((current) => ({ ...current, ...patch }));

  const toggleSection = (key: string) => {
    setSectionsTouched(true);
    const base = selectedSections;
    update({
      sectionKeys: base.includes(key)
        ? base.filter((value) => value !== key)
        : [...base, key],
    });
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const businessName = form.businessName.trim();
    if (!businessName) {
      setError("Enter a business name to generate a plan.");
      businessNameRef.current?.focus();
      businessNameRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    if (hasCatalog && selectedSections.length === 0) {
      setError("Select at least one section to include in the plan.");
      return;
    }
    setError(null);

    const inputs: Record<string, string> = {};
    if (form.product.trim()) inputs.product = form.product.trim();
    if (form.targetMarket.trim()) inputs.target_market = form.targetMarket.trim();
    if (form.problem.trim()) inputs.problem = form.problem.trim();
    if (form.businessModel.trim()) inputs.business_model = form.businessModel.trim();
    if (form.fundingAmount.trim()) inputs.funding_amount = form.fundingAmount.trim();

    const payload: PlanGenerateInput = {
      business_name: businessName,
      industry: form.industry.trim() || undefined,
      notes: form.notes.trim() || undefined,
      inputs,
      document_ids: documentIds.length ? documentIds : undefined,
      sections: selectedSections,
    };
    if (form.model.trim()) payload.model = form.model.trim();
    const temperature = Number.parseFloat(form.temperature);
    if (!Number.isNaN(temperature)) payload.temperature = temperature;
    const maxTokens = Number.parseInt(form.maxTokens, 10);
    if (!Number.isNaN(maxTokens)) payload.max_tokens = maxTokens;

    onSubmit(payload);
  };

  return (
    <form onSubmit={submit} className={cn("space-y-5", className)}>
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="text-base font-semibold tracking-tight">Business details</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The more you provide, the more specific and investor-ready the plan will be.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">
              Business name <span className="text-destructive">*</span>
            </span>
            <Input
              ref={businessNameRef}
              value={form.businessName}
              onChange={(event) => update({ businessName: event.target.value })}
              placeholder="e.g. Northwind Robotics"
              disabled={busy}
              maxLength={200}
              aria-invalid={Boolean(error) && !form.businessName.trim()}
              className={
                error && !form.businessName.trim() ? "border-destructive focus-visible:ring-destructive" : undefined
              }
            />
            {error && !form.businessName.trim() && (
              <span className="block text-xs text-destructive">{error}</span>
            )}
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium">Industry</span>
            <Input
              value={form.industry}
              onChange={(event) => update({ industry: event.target.value })}
              placeholder="e.g. Warehouse automation"
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium">Product or service</span>
            <Input
              value={form.product}
              onChange={(event) => update({ product: event.target.value })}
              placeholder="What you sell"
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium">Target market</span>
            <Input
              value={form.targetMarket}
              onChange={(event) => update({ targetMarket: event.target.value })}
              placeholder="Who you serve"
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium">Business model</span>
            <Input
              value={form.businessModel}
              onChange={(event) => update({ businessModel: event.target.value })}
              placeholder="How you make money"
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5">
            <span className="text-sm font-medium">Funding sought</span>
            <Input
              value={form.fundingAmount}
              onChange={(event) => update({ fundingAmount: event.target.value })}
              placeholder="e.g. $500k seed"
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Problem you solve</span>
            <Textarea
              value={form.problem}
              onChange={(event) => update({ problem: event.target.value })}
              placeholder="Describe the customer pain and why it matters now."
              rows={2}
              disabled={busy}
            />
          </label>

          <label className="space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Additional notes</span>
            <Textarea
              value={form.notes}
              onChange={(event) => update({ notes: event.target.value })}
              placeholder="Anything else the plan should reflect — history, traction, team, assumptions…"
              rows={3}
              disabled={busy}
              maxLength={4000}
            />
          </label>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="text-base font-semibold tracking-tight">Research documents</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Optionally ground the plan in uploaded documents. Facts are cited with page numbers.
        </p>
        <div className="mt-4">
          <DocumentSelector
            documents={documents}
            selected={documentIds}
            onChange={setDocumentIds}
            disabled={busy}
          />
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">Sections</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {hasCatalog
                ? `${selectedSections.length} of ${catalog.length} sections selected.`
                : "Using the standard section set."}
            </p>
          </div>
          {hasCatalog && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => {
                setSectionsTouched(true);
                update({ sectionKeys: defaults });
              }}
            >
              Reset to standard
            </Button>
          )}
        </div>

        {!hasCatalog ? (
          <p className="mt-4 rounded-lg border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
            Section catalogue unavailable — the standard set of sections will be used.
          </p>
        ) : (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {catalog.map((section) => {
            const checked = selectedSections.includes(section.key);
            return (
              <button
                key={section.key}
                type="button"
                onClick={() => toggleSection(section.key)}
                disabled={busy}
                className={cn(
                  "flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors",
                  checked
                    ? "border-primary/40 bg-primary/5"
                    : "border-border hover:bg-secondary",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                    checked ? "border-primary bg-primary text-primary-foreground" : "border-input",
                  )}
                >
                  {checked && <Check className="h-3 w-3" />}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{section.title}</span>
                  <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                    ~{section.target_words} words
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card shadow-sm">
        <button
          type="button"
          onClick={() => setShowAdvanced((value) => !value)}
          className="flex w-full items-center justify-between px-5 py-4 text-left"
        >
          <span className="text-sm font-medium">Advanced (model &amp; sampling)</span>
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", showAdvanced && "rotate-180")}
          />
        </button>
        {showAdvanced && (
          <div className="grid gap-4 border-t border-border p-5 sm:grid-cols-3">
            <label className="space-y-1.5">
              <span className="text-sm font-medium">Model</span>
              <Input
                value={form.model}
                onChange={(event) => update({ model: event.target.value })}
                placeholder="openai/gpt-oss-120b"
                disabled={busy}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium">Temperature</span>
              <Input
                type="number"
                step="0.1"
                min={0}
                max={2}
                value={form.temperature}
                onChange={(event) => update({ temperature: event.target.value })}
                placeholder="0.7"
                disabled={busy}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium">Max tokens per section</span>
              <Input
                type="number"
                min={16}
                max={8000}
                value={form.maxTokens}
                onChange={(event) => update({ maxTokens: event.target.value })}
                placeholder="2048"
                disabled={busy}
              />
            </label>
          </div>
        )}
      </div>

      {error && form.businessName.trim() && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-muted-foreground">
          {error}
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" variant="gradient" size="lg" disabled={busy || !configured}>
          {busy ? <Square className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "Generating…" : "Generate business plan"}
        </Button>
        {!configured && (
          <span className="text-xs text-muted-foreground">
            Configure OPENROUTER_API_KEY to generate plans.
          </span>
        )}
      </div>
    </form>
  );
}
