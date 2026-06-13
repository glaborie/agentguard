# Roadmap

<!-- markdownlint-disable MD013 -->

AgentGuard is building a self-hosted AI reliability platform for RAG and agentic applications.

The goal is to help teams detect, evaluate, and prevent costly AI incidents before they become customer-visible.

This roadmap reflects current priorities and product direction. It is not a guaranteed delivery schedule.

## Current focus

AgentGuard currently focuses on:

- self-hosted deployment for teams that want control over infrastructure, data, and observability
- observability across traces, retrieval, tool use, latency, and model behavior
- business protection and safety controls such as prompt injection blocking and PII masking
- golden dataset evaluation and regression detection for prompts, models, retrieval, and tools
- support for both RAG and agentic workflows

## Next

### 1. Stronger protection

We are expanding AgentGuard’s protection layer beyond regex-based controls to better handle realistic failure modes in production AI systems.

Priorities include:

- **semantic prompt injection detection**
  - add a second-pass ML or model-based classifier to catch paraphrased jailbreaks and instruction-bypass attempts
  - preserve the current regex layer as a fast first-pass filter

- **toxic and harmful content detection**
  - add screening for abusive or harmful requests and outputs
  - improve coverage of safety risks not addressed by injection blocking or PII masking alone

### 2. Safer release workflows

We want AgentGuard to make release confidence operational, not just conceptual.

Priorities include:

- **CI/CD regression gate integration**
  - ship a GitHub Actions workflow for regression testing on pull requests and mainline changes
  - reduce setup burden for teams adopting AgentGuard

- **coverage and quality visibility**
  - add coverage reporting and badges
  - make test completeness easier to understand for maintainers and adopters

- **stronger type safety**
  - improve annotation coverage in high-change and evaluation-related areas
  - create a clearer baseline for maintainability and refactoring safety

### 3. Better deployment and contributor onboarding

We want AgentGuard to be easier to deploy, evaluate, and contribute to.

Priorities include:

- **Google Cloud deployment guidance**
  - document a practical first deployment path for production-like environments
  - clarify stateful dependencies and operational tradeoffs

- **stronger contributor onboarding**
  - improve local development setup and contribution guidance
  - make it easier for new contributors to run tests, start the stack, and submit changes

## Later

Areas we expect to explore over time:

- broader cloud deployment options
- richer policy authoring and governance workflows
- stronger operational UX for incident investigation
- more advanced evaluation, benchmarking, and regression reporting
- multi-team or enterprise operating patterns

## Not currently focused on

To stay aligned with the product direction, AgentGuard is not currently optimized for:

- generic consumer chatbot experiences
- no-code website widget builders
- lightweight demo-only assistant frameworks
- fully managed SaaS operation in the current version

## How to contribute

Contributions are especially welcome in areas that improve:

- reliability and safety guardrails
- evaluation and regression workflows
- observability and operational clarity
- deployment, documentation, and developer experience
