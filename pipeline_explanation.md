# Pipeline Explanation for manual_agent_demo.py

This document provides a comprehensive explanation of the pipeline execution flow in `manual_agent_demo.py`, organized by chronological order of operations rather than file generation order. The pipeline follows a structured approach to Federal Reserve policy research with three main agents: Macro Analyst → Fact Checker → Executive Writer.

## Overview

The pipeline operates in six main phases:
1. **Initialization** - Setting up the environment and metadata
2. **Search & Data Collection** - Gathering source information (very early in the process)
3. **Macro Analysis** - Processing sources and generating initial analysis
4. **Fact Checking** - Validating the analysis against collected sources
5. **Executive Writing** - Synthesizing all information into a final brief
6. **Finalization** - Creating debug summaries and consolidating data

---

## 1. Initialization Phase

### 1.1 Manifest File Creation
- **File**: `{RUN_ID}.manifest.json`
- **Function**: `write_manifest()` in `run_logging.py`
- **Timing**: Very first operation in the script
- **Purpose**: Captures system metadata for reproducibility
- **Content**:
  - Run ID (UUID-based)
  - Git revision
  - Python version and platform
  - Environment variables with `FEDRATE_` prefix
  - Timestamp in ISO format
  - Timezone information

### 1.2 Environment & Tool Checks
- **Function**: `environment_check()` and `test_tool_availability()`
- **Timing**: After manifest creation
- **Purpose**: Verify system setup and HTTP client functionality
- **Operations**:
  - Logs Python version
  - Tests HTTP client with a simple `httpbin.org` call
  - Validates caching mechanism
  - Logs success/failure of tool availability

---

## 2. Search & Data Collection Phase

### 2.1 Search Operations (EARLY STAGE)
- **Function**: `search_with_fallback()` in `manual_agent_demo.py`
- **Timing**: First substantive work in the pipeline
- **Purpose**: Gather source information for macro analysis
- **Operations**:
  - Executes two predefined queries:
    - "Federal Reserve FOMC Jackson Hole meeting July 30, 2025"
    - "Jerome Powell Fed funds rate July 30, 2025"
  - Uses provider rotation (Brave Search → DuckDuckGo)
  - Implements caching with retry logic
  - Limits results to 6 per query (configurable via `TOP_SERP_PER_QUERY`)

### 2.2 Source Recording
- **Files**: 
  - `{RUN_ID}.sources.final.jsonl` (appended to during search)
  - `{RUN_ID}.sources.raw.json` (consolidated at the end)
- **Function**: `record_source_jsonl()` in `io_clients.py`
- **Timing**: During search operations (very early)
- **Purpose**: Track provenance of all sources
- **Content per record**:
  - Timestamp
  - Search query
  - Title
  - URL
  - Snippet (from search results)
  - Provider (brave or ddg)

### 2.3 Search Result Processing
- **Function**: `SerpRecorder.record_query_results()` in `serp_utils.py`
- **Purpose**: Deduplicate and organize search results
- **Operations**:
  - Removes duplicate URLs across queries
  - Maintains order of discovery
  - Limits total results to 20 (configurable via `run_cap`)

---

## 3. Macro Analysis Phase

### 3.1 Macro Analyst LLM Call
- **File**: `{RUN_ID}.MacroAnalyst.{timestamp}.llm.json`
- **Function**: `macro_analyst()` in `manual_agent_demo.py`
- **Model**: `z-ai/glm-4.5-air:free`
- **Purpose**: Generate initial analysis of Federal Reserve policy
- **Operations**:
  - Constructs RAG prompt with collected sources
  - Sends structured prompt to LLM with:
    - Current date context
    - Federal Reserve policy stance information
    - Market-implied rate path
    - Key FOMC messaging
    - Policy drivers
    - Consensus views
  - Includes system instruction to use ONLY provided sources
  - Saves complete LLM call (request/response) for audit

