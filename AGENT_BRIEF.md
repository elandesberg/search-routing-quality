# Handoff brief — specialize the search-quality framing doc

Paste this to the work agent, replacing `<URL>` with the published link.

---

## Task

Read the problem-framing document at `<URL>`. It is a deliberately generic version of an argument about how to define quality for an AI-enhanced ecommerce search product, and why routing exploration should start now even as experience improvements proceed in parallel. Your job is to turn it into the internal version: same argument, same structure, but grounded in our actual system, metrics, and numbers.

The output is a **document for human readers** — product managers, engineers, data scientists, and leadership. It is not a spec, not a ticket, and not a plan for you to execute. Write it to be read and argued with.

## What to change

Every `FILL` marker in the source is a slot you should replace with real specifics. Work through all of them. In addition, add concrete detail wherever the generic version gestures at something we actually know:

- **System description.** Replace the abstract "two paths" opening with how our routing actually works: how the allowlist is built and maintained, who owns it, how often it changes, roughly how many queries or what share of traffic it covers.
- **Cost and latency.** Give the real incremental cost per enhanced query and the real added latency, at whatever precision is appropriate for the audience. The argument that latency belongs *inside* the effect rather than beside it as a budget line is much stronger with a number attached.
- **Metrics.** Replace the metric-tier table's placeholders with our actual metric definitions and instrumentation names, so a reader knows exactly which dashboard each row refers to. If we already have a north-star metric, say so and use its real name throughout rather than the generic phrasing.
- **What we currently observe.** The doc claims the naive allowlist-versus-everything-else comparison is misleading. If we have actually run that comparison, say what it showed and then explain why it should not be trusted. A concrete misleading number is far more persuasive than a hypothetical one.
- **The concrete example in Part Three.** The generic version uses an invented pair of contrasting queries. Replace it with two real queries from our traffic — one on the allowlist, one off it — that differ sharply in shopper intent. Use real observed rates if you can.
- **Proposed exploration design.** Fill in the actual numbers being proposed: size of the uncertainty set, routing probability, expected exploration cost, expected time to sufficient data, guardrail thresholds and their halt conditions.
- **Query features.** Replace the generic feature list with the features actually available in our stack for representing a query.
- **Autoraters.** If we already run autoraters, name them and say what each measures. The calibration argument should reference our real ones rather than the abstract category.
- **Retailer-level considerations.** Fill in how routing policy relates to per-retailer configuration, and whether the proposal is global, per-retailer, or pooled.
- **Ownership and sequencing.** Add whatever the doc needs to be actionable: who owns which piece, rough sequencing, what decision is being asked of the reader and by when.

## What to preserve

The argument is the deliverable. Do not restructure it, soften it, or turn it into a neutral survey of options. Specifically, keep intact:

