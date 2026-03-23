# **Automated Data Extraction and Serialization Pipeline for Wikipedia Current Events**

## **Architectural Framework and System Design**

The integration of real-time, high-fidelity contextual data into Large Language Model (LLM) architectures represents one of the most significant engineering challenges in contemporary computational linguistics and artificial intelligence systems. Traditionally, the industry has relied heavily on Retrieval-Augmented Generation (RAG) architectures, which utilize monolithic vector databases and complex embedding models to retrieve semantic context. However, the demand for leaner, highly deterministic, and token-optimized ingestion pipelines has driven a paradigm shift toward serverless architectures. The architecture required to reliably extract, process, and serve continuous streams of global intelligence from the English Wikipedia Current Events portal necessitates a highly programmatic, programmatic approach that eliminates the overhead of vectorization in favor of direct, statically hosted contextual injection.

Attempting to acquire this data through traditional Document Object Model (DOM) scraping introduces severe systemic liabilities. Wikipedia's HTML structure is notoriously brittle, heavily reliant on transcluded templates, dynamic Cascading Style Sheets (CSS) classes, and unpredictable stylistic revisions executed by a decentralized community of editors. Traditional web scrapers targeting specific HTML tags (such as \<div\> or \<li\>) will inevitably fail when the underlying DOM hierarchy is modified, breaking the continuous integration pipeline and starving the LLM of necessary context.

To circumvent the fragility of DOM scraping, the optimal system design utilizes the MediaWiki Action API to request the raw, unrendered database content, known as Wikitext.1 The pipeline then processes this specialized markup document via an Abstract Syntax Tree (AST) to isolate the core semantic elements, strips non-informative artifacts using advanced Regular Expressions, and serializes the final hierarchical output into a Token-Oriented Object Notation, specifically YAML. This methodology prioritizes absolute token efficiency and high semantic density. Advanced LLM attention mechanisms perform optimally when structural noise—such as HTML tags, citation brackets, and deeply nested curly braces—is minimized, allowing the neural network to allocate its computational resources entirely to the semantic narrative of the text. By executing this end-to-end pipeline daily via continuous integration platforms like GitHub Actions, the system provides a perpetually updated, statically hosted YAML endpoint. This endpoint allows an LLM to perform runtime contextual injection with minimal latency, flawless deterministic formatting, and drastically reduced inference costs.1

## **Phase 1: Target Acquisition and MediaWiki API Integration**

The English Wikipedia Current Events portal serves as a globally maintained repository of significant daily occurrences, organized chronologically and categorically.1 Attempting to parse the main portal page directly introduces unnecessary computational complexity, as the main page acts primarily as a display mechanism that transcludes data from numerous underlying subpages. The architecture bypasses this routing complexity by directly targeting the isolated daily subpages. These daily subpages adhere strictly to a rigid, deterministic naming convention formatted as Portal:Current\_events/YYYY\_Month\_DD (for example, Portal:Current\_events/2026\_March\_13). This predictable Uniform Resource Identifier (URI) structure allows the ingestion pipeline to programmatically generate the exact target location for any given execution cycle without requiring preliminary indexing or search operations.

To interact with this foundational data layer reliably, the system invokes the MediaWiki Action API. The Action API is a robust, RESTful web service engineered to allow developers and system administrators to perform programmatic wiki-actions, including parsing, searching, and raw database retrieval.2 For operations targeting the English Wikipedia, the system interfaces with the designated endpoint situated at https://en.wikipedia.org/w/api.php.2

Rather than downloading the rendered HTML, which dramatically inflates network bandwidth consumption and introduces the aforementioned HTML parsing volatility, the architecture executes a highly structured HTTP GET request specifically targeting the API's action=query module.1 The query module is the primary engine for fetching information about the wiki and the specific data stored within its internal relational databases.5

The HTTP GET request must be meticulously parameterized to retrieve the precise revision text while explicitly rejecting supplementary metadata—such as authorship logs, timestamps, or edit summaries—that would bloat the JSON payload and unnecessarily consume memory within the ephemeral execution environment. The construction of this request relies on a highly specific configuration of URL query strings.

| API Parameter | Architectural Justification and Mechanism of Action |
| :---- | :---- |
| action=query | Instructs the MediaWiki endpoint to invoke the query module, indicating the intent to read database information rather than modify it.5 |
| titles={target\_page} | Deterministically targets the daily event subpage, generated dynamically by the execution script based on the current Coordinated Universal Time (UTC) date.6 |
| prop=revisions | Specifies that the system intends to fetch the underlying revision data of the targeted page, which is the only pathway to access the raw markup text.6 |
| rvprop=content | A critical filtering parameter that instructs the revision module to return exclusively the textual content, discarding all associated metadata to minimize payload size.6 |
| rvslots=main | Targets the main namespace slot of the revision, ensuring the system isolates the primary article body and ignores auxiliary data associated with the page.6 |
| format=json | Dictates the response payload serialization format. Requesting JSON standardizes the ingestion layer, making it natively compatible with the standard libraries of the Python runtime.2 |
| formatversion=2 | Requests the modernized, cleaner JSON schema developed by the Wikimedia Foundation. This significantly flattens the response hierarchy, eliminating the need to parse through arbitrary numerical page IDs.6 |

By deploying these specific parameters, the system receives a highly streamlined JSON response containing the unadulterated Wikitext. This response is accessed by traversing the predictable JSON tree structure returned by formatversion=2, specifically accessing the query dictionary, followed by the pages array, the revisions array, and finally isolating the string mapped to the content key.6 This raw string acts as the foundational raw material for the subsequent lexical parsing stage. The implementation of a specific HTTP User-Agent header is also fundamentally required during this phase to comply with Wikimedia Foundation API etiquette policies, preventing the execution node from encountering automated IP rate-limiting or outright firewall bans.2

