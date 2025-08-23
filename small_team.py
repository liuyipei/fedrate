# small_team.py
import os

# Optional but recommended headers for OpenRouter attribution:
os.environ["OPENROUTER_REFERRER"] = "http://localhost"   # any identifying URL/app
os.environ["OPENROUTER_TITLE"] = "Fed Rate Research Crew"

# ---- CrewAI + Tools ----
from crewai import Agent, Task, Crew, Process
from crewai import LLM

# ---------- LLMs (OpenRouter via LiteLLM under the hood) ----------
# deepseek/deepseek-chat-v3.1
# openai/gpt-oss-20b:free
# z-ai/glm-4.5-air:free
# moonshotai/kimi-k2:free
# openai/gpt-5-mini
# openrouter/anthropic/claude-3.5-sonnet
# openrouter/anthropic/claude-3.5-sonnet
ANALYST_MODEL = "openrouter/openai/gpt-oss-20b:free"
FACTCHECK_MODEL = "openrouter/glm-4.5-air:free"
WRITER_MODEL = "openrouter/moonshotai/kimi-k2:free"


analyst_llm = LLM(
    model=ANALYST_MODEL,
    # These go straight to LiteLLM; point to OpenRouter
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

factcheck_llm = LLM(
    model=FACTCHECK_MODEL,
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

writer_llm = LLM(
    model=WRITER_MODEL,
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# ---------- Tools (imported from agent_tools.py) ----------
from agent_tools import search, scraper



# ---------- Agents ----------
analyst = Agent(
    role="Macro Analyst",
    goal=("Identify the likely trajectory of the Federal Reserve policy rate "
          "over the next 12 months; gather market-implied probabilities, "
          "recent FOMC communications, and major sell-side views."),
    backstory=("You’re a careful macro researcher. You compare CME FedWatch, "
               "latest FOMC statements/minutes, SEP/dot plot summaries, and "
               "trusted outlets (WSJ, Bloomberg, FT)."),
    llm=analyst_llm,
    tools=[search, scraper],
    allow_delegation=False,
    verbose=True,
)

fact_checker = Agent(
    role="Fact Checker",
    goal=("Validate all numeric claims, dates, and quotes. Cross-check at least "
          "two independent reputable sources and flag discrepancies."),
    backstory=("Skeptical auditor who only approves facts with clear citations."),
    llm=factcheck_llm,
    tools=[search, scraper],
    allow_delegation=False,
    verbose=True,
)

writer = Agent(
    role="Executive Writer",
    goal=("Produce a crisp, cited brief with: (1) summary view, (2) 3–5 drivers, "
          "(3) risks & alternative scenarios, (4) near-term timeline. "
          "Use bullet points and include links."),
    backstory=("You write for senior decision-makers, focusing on clarity and signal."),
    llm=writer_llm,
    tools=[],
    allow_delegation=False,
    verbose=True,
)

# ---------- Tasks ----------
scope_task = Task(
    description=(
        "Define the concrete questions to answer:\n"
        "- What is today's date? All questions are meant to be forward looking into the future.\n"
        "- Current effective fed funds range and stance.\n"
        "- Market-implied path next 2–4 FOMC meetings (CME FedWatch).\n"
        "- Most recent FOMC statement/minutes + SEP/dot plot takeaways.\n"
        "- Key drivers (inflation trend, labor, growth, financial conditions).\n"
        "- Consensus from 2–3 reputable research notes or news outlets.\n"
        "Return a bullet list + preliminary links for each item."
    ),
    expected_output="A bullet list of questions + initial sources/links.",
    agent=analyst,
)

research_task = Task(
    description=(
        "Collect data and quotes with URLs: "
        "1) Market-implied probabilities for the next 2–4 meetings; "
        "2) Latest FOMC statement or minutes summary; "
        "3) SEP/dot plot highlights (if recent); "
        "4) Notable sell-side or major-media views; "
        "5) A short timeline of upcoming macro releases that could shift odds."
    ),
    expected_output="Structured notes with bullets, URLs inline, and dated facts.",
    agent=analyst,
)

factcheck_task = Task(
    description=(
        "Validate all numbers/dates/quotes from research_task. "
        "For each claim: provide at least two links or flag as uncertain. "
        "Create a 'Fact Table' with columns: Claim | Source A | Source B | Status."
    ),
    expected_output="A Fact Table with statuses (Confirmed/Disputed/Unclear).",
    agent=fact_checker,
)

write_task = Task(
    description=(
        "Write an executive brief (≤600 words) with sections:\n"
        "• Bottom line (1–2 sentences)\n"
        "• Base case path (next 12 months) with bullets\n"
        "• Key drivers (3–5 bullets)\n"
        "• Risks / alt scenarios (2–3)\n"
        "• Near-term watch items & dates\n"
        "Include inline links to sources vetted in the Fact Table."
    ),
    expected_output="Polished brief in Markdown with links.",
    agent=writer,
    context=[research_task, factcheck_task],  # use validated content
)

# ---------- Orchestration ----------
crew = Crew(
    agents=[analyst, fact_checker, writer],
    tasks=[scope_task, research_task, factcheck_task, write_task],
    process=Process.sequential,  # simple linear baton-pass
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()
    print("\n\n===== EXECUTIVE BRIEF =====\n")
    print(result)
