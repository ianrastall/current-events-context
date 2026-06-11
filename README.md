# current-events-context

This repository provides a daily, structured summary of global news and events in YAML format. Its primary purpose is to offer rich, machine-readable context for Large Language Models (LLMs) and AI Agents, especially for periods that fall outside their training data or knowledge cutoff dates.

## Project Status & Structure

The repository is actively maintained and organized chronologically by year and month (e.g., `/2026/03/`). Each file is named by its ISO date: `YYYY-MM-DD.yaml` (e.g., `2026-03-14.yaml`).

Currently, the files fall into two distinct tiers of detail:

* **Daily Snapshots (First-Draft, ~5 KB):** The vast majority of the archive consists of these baseline files. They contain a brief, scraped summary of the day's key events categorized by topic. 
* **Deep Context (Reviewed-Draft, ~50 KB):** These are expanded, heavily researched files. They include rigorous factual support, background information on key players, geographical coordinates, causality reports, and source URLs. 

**The ongoing goal of this project is to incrementally upgrade all the 5KB "Daily Snapshots" into 50KB "Deep Context" files.**

## How to Contribute (LLM Deep Research)

This is an open project, and contributions to expand the context engine are highly appreciated! The only contributions we are currently looking for are **LLM deep research projects** to upgrade existing 5KB Daily Snapshots into 50KB Deep Context files.

Because the repository creator is currently running automated scripts to backfill the archive from **2002 moving backwards**, please avoid the 2001–2004 era as the foundational architecture for those years is still being structured.

To minimize the chances of two contributors picking the exact same day at the exact same time, we ask that you pick dates entirely at random.

**Please adhere to the following workflow:**

1. **Pick a Random Date in the Middle:** Choose an existing, unexpanded `YYYY-MM-DD.yaml` Daily Snapshot completely at random from the middle of our available time period (e.g., anywhere between 2005 and 2025). Using a random number generator to pick a year and month is highly recommended!
2. **Do Not Generate New Dates:** Please DO NOT backfill or create new YAML files for missing dates. The skeleton of the repository and daily file generation is handled via automated backend scripts. Only edit existing files.
3. **Check for Duplication:** Before you start your LLM deep research, check the repository's open Pull Requests to ensure someone else hasn't already submitted an expansion for your randomly selected date.
4. **Submit Your Expansion:**
    * **Fork** this repository.
    * Make your deep-context additions to the existing YAML file, ensuring you adhere to the project's strict YAML schema. 
    * Submit a **Pull Request**. 

## Getting Started (for Local Use)

You can browse the YAML files directly on GitHub. To use them programmatically in your own LLM pipelines or RAG applications, clone the repository:

```bash
git clone [https://github.com/ianrastall/current-events-context.git](https://github.com/ianrastall/current-events-context.git)