# Nexus CLI — Complete Architectural & Technical Booklet
**Current State Report (TypeScript/Node.js Architecture)**

---

## Table of Contents
1. Executive Summary & Value Proposition
2. Architectural Design & Philosophy
3. Core Technology Stack
4. System Architecture Diagram
5. Directory & Module Breakdown
6. Deep Dive: Core Orchestrator
7. Deep Dive: Agentic Workflows (Planner, Coder, Tester)
8. Deep Dive: Mode-Specific Parsers & Utilities
9. Security & SAST Integration
10. Execution Flow: Tracing a Command

---

## 1. Executive Summary & Value Proposition

**Nexus** is an enterprise-grade, AI-powered Command Line Interface (CLI) engineered to orchestrate the entire Software Development Lifecycle (SDLC) from a single terminal window. 

Instead of developers context-switching between IDEs, Jira boards, Git clients, and Security scanners, Nexus unifies these operations. It uses Natural Language Processing (NLP) backed by Azure OpenAI to understand developer intent and execute complex workflows. It is entirely workspace-agnostic, meaning it can be installed globally and run inside any local git repository.

---

## 2. Architectural Design & Philosophy

Nexus is built on a **Hub-and-Spoke** architecture combined with an **Agentic Workflow** model.

*   **Deterministic Fallbacks**: While Nexus is AI-driven, it relies on strict deterministic fallbacks. If the AI is unreachable, standard regex-based parsers take over.
*   **Zero-Trust Security**: The CLI operates locally but requires environment variables (`.env`) or a Vault connection for secure operations.
*   **Agentic Separation of Concerns**: Instead of one massive LLM prompt, Nexus uses specialized agents (Planner, Coder, Tester) to break down complex tickets into manageable, verifiable steps.

---

## 3. Core Technology Stack

The project is built entirely in **TypeScript** running on **Node.js**.

### Runtime & Language
*   **Node.js**: The underlying V8 engine powering asynchronous I/O (critical for concurrent file scanning and network requests).
*   **TypeScript (v5.8.3)**: Provides strict type safety, interfaces (`FileSnapshot`, `Ticket`, `ScanReport`), and object-oriented architectural patterns.
*   **tsx**: Used for rapid development execution without the need for manual `tsc` compilation.

### User Interface & CLI
*   **Commander.js**: The industry standard for building CLI tools in Node.js. It handles argument parsing, flags, and the global `--help` menu.
*   **Readline**: Node's native module used to create the interactive, persistent `sdlc >` shell environment.
*   **Chalk (v4.1.2)**: Used for terminal string styling (colors, bolding).
*   **Custom Spinners**: The `spinner.ts` utility provides real-time asynchronous visual feedback (e.g., "Analyzing request...").

### Operations & Integration
*   **simple-git**: A robust promise-based wrapper around the native `git` executable, used for branching, committing, and enforcing enterprise policies.
*   **dotenv**: Securely injects environment variables like Jira tokens and Azure endpoints.
*   **Azure OpenAI**: The core intelligence engine, wrapped by `llm.ts`, utilizing models like `gpt-4.1` with deterministic parameters (temperature: 0.0 - 0.2) to ensure consistent JSON outputs.

---

## 4. System Architecture Diagram

```mermaid
graph TD
    User((Developer)) -->|Commands/NLP| Terminal[CLI Terminal Session\n(cli/terminal.ts)]
    Terminal --> Orchestrator[Core Orchestrator\n(core/orchestrator.ts)]
    
    subgraph Intent Parsing Layer
        Orchestrator --> NlParser{NLP Intent Parsers}
        NlParser --> GitParser[Git Parser]
        NlParser --> SecurityParser[Security Parser]
        NlParser --> DevOpsParser[DevOps Parser]
        NlParser --> NexusParser[Nexus Core Parser]
    end
    
    subgraph Autonomous Agents
        Orchestrator --> Agents[AI Agent Layer]
        Agents --> Planner[Planner Agent]
        Agents --> Coder[Code Agent]
        Agents --> Tester[Test Agent]
    end
    
    subgraph Service & Utility Layer
        Orchestrator --> Services[Integration Services]
        Services --> Jira[Jira REST Service]
        Services --> Git[Git Operations]
        Services --> Security[Static Code Scanner]
        Services --> DevOps[CI/CD & Docker Utils]
    end
    
    subgraph External Dependencies
        NlParser -.-> LLM[(Azure OpenAI)]
        Agents -.-> LLM
        Jira -.-> RemoteJira[(Atlassian Cloud)]
        Git -.-> LocalFS[(Local File System)]
    end
```

---

## 5. Directory & Module Breakdown

The repository (`src/`) is highly modularized into 5 primary domains:

1.  **`/cli`**: Presentation layer. Contains `terminal.ts` which manages the interactive `readline` loop and renders outputs.
2.  **`/core`**: Business logic layer. Contains the `Orchestrator`, `JiraService`, and state management logic.
3.  **`/agents`**: The autonomous workforce (`planner-agent.ts`, `code-agent.ts`, `test-agent.ts`).
4.  **`/utils`**: The largest domain containing domain-specific operations (Git, Security, DevOps), Intent Parsers, and the OpenAI wrapper (`llm.ts`).
5.  **`/config`**: Environment parsing, Vault integrations, and path resolution.

---

## 6. Deep Dive: Core Orchestrator

Located at `src/core/orchestrator.ts`, this is the "brain" of Nexus. It exposes high-level asynchronous methods that the CLI consumes.

**Key Responsibilities:**
*   **State Management**: It holds references to the `StateService` and `TicketService`.
*   **Workflow Execution**: Methods like `execute(ticketId)` coordinate multiple agents. It reads a ticket, calls the `ContextBuilder` to get file data, passes data to the `PlannerAgent`, then the `CodeAgent`, writes the changes to disk, and updates Jira.
*   **Mode Switching**: It acts as the router for the 5 distinct modes:
    *   `Command Mode`: Standard CLI commands (`tickets`, `plan`).
    *   `Security Mode`: Vulnerability scanning and compliance.
    *   `DevOps Mode`: CI/CD and infrastructure parsing.
    *   `Git Mode`: Conversational version control.
    *   `NLP Mode`: Free-form codebase chat and generative editing.

---

## 7. Deep Dive: Agentic Workflows

When a user runs `execute AUTH-101`, Nexus does not just send a single prompt to the LLM. It utilizes a multi-agent system.

### 1. The Context Builder (`context-builder.ts`)
Before any AI is invoked, the context builder scans the local workspace. It creates a highly optimized string representation of the codebase, ensuring the LLM understands the current architecture without blowing out the token limit.

### 2. Planner Agent (`planner-agent.ts`)
The Planner reads the ticket and the context. It does not write code. Its sole job is to return a strict JSON array of implementation steps (`{"steps": ["Create User interface", "Update auth route"]}`). This enforces architectural thinking.

### 3. Code Agent (`code-agent.ts`)
The Code Agent takes the Planner's steps and the codebase context. It outputs strict JSON containing file paths and complete file contents. The orchestrator receives this and overwrites/creates the physical files on disk.

### 4. Test Agent (`test-agent.ts`)
Once code is written, the Test Agent is invoked. It looks at the *diff* generated by the Code Agent and generates Jest unit tests to cover the new logic.

---

## 8. Deep Dive: Mode-Specific Parsers & Utilities

Nexus relies heavily on **Intent Parsers**. These are located in `/utils/` (e.g., `devops-nl-parser.ts`, `security-nl-parser.ts`).

**How Intent Parsing Works:**
Instead of fragile regex, Nexus sends the user's natural language string to Azure OpenAI with a strict `Pydantic`-style system prompt. 
For example, if a user types: *"check the dockerfile for bugs"*, the LLM is instructed to return a JSON object mapping to predefined commands:
`{ "command": "docker-validate", "args": [] }`

This allows developers to speak naturally while the system executes strict, predictable internal functions.

---

## 9. Security & SAST Integration

The `/utils/security-operations.ts` and `code-scanner.ts` modules form an enterprise-grade governance engine.

*   **Static Code Analysis (SAST)**: Nexus iterates through local files and uses the LLM (via `performAiVulnerabilityScan`) to identify vulnerabilities categorized by OWASP (Injection, XSS, Broken Access Control, Secrets).
*   **Auto-Correction Layer**: Because LLMs hallucinate line numbers, `code-scanner.ts` contains an auto-correction algorithm that cross-references the LLM's reported malicious code snippet with the physical file on disk to correct the line number before reporting it to the user.
*   **Infrastructure Auditing**: It parses `Dockerfile`s and `main.tf` (Terraform) files to ensure non-root users are used, state is encrypted, and minimal base images are utilized.
*   **Compliance Enforcement**: It hooks into `git-policy.ts` to ensure branch names follow GitFlow standards and commits follow Conventional Commits format.

---

## 10. Execution Flow: Tracing a Command

To summarize the architecture, let's trace exactly what happens when a developer types: **"push AUTH-101 to remote"**

1.  **`cli/terminal.ts`** intercepts the string via the Node `readline` module.
2.  The string is passed to **`orchestrator.parseNexusNaturalLanguage()`**.
3.  The **`nexus-nl-parser.ts`** sends the string to Azure OpenAI, which returns: `{ "command": "push", "args": ["AUTH-101"] }`.
4.  The terminal catches this intent and prompts the user for a safety confirmation (Yes/No).
5.  If yes, **`orchestrator.push("AUTH-101")`** is invoked.
6.  The **`JiraService`** checks the ticket status.
7.  **`git-operations.ts`** executes `git add .`, generates a conventional commit message, and runs `git push`.
8.  The **`StateService`** updates the local `.sdlc/status.json` to mark the ticket as COMPLETED.
9.  The Terminal renders a green `chalk` success panel summarizing the pushed files.

*End of Report*