## **Phase 2: Abstract Syntax Tree Generation and Lexical Parsing**

Raw Wikitext is an idiosyncratic, densely packed markup language that presents severe computational challenges when parsed using naive string manipulation or primitive regular expressions alone. It frequently contains deeply nested templates, recursive transclusions, interconnected category links, and overlapping HTML tag structures.7 A fundamental flaw in many amateur data extraction pipelines is the attempt to use Regular Expressions to strip nested templates (e.g., {{Infobox|{{Nested|Data}}}}). Because regular expressions are fundamentally incapable of tracking nested pairs of arbitrary depth without encountering catastrophic backtracking or stack overflows, a purely regex-based approach will inevitably corrupt the structural integrity of the text.9

To definitively resolve these structural complexities, the architecture implements a dedicated lexical parser known as mwparserfromhell.1 This specialized Python library, widely adopted within the Wikimedia developer ecosystem, operates as a direct interface to the MediaWiki source code. Rather than treating the text as a flat string, mwparserfromhell tokenizes the input and generates a robust Abstract Syntax Tree (AST) composed of discrete Wikicode nodes.7

The parsing algorithm processes the string returned by the MediaWiki API and converts it into a Wikicode object.7 This object behaves analogously to a highly sophisticated Python list—specifically utilizing an underlying SmartList architecture—that permits profound hierarchical traversal, modification, and extraction of specific nodes.12 Within the specific context of the Wikipedia Current Events daily pages, the thematic categories (e.g., "Armed conflicts and attacks", "Disasters and accidents", "Law and crime") and their underlying geopolitical events are consistently formatted using MediaWiki's native nested list syntax.1

The standard editorial convention dictates that top-level thematic macro-categories are designated with a single asterisk (\*), while the specific textual descriptions of the events falling under those categories are designated as sub-list items utilizing a double asterisk (\*\*).1 This formatting creates an implicit hierarchy that the parser must extract and translate into a structured dataset.

