# Responsible & ethical AI practices

| Concern | What this project does |
|---|---|
| **Hallucination** | The assistant is *grounded*: it only reports numbers computed from the database and shows them as “sources”. Unknown questions get “I can’t answer that from the stored data — I won’t guess”. |
| **Invented causes** | Alerts and answers state that readings cannot reveal the cause; they list typical checks only. |
| **Transparency** | UI labels demo data as simulated everywhere; the detector’s rules are documented and visible in code. |
| **Privacy** | No personal or plant data is sent to any external AI service. Passwords are hashed (scrypt), never logged. |
| **Human in the loop** | Alerts are advisory; an administrator acknowledges them. No automatic control actions. |
| **Fairness / bias** | No user profiling or scoring of people. Emission factor (0.71 kg CO₂/kWh) is an explicit, labelled assumption. |
| **Accountability** | Audit log records logins, asset changes, acknowledgements, ingests and demo actions. |
| **AI in development** | AI-generated code was run, tested, reviewed and mutation-checked; defects are logged in `AI_WORKFLOW.md`. |

**If you add an external LLM later:** send only aggregated numbers (never credentials), keep the grounding step, show sources, set a timeout with fallback to the rule-based answer, and add tests with the provider mocked.
