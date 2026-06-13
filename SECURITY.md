# Security Policy

<!-- markdownlint-disable MD013 -->

## Supported Versions

AgentGuard is an early-stage project. Security fixes are generally applied to the `main` branch and included in future releases.

At this stage, we recommend using the latest version from the default branch or the most recent tagged release, if available.

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues, discussions, or pull requests.

Instead, use GitHub’s private vulnerability reporting feature in this repository’s Security tab:

<https://github.com/glaborie/agentguard/security>

This is the preferred channel for reporting vulnerabilities in AgentGuard.

When submitting a report, please include as much of the following as possible:

- a clear description of the vulnerability
- the affected component, service, or file(s)
- steps to reproduce
- proof of concept, if available
- impact assessment
- any suggested remediation

## Response Process

We will aim to:

- acknowledge receipt of a vulnerability report within a reasonable time
- investigate and validate the report
- assess severity and impact
- prepare and release a fix when appropriate
- coordinate disclosure responsibly

Response times may vary depending on project availability and issue complexity.

## Scope

This policy applies to security issues in the AgentGuard codebase and maintained deployment/configuration assets.

Examples may include:

- authentication or authorization weaknesses
- remote code execution risks
- prompt injection protection bypasses
- sensitive data exposure
- secrets handling issues
- dependency-related vulnerabilities with practical impact
- insecure default configurations
- tenant or data isolation weaknesses, if introduced in the future

## Out of Scope

The following are generally out of scope unless they lead to a concrete, practical security impact in this repository:

- theoretical issues without a demonstrable exploit path
- best-practice suggestions without a specific vulnerability
- vulnerabilities only present in third-party services, unless caused by this project’s configuration or integration choices
- denial of service requiring unrealistic resources or privileged access in a local-only setup

## Disclosure Expectations

Please allow time for investigation and remediation before public disclosure.

We ask reporters to avoid public disclosure until:

- the issue has been confirmed
- a fix or mitigation is available, when feasible
- affected users have had a reasonable opportunity to update

## Security Best Practices for Users

If you deploy AgentGuard, we recommend that you:

- keep dependencies and container images up to date
- avoid committing secrets into the repository
- rotate exposed credentials immediately
- review default passwords and change them before non-local deployments
- restrict network exposure of internal services
- use HTTPS and proper access controls in any shared or production environment
- treat prompts, traces, datasets, and model outputs as potentially sensitive data
- review third-party model, telemetry, and storage integrations for compliance requirements

## Safe Deployment Note

AgentGuard handles observability data, traces, prompts, retrieval context, and model outputs. Depending on deployment and usage, these may contain sensitive or business-critical information.

Operators are responsible for:

- choosing an appropriate deployment environment
- controlling access to dashboards, APIs, and storage systems
- configuring retention, logging, and data handling in line with their security and compliance requirements
