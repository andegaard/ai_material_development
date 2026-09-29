# Multi-Agent R&D System Instructions: Anthropic-Powered Steel Innovation Pipeline

This document defines the agent architecture, Anthropic model configurations, temperatures, and behavioral protocols for the autonomous steel research and development system.

---

## Global System Configuration & Model Strategy
* **Core LLM Provider:** Anthropic Claude API
* **Design Philosophy:** Niche-optimized models balancing extreme structural fidelity (for data parsing and code execution) with deep analogical reasoning (for frontier research and strategic gap analysis).

---

## 1. Agent 1: Autonomous Web Scraper & Domain Portfolio Classifier
* **Role:** Market Intelligence & Portfolio Architect
* **Assigned Model:** `claude-3-5-sonnet-20241022`
* **Temperature:** `0.1` (Low creativity, high precision for technical data extraction)
* **Input:** Company Name and Main Web Page URL.
* **Core Objective:** Autonomously crawl public web data to map out the company's material portfolio, organizing them into distinguishable functional domains (e.g., Wear-Resistant, High-Strength Structural, Tool Steels).
* **Deliverable:** Baseline Portfolio & Domain Classification Report (`agent_1_baseline.json`).

---

## 🛑 Human-in-the-Loop Intermission: Domain Selection
* **Action:** The human operator reviews Agent 1's domain breakdown and selects **one specific steel domain** to drive Agent 2.

---

## 2. Agent 2: Open-Ended Frontier Research & Mechanism Hunter
* **Role:** Academic Metallurgist & Trend Analyst
* **Assigned Model:** `claude-3-5-sonnet-20241022`
* **Temperature:** `0.3` (Balanced exploratory reasoning to catch "unknown unknowns")
* **Input:** The specific steel domain selected by the human operator.
* **Core Objective:** Scan global literature, patents, and research databases for cutting-edge mechanisms, extracting chemical composition vectors, microstructural phases, and processing routes.
* **Deliverable:** Independent Frontier Research & Mechanism Report (`agent_2_report.json`).

---

## 3. Agent X: Thermodynamic Simulator & Extrapolating Designer
* **Role:** Computational Materials Scientist (CALPHAD & Extrapolation Specialist)
* **Assigned Model:** `claude-3-5-sonnet-20241022`
* **Temperature:** `0.0` (Strictly deterministic execution for accurate code writing and numerical processing)
* **Input:** Frontier Research Report from Agent 2.
* **Core Objective:** Interpret Agent 2's findings, isolate **positive trends** (e.g., parameters that correlate with superior mechanical performance), and **extrapolate** beyond published data bounds to formulate new virtual prototype alloy recipes using thermodynamic simulation (TC-Python).
* **Deliverable:** Thermodynamic Simulation & Extrapolated Alloy Recipe Report (`agent_x_simulation_results.json`).

---

## 4. Agent 3: Strategic Gap Analysis & TRIZ Problem Solver
* **Role:** Chief Technology Officer (CTO) & Innovation Strategist
* **Assigned Model:** `claude-3-opus-20240229` (High-tier deep reasoning model for complex strategic trade-offs)
* **Temperature:** `0.4` (Moderate creativity for cross-domain innovation and contradiction resolution)
* **Input:** Agent 1's Baseline Report + Agent X's Extrapolated Alloy Recipe Report.
* **Core Objective:** Compare current company capabilities against simulated future materials, resolving metallurgical trade-offs using structured problem-solving (TRIZ/First Principles).
* **Deliverable:** Strategic Innovation & Implementation Roadmap (`agent_3_roadmap.md`).

---

## 5. Agent 4: IP-Freedom & Life Cycle Assessment (LCA) Optimizer
* **Role:** Patent Attorney & Sustainability Engineer
* **Assigned Model:** `claude-3-5-sonnet-20241022`
* **Temperature:** `0.1` (Rigid compliance and factual auditing)
* **Input:** Strategic Innovation Roadmap and proposed alloy recipes.
* **Core Objective:** Validate Freedom-to-Operate (FTO) via patent searches and simulate CO2/energy footprints for the manufacturing routes. Issue final Feasibility Scores.
* **Deliverable:** Final IP & Sustainability Risk Audit (`agent_4_audit.md`).