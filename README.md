# current-events-context

[](https://opensource.org/licenses/MIT)

This repository provides a daily, structured summary of global news and events in YAML format. Its primary purpose is to offer rich context for Large Language Models (LLMs), especially for periods that may fall outside their training data or knowledge cutoff dates.

## Project Status & Structure

The repository is actively maintained and organized by year (e.g., `/2026`, `/2025`). Each file is named by date: `YYYY-MM-DD.yaml` (e.g., `2026-03-14.yaml`).

Currently, the files fall into two categories:

  * **Deep Context (Recent entries):** The latest entries are deep-researched and comprehensive, averaging around **50KB** per file.
  * **Daily Snapshots (Older entries):** The vast majority of older dates are currently placeholders containing a brief summary of the day's key events, averaging around **5KB** per file.

The ongoing goal of this project is to incrementally upgrade all the 5KB "Daily Snapshots" into 50KB "Deep Context" files.

## The Vision: Two Tiers of Detail

1.  **Daily Snapshot:** A concise, factual overview of the day's most significant global news.
2.  **Deep Context:** A highly detailed expansion of a Daily Snapshot that includes:
      * Background information on key players and organizations.
      * The historical context leading up to major announcements.
      * Analysis of the potential short and long-term implications of events.
      * Connections to ongoing trends or future developments.

## How to Contribute

This is a project that anyone who uses LLMs can contribute to, and your help building out this context engine is highly appreciated\!

Please DO NOT backfill or create new YAML files for missing dates. The skeleton of the repository and daily file generation is handled separately.

Here is the required workflow:

1.  **Pick an Existing File:** Choose an existing, unexpanded `YYYY-MM-DD.yaml` file (usually around \~5KB) that you'd like to research and expand into a Deep Context file (\~50KB).
2.  **Check for Duplication:** Before you start researching, please check the repository's open Pull Requests to ensure someone else isn't already working on an expansion for that specific date.
3.  **Submit Your Expansion:**
      * **Fork** this repository.
      * Make your deep-context additions to the existing YAML file.
      * Submit a **Pull Request**. (If you're new to GitHub, there are many excellent guides online for "how to create a pull request").

## Getting Started (for Local Use)

You can browse the YAML files directly on GitHub. To use them programmatically, clone the repository:

```bash
git clone https://github.com/ianrastall/current-events-context.git
```

You can then parse the YAML files locally using any standard library (like `PyYAML` in Python).

## License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.