1. **The central claim that quality is a comparison, not a property.** Including the three-baseline table and the point that the retailer's incumbent search is often the weakest baseline, so a flat internal result does not imply a flat commercial one.
2. **The two-level definition of quality** — per-query incremental effect, and product-level captured value — and the reason the split matters: it separates "the experience is weak here" from "we should never have routed this."
3. **The three-way diagnosis in Part Three, and the distinction between the three.** Composition and selection are biases that adjustment can partly address. Zero overlap is *not* a bias — it is missing data by construction, and no statistical method fixes it. This distinction is the load-bearing part of the whole document. Do not flatten the three into a general "our data has problems."
4. **The point that CTR is a diagnostic, not a north star,** because a summary that answers the question suppresses clicks while serving the shopper better.
5. **The two-way interaction between the axes**, and the careful shape of the priority claim: the axes proceed in parallel and do not compete for the same slot, but exploration cannot be deferred, because it is what makes experience improvements measurable beyond the allowlist. Do not sharpen this back into "routing before experience" — the document deliberately does not claim that.
6. **The framing of exploration as buying information** with a bounded, known, pre-set cost, against a status quo whose cost is unbounded and unmeasured.
7. **The point that we are learning what *kinds* of queries to route, not which specific queries** — this is what makes the tail tractable.
8. **The autorater hierarchy**: randomized outcomes are the anchor, autoraters are the extrapolation, and the correlation between them must be measured rather than assumed.
9. **"Doing nothing is not neutral"** as the last row of the risk table. The status quo is itself an untested routing policy.
10. **The notation, exactly as defined and no heavier**: outcomes Y(1)/Y(0), the per-query effect τ(x), the routing probability e(x), the policy π and its value V(π). That is the full set — the document deliberately stops there. Keep the symbols consistent everywhere; if you fill in a real outcome metric, it becomes the concrete definition of Y and should be stated as such in the Setup block.
11. **The instruction to log e(x) at serve time.** It is an implementation detail with outsized value (it enables off-policy evaluation of candidate policies from one experiment's logs) and is easy to lose in editing.

## What not to do

- Do not remove the "open design questions" section or resolve its questions by fiat. They are open on purpose, and the randomization-unit question in particular should stay framed as a decision the team needs to make explicitly.
- Do not expand the notation beyond what the document already carries. The register is deliberately light-formal: enough notation to make the estimands unambiguous (τ, π, e, V, the decomposition), everything else in prose. No derivations, no estimator algebra, no additional symbols. The document should remain readable start-to-finish by a technical PM.
- Do not soften the claim that the current data cannot answer the routing question. It is the reason the document exists.
- Do not turn the risk table into reassurance. Each risk should be stated honestly, including the one about optimizing to short-horizon metrics, which is genuinely only partly mitigated.
- Do not remove or replace the schematic figure. If you can ground it in real data, do — but a real version must keep the same two points: the boundary location is unknown, and a restrictive heuristic can err in both directions at once.
- Do not add filler sections (background, glossary, appendices) unless they carry real information.

## The simulation section (Part Seven) and the concrete design (Part Six)

- Part Seven is a **synthetic** demonstration and must stay labeled that way. Its numbers are invented; its shapes are the argument. Do not swap in real numbers by hand — the only legitimate way to update its figures is to rerun the simulation with production-calibrated parameters, per the separate replication packet (`production-replication-packet.md` + `routing_sim.py`). Until that has been done, keep the toy-world figures and their "simulation" labels exactly as they are, and fill the FILL slot with a link to wherever the sim code is hosted internally.
- Preserve the equal-budget broad-vs-narrow comparison and its takeaway (breadth beats intensity; the narrow design converges to its own ceiling), the support rule (learned policies act only where their design explored), and the allowlist-holdback point (learning to prune requires e < 1 on the allowlist). These are the load-bearing design conclusions.
- The "experiment, concretely" list in Part Six is a proposal, not a settled decision — keep its tone as a recommendation, and keep Part Nine's remaining open questions genuinely open.
- Part Eight (the batch version) is the near-term path and its figures are also synthetic (`batch_allowlist_sim.py` in the same packet; `allowlist_model_pymc.py` is the estimator to actually run on real logs — run its `--demo` cross-check against the Gibbs sampler in `hier_bayes_allowlist.py` first, since the PyMC version could not be executed in the environment that authored it). Preserve: the shadow allowlist flag in control as the one strict prerequisite; the partial-pooling estimator and its one-line equation; pruning by posterior probability rather than raw or significance-gated estimates; the probation tier for removals (removals are the non-self-validating direction); random/near-support additions; the first-exposure caveat. If production has an A/B running today, this section is the first thing the team can act on — do not bury it.

## Format

Return a single self-contained HTML file, preserving the source document's styling, structure, section numbering, light/dark mode support, and figure. Remove all `FILL` markers and their styling once filled — no placeholder should survive into the final version. Flag anything you could not fill in a short list at the end of your response, outside the document itself, rather than leaving a gap in the text.