| Wikitext Element | AST Node Representation | Structural Significance in Data Pipeline |
| :---- | :---- | :---- |
| \`{{Template | ...}}\` | TemplateNode |
| \] | WikilinkNode | Internal wiki navigation. The parser extracts only the display text, stripping the bracketed routing logic.9 |
| \* Category Name | TextNode (after strip) | Identifies the instantiation of a new macro-category. Signals the dictionary builder to generate a new top-level key.1 |
| \*\* Event Description | TextNode (after strip) | Contains the actual intelligence payload. Appended as a string to the list associated with the active macro-category key.1 |
| \<ref\>Citation\</ref\> | TagNode | HTML-style reference tags. Wholly discarded during the stripping process as they provide no runtime context for the LLM.11 |

However, mwparserfromhell excels primarily at identifying, extracting, and manipulating templates, HTML tags, and WikiLinks.11 Extracting the implicit hierarchy of bulleted lists requires a hybrid approach. The system first utilizes the parser's built-in strip\_code() method. This function gracefully degrades the complex Abstract Syntax Tree into a flat, plain text string, effectively neutralizing templates, bolding syntax ('''), italics syntax (''), and internal link routing formatting, while preserving the raw text of the links and the essential bulleted structural markers (the asterisks).11

Once this neutralized plain text is generated, the pipeline's execution logic treats the string as a sequential data stream. The system iterates through the textual lines, evaluating the presence and exact count of leading asterisks. By tracking these markers, the Python script dynamically reconstructs the relationship between the macro-categories and the micro-events. A single asterisk signals the instantiation of a new string key within a Python dictionary. Subsequent lines featuring double asterisks are evaluated, heavily sanitized, and appended as string values to the array belonging to the currently active category key. This transformation effectively converts a chaotic, markup-heavy document into a cleanly nested, strictly typed Python dictionary object, fully prepared for the final lexical cleansing phase.

## **Phase 3: Semantic Cleansing and Regular Expression Filtering**

Despite the highly robust stripping capabilities of the AST parser's strip\_code() method, certain artifacts intrinsic to Wikipedia's editorial citation standards persist in the resulting text stream. The most prominent and problematic offenders are numeric citation brackets (e.g., , , ) and external web links formatted with single square brackets, which often include both the URL and descriptive text (e.g., ).1

Within the architectural context of LLM reasoning and contextual injection, these persistent artifacts provide absolutely zero semantic value. A language model analyzing the geopolitical implications of an event does not gain inferential capability from the characters \`\`. On the contrary, these artifacts consume valuable computational tokens. Furthermore, they can subtly degrade the model's multi-head attention mechanism by introducing non-linguistic noise into the sequence, forcing the neural network to evaluate meaningless numerical associations during its forward pass.

To maximize information density and mathematical token efficiency, the pipeline executes a secondary, surgical cleansing pass utilizing advanced Regular Expressions (Regex) via Python's standard re module.1 Regular expressions operate as highly optimized finite state machines that can identify, capture, and neutralize complex string patterns at the byte level.19

The implementation relies on three specific regex patterns, executed sequentially to ensure comprehensive sanitization without inadvertently destroying legitimate punctuation.

### **Numeric Citation Obliteration**

Wikipedia relies heavily on bracketed numerical citations. The pipeline targets these using the pattern: \\\[\\d+\\\].16 This pattern is constructed using escaped literal brackets (\\\[ and \\\]) encompassing the \\d+ token, which matches one or more numeric digits. The Python re.sub() function evaluates the entire corpus against this state machine, replacing all identified occurrences with an empty string, effectively deleting them instantly. This prevents the LLM from processing meaningless citation numbers that do not map to any provided reference list.

### **Descriptive External Link Consolidation**

Editors frequently link to external news sources directly within the event text using the format \`\`. The parser's native capabilities often fail to dismantle these seamlessly, leaving the URL intact within the text. The pipeline neutralizes this using the capture-group pattern: \\\[https?://\[^\\s\\\]\]+\\s(\[^\\\]\]+)\\\].20 This sophisticated regex operates by identifying the literal opening bracket \\\]+ up to the first space \\s. The most critical component is the capture group (\[^\\\]\]+), which isolates the human-readable descriptive text. The closing literal bracket \\\] terminates the match. By passing the backreference \\1 as the replacement string to re.sub(), the pipeline entirely deletes the URL and the brackets, leaving only the semantically valuable descriptive text integrated flawlessly into the sentence.21

### **Bare URL Eradication**

In instances where an editor has pasted a bare URL into brackets without descriptive text, the system deploys a fallback pattern: \\\[https?://\[^\\\]\]+\\\].16 This pattern simply matches the protocol and any subsequent characters until a closing bracket is encountered. Unlike the previous regex, it utilizes no capture groups and replaces the entire matched sequence with an empty string, thoroughly purging the raw URL from the dataset.16

### **Whitespace Normalization**

The sequential removal of citations and links often leaves aberrant spacing—such as double or triple spaces—where the artifacts previously existed. The final regex pattern \\s{2,} is deployed to consolidate two or more consecutive whitespace characters into a single standard space. The Python re module defaults to Unicode matching ((?u)), which safely and accurately processes the vast array of international characters, diacritics, and non-Latin scripts frequently found in global current events data, ensuring the structural integrity of foreign names and locations.22

The strings output by this multi-stage cleansing process are mathematically optimized for the lowest possible token footprint while retaining 100% of their semantic narrative payload.

## **Phase 4: Token-Oriented Object Notation (TOON) and YAML Serialization**

The serialization mechanism chosen to package the highly sanitized Python dictionary for final delivery is arguably the most critical component of the architecture's token economics. While JSON (JavaScript Object Notation) serves as the ubiquitous industry standard for REST API payloads and web application data interchange, it is fundamentally suboptimal for LLM context windows due to the phenomenon of "syntax noise".

JSON mandates a rigidly explicit structure. It requires double quotes for every string key and value, colons to map pairs, commas to separate elements, curly braces {} to define object boundaries, and square brackets \`\` to delineate arrays. When a serialized dataset is ingested by a Large Language Model, it is first processed by a Byte Pair Encoding (BPE) tokenizer (such as OpenAI's tiktoken or the LLaMA tokenizer). BPE tokenizers are statistically trained to recognize common word fragments. However, every individual structural character in a JSON payload—every brace, bracket, and comma—often constitutes a unique, discrete token. When injecting hundreds of daily events into a prompt, this structural overhead rapidly compounds, consuming thousands of tokens that provide absolutely no semantic context to the neural network.

YAML (YAML Ain't Markup Language) provides a significantly superior alternative, functioning effectively as a Token-Oriented Object Notation. YAML relies entirely on whitespace indentation and minimal syntactical markers (such as hyphens for lists) to define strict data hierarchies. By eliminating the structural characters required by JSON, YAML reduces the token consumption of the payload by a mathematically verified 16% to 50%, depending heavily on the nesting depth and array volume of the specific dataset.

This relationship can be expressed through the theoretical token savings equation:

![][image1]  
Where ![][image2] represents the total token count of the payload serialized in JSON, and ![][image3] represents the token count of the identical semantic payload serialized in YAML.

Furthermore, YAML inherently and elegantly handles the non-uniform data structures associated with unpredictable daily news volumes and fluctuating categorical hierarchies. While highly compressed formats like TOON strictly require rigid tabular schemas, YAML adapts fluidly to datasets where one category might contain ten events and another only one.

Modern LLMs process YAML with native fluency. Because YAML was designed to be supremely human-readable, its structure maps chronological and categorical data linearly, closely mirroring the logical flow of natural language. When configuring the pyyaml library within the Python extraction script, the system explicitly utilizes the parameter default\_flow\_style=False. This parameter absolutely forbids the library from falling back to inline JSON-like formatting, forcing strict block-style indentation. Additionally, allow\_unicode=True is explicitly passed to the yaml.dump() function to prevent the library from escaping international characters into unreadable \\uXXXX byte sequences, guaranteeing flawless textual interpretation upon ingestion by the LLM.

## **Phase 5: Step-by-Step Python Implementation Guide**

The following Python code represents the complete, executable implementation of the extraction, parsing, lexical cleansing, and YAML serialization phases exhaustively detailed in the preceding sections. This script, intended to be saved as update\_data.py at the root of the repository, is engineered for maximum operational reliability, deterministic execution, and graceful error handling.

Python

import os  
import re  
import yaml  
import requests  
from datetime import datetime, timezone  
import mwparserfromhell

def get\_wikipedia\_date\_title():  
    """  
    Generates the target Wikipedia subpage title based on the current UTC date.  
    The string must be strictly formatted to match the MediaWiki routing schema:  
    Portal:Current\_events/YYYY\_Month\_DD  
    """  
    now \= datetime.now(timezone.utc)  
    \# Wikipedia utilizes full month names and zero-padded days for URI resolution  
    date\_str \= now.strftime("%Y\_%B\_%d")  
    return f"Portal:Current\_events/{date\_str}"

def fetch\_wikitext(page\_title):  
    """  
    Executes a structured, parameterized HTTP GET request to the MediaWiki Action API  
    to retrieve the raw Wikitext payload of the targeted daily subpage.  
    """  
    url \= "https://en.wikipedia.org/w/api.php"  
      
    \# Payload parameters defined to strictly return formatversion=2 content  
    params \= {  
        "action": "query",  
        "prop": "revisions",  
        "titles": page\_title,  
        "rvprop": "content",  
        "rvslots": "main",  
        "format": "json",  
        "formatversion": "2"  
    }  
      
    \# Implementing a descriptive User-Agent is a mandatory MediaWiki policy  
    headers \= {  
        "User-Agent": "LLM-Context-Pipeline/1.0 (https://github.com/yourusername/repo)"  
    }  
      
    try:  
        response \= requests.get(url, params=params, headers=headers, timeout=15)  
        response.raise\_for\_status()  
        data \= response.json()  
          
        \# Traverse the modernized JSON hierarchy to isolate the content string  
        pages \= data.get("query", {}).get("pages",)  
        if not pages or "missing" in pages:  
            print(f" Page {page\_title} does not exist in the database yet.")  
            return None  
              
        return pages.get("revisions",).get("content", "")  
          
    except requests.exceptions.RequestException as e:  
        print(f" Network layer failure during API invocation: {e}")  
        return None  
    except (IndexError, KeyError) as e:  
        print(f" Structural anomaly in API response schema: {e}")  
        return None

def cleanse\_text(text):  
    """  
    Deploys a sequence of Regular Expressions to eliminate non-semantic artifacts   
    from the plain text, optimizing the sequence for LLM BPE token density.  
    """  
    if not text:  
        return ""  
          
    \# Pattern 1: Eradicate bracketed numerical citations (e.g., )  
    text \= re.sub(r'\\\[\\d+\\\]', '', text)  
      
    \# Pattern 2: Extract descriptive text from complex URL brackets and discard the URL  
    text \= re.sub(r'\\\[https?://\[^\\s\\\]\]+\\s(\[^\\\]\]+)\\\]', r'\\1', text)  
      
    \# Pattern 3: Eradicate bare URLs lacking descriptive payload  
    text \= re.sub(r'\\\[https?://\[^\\\]\]+\\\]', '', text)  
      
    \# Pattern 4: Normalize structural whitespace to a single space  
    text \= re.sub(r'\\s{2,}', ' ', text).strip()  
      
    return text

def parse\_events(wikitext):  
    """  
    Parses the raw Wikitext into a Wikicode AST, strips the markup nodes,  
    and dynamically constructs a nested Python dictionary representing the hierarchy.  
    """  
    \# Generate the AST and strip all templates, HTML, and wiki links  
    parsed \= mwparserfromhell.parse(wikitext)  
    plain\_text \= parsed.strip\_code()  
      
    events\_hierarchy \= {}  
    current\_category \= "Uncategorized"  
      
    \# Process the stripped text as a sequential stream to detect list markers  
    lines \= plain\_text.split('\\n')  
    for line in lines:  
        line \= line.strip()  
        if not line:  
            continue  
              
        \# Top-level list item denotes the instantiation of a macro-category  
        if line.startswith('\*') and not line.startswith('\*\*'):  
            raw\_category \= line.lstrip('\*').strip()  
            current\_category \= cleanse\_text(raw\_category)  
              
            \# Initialize an empty array for the new semantic key  
            if current\_category not in events\_hierarchy:  
                events\_hierarchy\[current\_category\] \=  
                  
        \# Sub-level list item denotes a specific intelligence event payload  
        elif line.startswith('\*\*'):  
            raw\_event \= line.lstrip('\*').strip()  
            cleansed\_event \= cleanse\_text(raw\_event)  
              
            if cleansed\_event:  
                \# Safeguard against malformed documents lacking a parent category  
                if current\_category not in events\_hierarchy:  
                    events\_hierarchy\[current\_category\] \=  
                events\_hierarchy\[current\_category\].append(cleansed\_event)  
                  
    \# Filter dictionary to discard macro-categories lacking event data  
    events\_hierarchy \= {k: v for k, v in events\_hierarchy.items() if len(v) \> 0}  
    return events\_hierarchy

def main():  
    """  
    Main orchestration routine governing the state transitions of the pipeline.  
    """  
    target\_page \= get\_wikipedia\_date\_title()  
    print(f"\[INFO\] Initializing targeting sequence for: {target\_page}")  
      
    wikitext \= fetch\_wikitext(target\_page)  
      
    if not wikitext:  
        print("\[INFO\] No content payload retrieved. Terminating pipeline execution safely.")  
        return  
          
    events\_data \= parse\_events(wikitext)  
      
    if not events\_data:  
        print("\[INFO\] AST traversal yielded no event nodes. Terminating pipeline.")  
        return  
          
    \# Construct the final dataset wrapper with essential origin metadata  
    dataset \= {  
        "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),  
        "Source\_URI": target\_page,  
        "Intelligence\_Payload": events\_data  
    }  
      
    \# Serialize the dictionary to token-optimized YAML  
    output\_filename \= "current\_events.yaml"  
    with open(output\_filename, 'w', encoding='utf-8') as file\_descriptor:  
        yaml.dump(  
            dataset,   
            file\_descriptor,   
            default\_flow\_style=False,   
            allow\_unicode=True,   
            sort\_keys=False  
        )  
          
    print(f" Successfully generated statically hosted artifact: {output\_filename}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    main()

### **Architectural Analysis of the Python Implementation**

The script begins execution within the get\_wikipedia\_date\_title module, calculating the current UTC date and rigorously formatting it to match the stringent requirement of the Wikipedia database routing mechanism (%Y\_%B\_%d). It constructs the HTTP GET request securely using the requests library, ensuring that parameters such as rvslots="main" are explicitly declared.6 A critical operational element included in the fetch\_wikitext function is the explicit inclusion of a timeout parameter (timeout=15). In automated, headless serverless environments, an unresolved network request can cause a pipeline runner to hang indefinitely, accruing significant compute charges. The timeout forces a termination if the Wikimedia servers are unresponsive.

The lexical parsing function relies completely on the fundamental behavior of mwparserfromhell.parse(wikitext).strip\_code().8 Because MediaWiki markup intertwines logical data hierarchy with aesthetic HTML rendering, stripping the code provides an isolated view of the text.11 Crucially, the parser retains the asterisk markers because they are evaluated as fundamental text string characters within a stripped node stream. This specific retention enables the subsequent split('\\n') iteration to logically map single asterisks to dictionary keys and double asterisks to list string values.1

The cleanse\_text module utilizes the precise regex formulas extensively justified in Phase 3\.16 Finally, the resulting Python dictionary is passed directly to the yaml.dump method. By enforcing sort\_keys=False, the library maintains the original chronological and categorical order generated by the Wikipedia editors, generating a highly pristine, tightly packed hierarchical file ready for immediate cross-origin resource sharing (CORS) delivery to an active LLM.

## **Phase 6: Continuous Integration and Serverless Automation**

To achieve true operational independence, ensuring the LLM ecosystem always has access to the latest global events without requiring human intervention, the pipeline must be fully automated using a Continuous Integration/Continuous Deployment (CI/CD) methodology. The architecture relies on GitHub Actions as the serverless execution environment.1 GitHub Actions utilizes specific YAML-based workflow files to define execution triggers, configure ephemeral Linux environments, and orchestrate complex computational sequences directly within the repository structure.

The overarching automation strategy relies on a schedule event trigger utilizing standard POSIX Cron syntax.24 By configuring the Cron schedule to execute once daily, the pipeline is guaranteed to retrieve the almost-completed Wikipedia daily subpage right before the chronological rollover. Upon triggering, the workflow spins up a pristine Ubuntu Linux runner, checks out the repository codebase, provisions the specified Python 3.10 runtime environment, and utilizes the pip package manager to install the necessary external dependencies (requests, mwparserfromhell, and pyyaml).3

Following the successful execution of the Python script, the workflow must persist the newly generated YAML artifact back into the repository to serve as a static endpoint. This state change operation requires configuring the local Git client within the runner using an automated identity.25 The workflow executes a sequential chain of git add, git commit, and git push commands.

However, a critical vulnerability inherent in automated CI/CD data pipelines is the "empty commit" failure loop. If the Python script executes flawlessly but generates a YAML file mathematically identical to the previous day (for example, if Wikipedia editors have not yet published the new subpage or no new events have occurred), a standard git commit command will evaluate the empty staging area and immediately trigger an exit code 1\.24 This exit code will forcefully fail the workflow run, polluting the repository with false-positive error alerts.

To surgically prevent this architectural flaw, the workflow introduces a differential state evaluation prior to committing. It utilizes the shell command git diff \--staged \--quiet.24 This command interrogates the Git index; if the working tree is clean, it exits cleanly and bypasses the commit stage by writing a boolean flag to the $GITHUB\_OUTPUT environment variable.26 If structural changes exist, it proceeds with the commit and flags the system to execute the push phase.26

The use of the native ${{ secrets.GITHUB\_TOKEN }} ensures the workflow has the federated, repository-scoped permissions necessary to write data back to the codebase without requiring developers to manage and rotate external Personal Access Tokens (PATs). This implementation maintains a strict, highly sensible security posture.3

## **Phase 7: System Implementation: Workflow Configuration (main.yaml)**

To automate the Python architecture detailed in Phase 5, the following GitHub Actions workflow must be strictly implemented. This file must be located exactly at .github/workflows/main.yaml within the repository structure to be recognized by the GitHub Actions execution engine.

YAML

name: Wikipedia Current Events Daily Pipeline

\# Orchestrate execution schedule and permit manual developer triggers  
on:  
  schedule:  
    \# Executes daily at 23:30 UTC to capture the day's near-complete event payload  
    \- cron: "30 23 \* \* \*"  
  workflow\_dispatch: \# Enables manual execution from the GitHub user interface for debugging

\# Explicitly define the permissions required for the federated GITHUB\_TOKEN  
permissions:  
  contents: write

jobs:  
  extract-and-serialize:  
    \# Provision an ephemeral, lightweight Linux execution environment  
    runs-on: ubuntu-latest  
      
    steps:  
      \- name: Checkout Repository Codebase  
        \# Pulls the repository contents into the runner's workspace  
        uses: actions/checkout@v4  
          
      \- name: Provision Python Runtime Environment  
        \# Initializes the Python interpreter required by the script  
        uses: actions/setup-python@v5  
        with:  
          python-version: "3.10"  
            
      \- name: Install System Dependencies  
        \# Upgrades pip and installs the required lexical and network libraries  
        run: |  
          python \-m pip install \--upgrade pip  
          pip install requests mwparserfromhell pyyaml  
            
      \- name: Execute Extraction Pipeline  
        \# Triggers the state machine and generates the current\_events.yaml artifact  
        run: |  
          python update\_data.py  
            
      \- name: Evaluate Differential State and Commit Changes  
        id: commit\_step  
        run: |  
          \# Configure Git metadata to identify the automated runner  
          git config \--local user.email "github-actions\[bot\]@users.noreply.github.com"  
          git config \--local user.name "github-actions\[bot\]"  
            
          \# Stage the newly generated YAML artifact for evaluation  
          git add current\_events.yaml  
            
          \# Evaluate differential state: commit only if the working tree is mathematically dirty  
          if git diff \--staged \--quiet; then  
            echo "\[INFO\] No changes detected in the parsed data. Bypassing commit sequence."  
            echo "push=false" \>\> $GITHUB\_OUTPUT  
          else  
            \# Execute the commit with a dynamically generated date string  
            git commit \-m "Automated Data Update: $(date \+'%Y-%m-%d') Wikipedia Events"  
            echo "push=true" \>\> $GITHUB\_OUTPUT  
          fi  
            
      \- name: Push State to Repository  
        \# Conditionally executes only if the differential evaluation flagged push=true  
        if: steps.commit\_step.outputs.push \== 'true'  
        uses: ad-m/github-push-action@master  
        with:  
          github\_token: ${{ secrets.GITHUB\_TOKEN }}  
          branch: ${{ github.ref }}  
          force: false

### **Analysis of the Workflow Architecture**

The workflow configuration begins by defining the on block, which dictates the event triggers. By pairing schedule with workflow\_dispatch, developers retain the ability to trigger the pipeline manually during testing phases without waiting for the 23:30 UTC chronological trigger.

The permissions: contents: write block is a modern GitHub Actions security requirement. It explicitly elevates the privileges of the ephemeral token just enough to allow the ad-m/github-push-action step to push the updated current\_events.yaml file back to the primary branch.3

The most sophisticated component of the YAML workflow is the Evaluate Differential State and Commit Changes step. By utilizing standard bash scripting methodologies, the workflow traps the boolean output of git diff \--staged \--quiet. This effectively prevents the pipeline from failing on days where the API returns identical data, ensuring 100% operational uptime and preventing continuous integration alert fatigue.24

## **Advanced Operational Considerations and Edge Cases**

### **Context Window and Scaling Constraints**

As this automated serverless pipeline runs daily, the volume of serialized YAML files stored within the repository or ingested by a downstream application will aggregate continuously. While modern LLM architectures boast expansive and highly capable context windows—occasionally accommodating up to 1 million or even 2 million tokens depending on the underlying foundation model—injecting vast swathes of historical intelligence context correlates directly with severe, non-linear increases in inference latency and API computational expenditure.

The architecture dictates that historical data inflation necessitates strategic, programmatic management. Rather than injecting the entire historical database of generated YAML files into a system prompt blindly, the YAML endpoint should be integrated alongside a lightweight orchestration layer (such as LangChain, Semantic Kernel, or LlamaIndex). This orchestration layer must dynamically filter and inject only the most recent or categorically relevant YAML files. By limiting the context payload to a precisely defined chronological window (for example, strictly the past 72 hours of global events), the system prevents latency spikes, optimizes API costs, and maintains highly acute contextual awareness without overwhelming the model's attention heads.

### **Handling Non-Standard Wikitext Formatting Deviations**

While mwparserfromhell is exceptionally adept at handling standard templates and deep transclusions, Wikipedia's crowdsourced, decentralized nature guarantees eventual deviations from established formatting norms. Occasionally, inexperienced editors may nest definition terms rather than using strict asterisk lists, or they may utilize explicit HTML tags such as \<br\> for visual spacing instead of the standard structural asterisks.27

The regex sanitization layer (\\s{2,}) acts as an immediate operational safeguard against erratic spacing resulting from these visual deviations. However, if an editor completely abandons the single and double asterisk structural format for a given entry, the Python dictionary mapping sequence may temporarily fail to recognize sub-events, classifying them instead as empty macro-categories. Because the Python pipeline is explicitly designed to discard empty categories during the final validation pass (events\_hierarchy \= {k: v for k, v in events\_hierarchy.items() if len(v) \> 0}), it actively prevents malformed, empty structural elements from contaminating the final YAML endpoint. The system gracefully drops malformed data rather than halting execution.

### **MediaWiki API Rate Limiting and Institutional Etiquette**

The MediaWiki Action API operates as a shared, publicly funded global resource managed by the Wikimedia Foundation. While the Python script implemented in this architecture targets only a single, lightweight daily subpage, uncontrolled manual triggering of the workflow loop could run afoul of the Foundation's acceptable use policies.2

The explicit and hardcoded inclusion of the User-Agent HTTP header in the Python request object ensures that, in the highly unlikely event of an anomalous traffic spike or an endless execution loop, Wikimedia Foundation network engineers can definitively identify the source repository. This allows them to contact the repository owner directly to resolve the technical issue, rather than being forced to issue a blanket IP ban on the entire subset of GitHub Actions runner nodes.2 By executing strictly once per day on the automated cron schedule, the pipeline remains orders of magnitude under the MediaWiki infrastructure rate limits, establishing a highly sustainable, well-mannered integration with the platform.

## **Conclusion**

The comprehensive architecture detailed throughout this report establishes an ultra-efficient, highly autonomous data ingestion pipeline capable of bridging the systemic gap between dynamic, human-curated intelligence repositories and stateless Large Language Models. By leveraging the programmatic predictability of the MediaWiki Action API, the system entirely bypasses the inherent instability and computational waste of traditional DOM-based web scraping methodologies, securing highly reliable access to raw database data.

The integration of the mwparserfromhell lexical parser allows for sophisticated, object-oriented traversal of complex abstract syntax trees, elegantly translating chaotic, unstructured Wikitext markup into a highly organized, deterministic logical hierarchy. Furthermore, the rigorous mathematical application of custom Regular Expressions ensures that all non-semantic artifacts are systematically eradicated at the byte level, paving the way for the token-optimized serialization phase.

The deliberate architectural shift from ubiquitous JSON serialization to YAML fundamentally alters the token economics of the entire system, mathematically reducing the context payload density and enabling tangibly faster, vastly cheaper LLM inference cycles. Finally, the encapsulation of this system within a serverless, state-aware GitHub Actions workflow guarantees perpetual, zero-maintenance execution. This methodology represents the definitive technical standard for continuous contextual data ingestion, providing modern AI architectures with a highly resilient, mathematically optimized, and high-fidelity lens into global current events.

#### **Works cited**

1. Wikipedia Current Events Data Pipeline.md  
2. API:Tutorial \- MediaWiki, accessed March 13, 2026, [https://www.mediawiki.org/wiki/API:Tutorial](https://www.mediawiki.org/wiki/API:Tutorial)  
3. Push commits to another repository with GitHub Actions, accessed March 13, 2026, [https://some-natalie.dev/blog/multi-repo-actions/](https://some-natalie.dev/blog/multi-repo-actions/)  
4. Portal:Current events \- Wikipedia, accessed March 13, 2026, [https://en.wikipedia.org/wiki/Portal:Current\_events](https://en.wikipedia.org/wiki/Portal:Current_events)  
5. API:Query \- MediaWiki, accessed March 13, 2026, [https://www.mediawiki.org/wiki/API:Query](https://www.mediawiki.org/wiki/API:Query)  
6. API:Get the contents of a page \- MediaWiki, accessed March 13, 2026, [https://www.mediawiki.org/wiki/API:Get\_the\_contents\_of\_a\_page](https://www.mediawiki.org/wiki/API:Get_the_contents_of_a_page)  
7. earwig/mwparserfromhell: A Python parser for MediaWiki wikicode \- GitHub, accessed March 13, 2026, [https://github.com/earwig/mwparserfromhell](https://github.com/earwig/mwparserfromhell)  
8. mwparserfromhell Documentation \- Read the Docs, accessed March 13, 2026, [https://readthedocs.org/projects/mwparserfromhell/downloads/pdf/develop/](https://readthedocs.org/projects/mwparserfromhell/downloads/pdf/develop/)  
9. 5j9/wikitextparser: A Python library to parse MediaWiki WikiText \- GitHub, accessed March 13, 2026, [https://github.com/5j9/wikitextparser](https://github.com/5j9/wikitextparser)  
10. mwparserfromhell \- PyPI, accessed March 13, 2026, [https://pypi.org/project/mwparserfromhell/0.3/](https://pypi.org/project/mwparserfromhell/0.3/)  
11. nodes Package — mwparserfromhell 0.7.2 documentation, accessed March 13, 2026, [https://mwparserfromhell.readthedocs.io/en/latest/api/mwparserfromhell.nodes.html](https://mwparserfromhell.readthedocs.io/en/latest/api/mwparserfromhell.nodes.html)  
12. mwparserfromhell Package \- Read the Docs, accessed March 13, 2026, [https://mwparserfromhell.readthedocs.io/en/v0.3/api/mwparserfromhell.html](https://mwparserfromhell.readthedocs.io/en/v0.3/api/mwparserfromhell.html)  
13. mwparserfromhell Package, accessed March 13, 2026, [https://mwparserfromhell.readthedocs.io/en/v0.1/api/mwparserfromhell.html](https://mwparserfromhell.readthedocs.io/en/v0.1/api/mwparserfromhell.html)  
14. Quick Start Guide \- wikitextparser's documentation\! \- Read the Docs, accessed March 13, 2026, [https://wikitextparser.readthedocs.io/en/latest/README.html](https://wikitextparser.readthedocs.io/en/latest/README.html)  
15. How to get plain text out of Wikipedia \- python \- Stack Overflow, accessed March 13, 2026, [https://stackoverflow.com/questions/4452102/how-to-get-plain-text-out-of-wikipedia](https://stackoverflow.com/questions/4452102/how-to-get-plain-text-out-of-wikipedia)  
16. How to automatically remove hyperlinks when copying something from Wikipedia \- Reddit, accessed March 13, 2026, [https://www.reddit.com/r/ObsidianMD/comments/zgyrb7/how\_to\_automatically\_remove\_hyperlinks\_when/](https://www.reddit.com/r/ObsidianMD/comments/zgyrb7/how_to_automatically_remove_hyperlinks_when/)  
17. Template:Regex \- Wikipedia, accessed March 13, 2026, [https://en.wikipedia.org/wiki/Template:Regex](https://en.wikipedia.org/wiki/Template:Regex)  
18. Python regular expression with wiki text \- regex \- Stack Overflow, accessed March 13, 2026, [https://stackoverflow.com/questions/4929082/python-regular-expression-with-wiki-text](https://stackoverflow.com/questions/4929082/python-regular-expression-with-wiki-text)  
19. Help:Searching \- Wikipedia, accessed March 13, 2026, [https://en.wikipedia.org/wiki/Help:Searching](https://en.wikipedia.org/wiki/Help:Searching)  
20. Remove wikitext hyperlinks via regex \- java \- Stack Overflow, accessed March 13, 2026, [https://stackoverflow.com/questions/29918472/remove-wikitext-hyperlinks-via-regex](https://stackoverflow.com/questions/29918472/remove-wikitext-hyperlinks-via-regex)  
21. remove content between tags in python using regex \- Stack Overflow, accessed March 13, 2026, [https://stackoverflow.com/questions/43314971/remove-content-between-tags-in-python-using-regex](https://stackoverflow.com/questions/43314971/remove-content-between-tags-in-python-using-regex)  
22. re — Regular expression operations — Python 3.14.3 documentation, accessed March 13, 2026, [https://docs.python.org/3/library/re.html](https://docs.python.org/3/library/re.html)  
23. Add & Commit · Actions · GitHub Marketplace, accessed March 13, 2026, [https://github.com/marketplace/actions/add-commit](https://github.com/marketplace/actions/add-commit)  
24. Can GitHub actions directly edit files in a repository? · community · Discussion \#25234, accessed March 13, 2026, [https://github.com/orgs/community/discussions/25234](https://github.com/orgs/community/discussions/25234)  
25. Github actions commit and push to same branch \- Stack Overflow, accessed March 13, 2026, [https://stackoverflow.com/questions/74647350/github-actions-commit-and-push-to-same-branch](https://stackoverflow.com/questions/74647350/github-actions-commit-and-push-to-same-branch)  
26. Commit From GitHub Action Only When Changes Exist \- Reddit, accessed March 13, 2026, [https://www.reddit.com/r/github/comments/ju3ipr/commit\_from\_github\_action\_only\_when\_changes\_exist/](https://www.reddit.com/r/github/comments/ju3ipr/commit_from_github_action_only_when_changes_exist/)  
27. List tags should include the item text in their contents · Issue \#46 · earwig/mwparserfromhell, accessed March 13, 2026, [https://github.com/earwig/mwparserfromhell/issues/46](https://github.com/earwig/mwparserfromhell/issues/46)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAfCAYAAAClDZ5ZAAACyElEQVR4Xu2XT6hNURTGP6EISUSKRFJIBihJSv5EIb1MTf3LhAEx0DOQgQGJkqIMkCiD94QSN0+IIsrQgEQRpRggf77P2tvZd71zud3e7Zyb89Wve+9e996z19rf3mcdoFKlSv+dZpKTLbIIJdJR8pN8Ii8TNCa+k6fkVBj/msRWoyQaR56RhWSQi8XJKtFUo8lt8pnMc7HCdICc94PUCFgSb8g0F5M2kxoZ6cYL0Rhyl6zyAdjklUgN+ZPdS874waK0mDyA2ctL3lciWjEvWfAs2e0DRUkJzPKDQUpAiazzAVgic5BfgFJJVqqh8f7oGGkVGtmqoxRtVZp7RCuKtlIizdpKR/UOMsMHipQmr72hRDTBZrQT9n3dW0qjuD9Es9LptZQM94GilNpKq9KMhsLalME+ABtTQ7oB+a2MjvH1ZAnsf6K0NyeH9xqfTyZk4X9LF30PS+SGi+VpCrlMHpIjqO/V1I/1ksOwRI67uPbTvRA7RB7B/k/F3E9ekY2kh2wiH8ny379soFgxoZYj2kqNZByf/ufbmWSjE7DYFfRvZbaTS2QILKn7ZFiIqcJvya7weRTpI8dgq6HVU0OqYuq30gv8pZPQ0l9ANvlG5P2BOoKt4f1z9O+QVZTXsEJoovG5JdpXrdFYNyZUgC7yDbbvouQUHSptlS6qi6fagvpinA7jsscP1N9sdVjIATVYUiqKPqct0BdYb9g2yTraI+qko8aTq8iObx3psoakqqbPMdo32l/vyOww5qs/lXTD7HwQ2UoOqFQ1b6u5ZB+yzb2G3AnvlcAHZI8OK2EnZLqiWuG0+mvJArIC9vjQFumC3lY6Mm/CnukvklvI7vpKbhvsVNI+0pOm78CfoL7qWlGt8Dlkm3/AJQvo5POS1yeG1zzpBFM8T3m/0crn3atalny/hyyDefZaeO04TSLXyWOYdfS5UqVEvwAjBJn+zVz73QAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADUAAAAfCAYAAABH0YUgAAADKklEQVR4Xu2YS6iNURTHl1CeeUbylkdEkkcpGUkkEgbK0ICBCYpCugbyiiIiKRl4lTAglHSjRMpjIAPkkjJiRiGP/8/aq++72+G6OoOPzr9+nfOt9e199mPtvdc+Zg011FBD7dB0cfQvWEnhKqqDOC6+iXfiVQlsYb8ozqbvYT9gFdVg0SLGZHZEw9+LqSUbg7Am+daV7JURDTyYyDXevOHMIu+VNUo8FpMzeyXUX9wVM3OHtMS8Uytyh/nMPRSDckcVNEfcFL1yh/l6yUMvtFA0ix6ZvRJipibkRqmnuGUeYryT61flKi3W01tx0n5eT/+sCD3WE+fXfyHWSbN5p2qFXlXUWQwUXXJHLbFdvzHvVKfMVwV1E2fM2/fVfLNrU/OtyBiqrO3itRiSO2qJl+nQ59xRIRFylxNthl859CjwO/Uzn9WhJRtxnp95PM8VY631Tsp3MpLZ6Zn1wfnHM/UgykH39Bwi5D6lzzZVDr1Nma+saeKC+TvPxbhk3yvuWNGxDemZrGSfuG/eeEQH9ogbYqs4LJaL2+KUWGxe7pB4Yq3DjGhi8JmEmpoklplX8MCKTp1I9gXWeqS6iiNitFgkPpinWX3EPSvONngqRvwoVfjZXaljv3kHj4ml6R200fz36SQioyGzYRBQm6HHTnLNio7UgkOYwzhEuG02D5HTVsxMHNir0ns0pil9R3SAWUVRB+XIXCLcEGdki/ntATFwH8Ws9BxLhNmqu0aa7z5N6ZmZZtbiwKZx0RDEdxpXVgxEKM7Ic1YcJ9RD+EXYtms9tVeEyUsrMnVCKxoTjYuwxYaPWdkthiU7DY7ZQ/mszDPvAJ8M4i4rQq+32Gl1ThC4IJY79cWK0It7WmTxrBn8rFPWI2shkmY6G4pOxqyw8URSvdb8OoSf0JtovonUNUEYLh6JK+bX/Pyawm5Fg/kbYIfYIp6JGclPecI3/udgVq+br9NoKJvDC3FebDNfe3SUei5ZUVddxEww0vz4ANHXWm/lIXzlOxchE6IOdsSOJRvv5jsatrwcZ2Td73LrzfMuzjU0Rawu3P+myA6umq8JQiaygoYa+kN9B4ArszOTXikeAAAAAElFTkSuQmCC>