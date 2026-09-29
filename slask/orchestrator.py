import json
import os


def run_pipeline():
  print("=== STARTING MULTI-AGENT STEEL R&D PIPELINE ===")

  # --- STEP 1: Agent 1 (Baseline & Domain Classification) ---
  company_name = "SSAB"  # Example target
  url = "https://www.ssab.com"
  print(
      f"\n[Step 1] Running Agent 1: Crawling {company_name} ({url}) for domain"
      " classification..."
  )

  # Mock Agent 1 output (domains discovered)
  agent_1_output = {
      "company": company_name,
      "domains": [
          {
              "domain_id": 1,
              "name": "Wear-Resistant Steels",
              "grades": ["Hardox 400", "Hardox 500"],
          },
          {
              "domain_id": 2,
              "name": "High-Strength Structural Steels",
              "grades": ["Strenx 700", "Strenx 960"],
          },
      ],
  }

  os.makedirs("temp_data", exist_ok=True)
  with open("temp_data/agent_1_baseline.json", "w") as f:
    json.dump(agent_1_output, f, indent=2)

  print("\n--- AGENT 1 REPORT SUMMARY ---")
  for d in agent_1_output["domains"]:
    print(f"Domain ID {d['domain_id']}: {d['name']} ({len(d['grades'])} grades)")

  # --- HUMAN-IN-THE-LOOP INTERMISSION ---
  print(
      "\n🛑 [Human-in-the-Loop] Review domains above and select target domain."
  )
  # For automation demonstration, we select Domain 1 programmatically
  selected_domain = "Wear-Resistant Steels"
  print(f"-> Human selected domain for deep-dive: '{selected_domain}'")

  # --- STEP 2: Agent 2 (Frontier Research) ---
  print(
      f"\n[Step 2] Running Agent 2: Scanning global literature for '{selected_domain}'..."
  )
  # Agent 2 output is saved as agent_2_report.json (handled in Agent X script setup)

  # --- STEP X: Agent X (Simulation & Extrapolation) ---
  print(
      "\n[Step X] Running Agent X: Isolating positive trends and extrapolating"
      " virtual alloys..."
  )
  os.system("python agent_x_simulator.py")

  # --- STEP 3: Agent 3 (Gap Analysis & TRIZ) ---
  print(
      "\n[Step 3] Running Agent 3: Performing gap analysis and TRIZ resolution..."
  )
  os.system("python agent_3_cto.py")

  print(
      "\n=== PIPELINE EXECUTION COMPLETE. CHECK 'temp_data/' FOR REPORTS ==="
  )


if __name__ == "__main__":
  run_pipeline()