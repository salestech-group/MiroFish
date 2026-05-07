# Product Overview

MiroFish is a multi-agent **swarm intelligence prediction engine**. Given seed
material (news, policy drafts, financial signals, novel chapters, etc.) and a
natural-language prediction question, it builds a knowledge graph, populates a
parallel "digital sandbox" with thousands of personality-driven AI agents,
runs a social simulation, and returns an analytical report plus an explorable
simulated world.

The user-facing experience is a guided **5-step workflow**: Graph Build →
Environment Setup → Simulation → Report → Interaction. Long-running steps
(LLM ontology extraction, graph build, profile generation, simulation, report)
execute as background tasks the UI polls for progress.

## Core Capabilities

- **Knowledge graph construction** — Files (PDF, text) are parsed, an LLM
  extracts ontology, and Graphiti writes nodes/edges into Neo4j scoped per
  project (`group_id`).
- **Persona-driven agent generation** — Entities pulled from the graph become
  OASIS agent profiles with traits, memory, and behavior priors.
- **Dual-platform social simulation** — CAMEL-OASIS runs Twitter and Reddit
  agents in parallel rounds with a configurable action set.
- **ReACT-loop report agent** — A reasoning agent answers the prediction
  question using graph tools (`SearchResult`, `InsightForge`, `Panorama`,
  `Interview`).
- **Post-simulation interaction** — Users can chat with any simulated agent
  or the report agent to probe results.

## Target Use Cases

- **Macro decision rehearsal** — Stress-test policies, PR strategies, or
  market moves against a synthetic public before committing.
- **Public-opinion / political forecasting** — Project how an event or
  narrative may diffuse across social platforms.
- **Narrative and creative simulation** — Explore alternate endings,
  what-if scenarios, or fiction continuations (e.g. *Dream of the Red
  Chamber* lost-ending demo).
- **Operator-led research** — Internal analysts upload reports and inspect
  the resulting graph + simulation rather than running ad-hoc surveys.

## Value Proposition

MiroFish converts a static document into a **dynamic, interrogable digital
society**. Where traditional forecasting summarizes data, MiroFish lets
decision-makers *watch the future play out* — observing emergent collective
behavior, intervening from a "god view," and reading both an analytical
report and the underlying agent interactions that produced it.

The pipeline is deliberately **provider-agnostic** at the LLM layer (any
OpenAI-SDK-compatible endpoint works) and **self-hosted** at the graph layer
(Neo4j + Graphiti, no third-party graph service required), so the same
system can run from a developer laptop to a managed deployment without
vendor lock-in.

---
_Focus on patterns and purpose, not exhaustive feature lists_
