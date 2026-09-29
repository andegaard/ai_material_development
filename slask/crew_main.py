import os
from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

# Läs in miljövariabler från .env
load_dotenv()

if not os.getenv("ANTHROPIC_API_KEY"):
  raise ValueError(
      "Hittade ingen ANTHROPIC_API_KEY! Kontrollera din .env-fil i rotmappen."
  )


# Hjälpfunktion för att läsa in fylliga instruktioner från instructions/-mappen
def load_instruction_file(filename):
  path = os.path.join("instructions", filename)
  if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
      return f.read().strip()
  raise FileNotFoundError(
      f"Kunde inte hitta instruktionsfilen: {path}. Kontrollera att den ligger"
      " i mappen 'instructions'."
  )


# Definiera LLM-instanser med anpassad temperatur för olika uppgifter
llm_sonnet_precise = ChatAnthropic(
    model="claude-3-5-sonnet-20241022", temperature=0.1
)
llm_sonnet_creative = ChatAnthropic(
    model="claude-3-5-sonnet-20241022", temperature=0.3
)
llm_sonnet_deterministic = ChatAnthropic(
    model="claude-3-5-sonnet-20241022", temperature=0.0
)
llm_opus_strategy = ChatAnthropic(
    model="claude-3-opus-20240229", temperature=0.4
)

# --- SKAPA AGENTER MED LADDADE TEXTER ---

market_intelligence_agent = Agent(
    role="Market Intelligence & Portfolio Architect",
    goal=(
        "Autonomously map a target company's public material portfolio and"
        " categorize them into distinguishable functional domains."
    ),
    backstory=load_instruction_file("market_instructions.md"),
    llm=llm_sonnet_precise,
    verbose=True,
)

metallurgical_researcher_agent = Agent(
    role="Academic Metallurgist & Trend Analyst",
    goal=(
        "Scan global scientific literature and patents for cutting-edge"
        " breakthroughs within a specific steel domain."
    ),
    backstory=load_instruction_file("metallurgical_instructions.md"),
    llm=llm_sonnet_creative,
    verbose=True,
)

thermodynamic_simulator_agent = Agent(
    role="Computational Materials Scientist",
    goal=(
        "Isolate positive performance trends and extrapolate beyond published"
        " limits to design virtual alloy recipes."
    ),
    backstory=load_instruction_file("thermodynamic_instructions.md"),
    llm=llm_sonnet_deterministic,
    verbose=True,
)

cto_strategy_agent = Agent(
    role="Chief Technology Officer & Innovation Strategist",
    goal=(
        "Bridge manufacturing capabilities and simulated recipes using TRIZ"
        " inventive principles."
    ),
    backstory=load_instruction_file("cto_instructions.md"),
    llm=llm_opus_strategy,
    verbose=True,
)

ip_sustainability_agent = Agent(
    role="Patent Attorney & Sustainability Engineer",
    goal=(
        "Audit proposed alloy designs for Freedom-to-Operate (FTO) patent risks"
        " and carbon footprint viability."
    ),
    backstory=load_instruction_file("ip_audit_instructions.md"),
    llm=llm_sonnet_precise,
    verbose=True,
)


# --- HUVUDFÖRLOPP ---
def run_pipeline():
  company_name = "SSAB"
  company_url = "https://www.ssab.com"

  print(f"\n=== STARTAR CREWAI-PIPELINE FÖR {company_name} ===")

  # Steg 1: Agent 1 kartlägger portföljen
  task_baseline = Task(
      description=(
          f"Crawl public web sources for {company_name} at {company_url}. Map"
          " out their material portfolio and group them into distinct"
          " functional domains. Save output."
      ),
      expected_output=(
          "A structured market baseline report containing distinct steel"
          " domains and key grade examples."
      ),
      agent=market_intelligence_agent,
      output_file="temp_agent_1_baseline.md",
  )

  Crew(
      agents=[market_intelligence_agent],
      tasks=[task_baseline],
      process=Process.sequential,
  ).kickoff()

  # Mänsklig paus för att välja spår
  print(
      "\n"
      "------------------------------------------------------------------"
  )
  print(
      "🛑 [MANUELLT VAL] Läs filen 'temp_agent_1_baseline.md' i din mapp."
  )
  print(
      "------------------------------------------------------------------"
  )
  selected_domain = input(
      "Vilken specifik ståldomän vill du att Agent 2 ska forska djupare i? (t.ex."
      " Wear-Resistant Steels): "
  )

  # Steg 2, X, 3 (Kedjan körs vidare baserat på ditt val)
  task_frontier = Task(
      description=(
          f"Perform an open-ended frontier research scan focusing exclusively"
          f" on the selected domain: '{selected_domain}'. Identify cutting-edge"
          " mechanisms and microstructural phases."
      ),
      expected_output="Frontier Research Report detailing breakthrough mechanisms.",
      agent=metallurgical_researcher_agent,
      output_file="temp_agent_2_research.md",
  )

  task_sim = Task(
      description=(
          "Analyze the Frontier Research Report. Isolate positive performance"
          " trends and extrapolate 15% beyond published limits to formulate 3"
          " virtual prototype alloy recipes."
      ),
      expected_output="Thermodynamic Simulation & Extrapolated Alloy Recipe Report.",
      agent=thermodynamic_simulator_agent,
      output_file="temp_agent_x_simulation.md",
  )

  task_gap = Task(
      description=(
          f"Compare {company_name}'s baseline portfolio against virtual"
          " prototype recipes. Apply TRIZ inventive principles to resolve"
          " technical contradictions and create a 3-step R&D roadmap."
      ),
      expected_output="Strategic Innovation & Implementation Roadmap.",
      agent=cto_strategy_agent,
      output_file="agent_3_roadmap.md",
  )

  Crew(
      agents=[
          metallurgical_researcher_agent,
          thermodynamic_simulator_agent,
          cto_strategy_agent,
      ],
      tasks=[task_frontier, task_sim, task_gap],
      process=Process.sequential,
  ).kickoff()

  # Steg 4: IP & Hållbarhet
  task_audit = Task(
      description=(
          "Audit the final R&D roadmap and alloy recipes for Freedom-to-Operate"
          " (FTO) patent conflicts and carbon footprint impacts. Issue a final"
          " feasibility score."
      ),
      expected_output="Final IP & Sustainability Risk Audit report.",
      agent=ip_sustainability_agent,
      output_file="agent_4_audit.md",
  )

  Crew(
      agents=[ip_sustainability_agent],
      tasks=[task_audit],
      process=Process.sequential,
  ).kickoff()

  print(
      "\n=== KLART! Alla rapporter har sparats som .md-filer i projektmappen. ==="
  )


if __name__ == "__main__":
  run_pipeline()