### 3.2 Macro Notes Generation
- **File**: `{RUN_ID}.macro.notes.md`
- **Function**: `RUN_FILES.macro_notes()` in `run_files.py`
- **Purpose**: Save the macro analyst's textual response
- **Content**:
  - One-paragraph bottom line summary
  - 3-5 bullet points on key drivers
  - Inline citations using [#] indices matching source list

### 3.3 Source Formatting for Analysis
- **Function**: Hard-coded sources block in `macro_analyst()`
- **Purpose**: Provide structured context to the LLM
- **Note**: Currently uses placeholder content rather than actual search results

---

## 4. Fact Checking Phase

### 4.1 Source Loading and Formatting
- **Function**: `load_and_format_sources()` in `manual_agent_demo.py`
- **Purpose**: Prepare collected sources for fact checking
- **Operations**:
  - Loads all records from `{RUN_ID}.sources.final.jsonl`
  - Groups sources by original query
  - Formats as structured text for LLM consumption

### 4.2 Fact Checker LLM Call
- **File**: `{RUN_ID}.factcheck.json` (contains LLM response + flags)
- **Function**: `fact_checker()` in `manual_agent_demo.py`
- **Model**: `moonshotai/kimi-k2:free`
- **Purpose**: Validate macro analyst's claims against sources
- **Operations**:
  - Sends structured prompt with:
    - Macro analyst's notes
    - Formatted source collection
    - Instructions for validation
  - Requests claim-by-claim validation

### 4.3 Source Assessment
- **Function**: `assess_source_completeness()` in `manual_agent_demo.py`
- **Purpose**: Evaluate if collected sources are adequate
- **Current Logic**: Simple heuristic (has sources + has content = sufficient)
- **Returns**: List of flags (e.g., "sources_missing", "sources_incomplete")

### 4.4 Fact Check Results
- **File**: `{RUN_ID}.factcheck.json`
- **Content**:
  - Fact checker's textual response
  - Assessment flags
  - JSON structure with validation findings

### 4.5 FACT CHECKING LIMITATIONS
**Current Limitations:**
1. **Surface-level validation only**: The fact checker only validates against search metadata (titles, URLs, snippets) rather than actual content
2. **No content scraping**: The fact checker never makes HTTP requests to fetch the full content of source URLs
3. **Snippet dependency**: Validation quality is limited to what's captured in search engine snippets, which may not represent the full article content
4. **No source depth**: Cannot detect if search snippets accurately reflect the source material or if important context is missing
5. **Metadata-only verification**: Can only check consistency between macro notes and search snippets, not factual accuracy against source content

**Implications:**
- Fact checking is limited to surface-level consistency rather than deep content validation
- May miss nuanced claims that aren't reflected in search snippets
- Cannot verify information that exists in the full article but not in the excerpt
- Quality depends entirely on the comprehensiveness of search results

---

## 5. Executive Writing Phase

### 5.1 Executive Writer LLM Call
- **File**: `{RUN_ID}.ExecutiveWriter.{timestamp}.llm.json`
- **Function**: `executive_writer()` in `manual_agent_demo.py`
- **Model**: `openai/gpt-oss-20b:free`
- **Purpose**: Synthesize all information into a concise executive brief
- **Operations**:
  - Combines macro analyst notes, fact check results, and flags
  - Generates structured brief with methodology section
  - Includes limitations and source information

### 5.2 Brief Generation
- **File**: `{RUN_ID}.brief.md`
- **Function**: `RUN_FILES.brief()` in `run_files.py`
- **Content**:
  - Executive summary of Federal Reserve policy
  - Methodology box explaining approach
  - Source attribution
  - Limitations disclosure

---

## 6. Finalization Phase

### 6.1 Source File Consolidation
- **File**: `{RUN_ID}.sources.raw.json`
- **Function**: Final source data consolidation in `main()`
- **Purpose**: Create a consolidated JSON version of all collected sources
- **Operations**:
  - Loads all records from JSONL file
  - Writes as formatted JSON for easier reading

### 6.2 Debug Information
- **File**: `{RUN_ID}.debug.json`
- **Function**: Debug summary in `main()`
- **Purpose**: Provide pipeline execution summary
- **Content**:
  - Number of search results found
  - Paths to source files
  - Error flags from fact checking
  - Performance metrics

---

## File Summary (All Artifacts)

### Core Pipeline Files
1. **`{RUN_ID}.manifest.json`** - System metadata and environment snapshot
2. **`{RUN_ID}.sources.final.jsonl`** - Append-only source records (created during search)
3. **`{RUN_ID}.sources.raw.json`** - Consolidated source data (created at end)
4. **`{RUN_ID}.macro.notes.md`** - Macro analyst's analysis
5. **`{RUN_ID}.factcheck.json`** - Fact check results and validation flags
6. **`{RUN_ID}.brief.md`** - Final executive brief

### LLM Interaction Files
7. **`{RUN_ID}.MacroAnalyst.{timestamp}.llm.json`** - Complete Macro Analyst LLM call
8. **`{RUN_ID}.ExecutiveWriter.{timestamp}.llm.json`** - Complete Executive Writer LLM call

### Debug Files
9. **`{RUN_ID}.debug.json`** - Pipeline execution summary and statistics

## Key Observations

1. **Search Happens Early**: Despite JSON files being written later, search operations are the first substantive work in the pipeline
2. **Source Integration**: Search results are integral to macro notes generation, even if the final JSON files are created later
3. **Fact Checking Scope**: Current fact checking is limited to metadata validation rather than deep content verification
4. **File Generation Order**: Files are not generated in chronological order of operations (e.g., search results are collected early but written to JSON at the end)
5. **Audit Trail**: Complete LLM interactions are saved for transparency and reproducibility

## Pipeline Flow Visualization

```
Initialization → Search & Collection → Macro Analysis → Fact Checking → Executive Writing → Finalization
     ↓                ↓                  ↓              ↓                ↓              ↓
Manifest        Source Records      Macro Notes    Fact Check Results  Executive Brief  Debug Info
Environment    (JSONL + Raw JSON)   + LLM Call     + Flags             + LLM Call       + Summary
Checks          (Early Collection)   (Early)        (Mid)               (Late)          (End)
```

This pipeline emphasizes reproducibility, auditability, and structured data collection while maintaining a clear separation of concerns between the three specialized agents.
