"""
peer_reviewer.py — Adversarial peer-review specialist.

Runs AFTER all regular specialists complete, receives their full findings as
input, and produces a structured critique. Does not generate new risks — it
attacks existing ones: redundant claims, unsupported mechanisms, overconfident
severity ratings.

Toggled by enable_peer_review=True in the simulation request.
"""

import json


async def run_peer_review(
    client,
    asst_id: str,
    policy_text: str,
    specialist_results: list[dict],
    specialist_risks: list[dict],
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o",
) -> dict:
    """Run the adversarial peer-review pass over specialist findings.

    Returns a dict with keys:
      - critiques: list of per-risk critique objects
      - panel_summary: str
    """
    n_specialists = len(specialist_results)

    # Build a compact risk list for the prompt
    risks_for_prompt = [
        {
            "risk_index": i + 1,
            "specialist": r.get("source", "unknown"),
            "risk": r.get("risk", ""),
            "mechanism": r.get("mechanism", ""),
            "severity": r.get("severity", 1),
            "category": r.get("category", ""),
            "most_exposed": r.get("most_exposed", ""),
            "historical_precedent": r.get("historical_precedent") or "none cited",
        }
        for i, r in enumerate(specialist_risks)
    ]
    risks_json = json.dumps(risks_for_prompt, indent=2)

    prompt = f"""You are a peer reviewer for a Canadian policy risk analysis. Your job is NOT to identify new risks — it is to critically examine the risks already identified by {n_specialists} specialists and flag weaknesses.

Policy: {policy_text}

Specialist findings to review:
{risks_json}

YOUR PRIMARY TASK — CROSS-SPECIALIST DUPLICATION HUNT:
Before assessing individual risk quality, scan ALL findings together and identify any group of risks that share the same underlying mechanism and affected population, just described in different words by different specialists. This is the most common quality failure in multi-specialist panels.

Red flags for duplication:
- Multiple findings about "exclusion of vulnerable groups" or "access barriers" from different specialists
- Multiple findings about "compliance costs" affecting the same business type
- Multiple findings about the same demographic (e.g. Indigenous youth, low-income households) facing the same structural barrier
- Two risks where merging them into one sentence loses no information

When you find duplicates: mark all but the MOST SPECIFIC one as "duplicate", pointing to the best version via duplicate_of.

THEN for each non-duplicate finding assess:
1. LENS DISCIPLINE: Does this finding actually reflect the specialist's named expertise? A "Parental Controls Analyst" who returns a generic equity finding has not done their job. A "Supply Chain Analyst" who returns a cost finding instead of a logistics/distribution finding has drifted from their lens. Flag lens drift as mechanism_invalid.
2. MECHANISM VALIDITY: Is the causal chain from policy action to harm actually valid and specific?
3. SEVERITY CALIBRATION: Is HIGH defensible with specific population data, or is this a MEDIUM dressed up?
4. TIMELINE COHERENCE: Does the stated timeline match the mechanism speed?

Return only valid JSON with no markdown:
{{
  "critiques": [
    {{
      "risk_index": 1,
      "risk_title": "copy from input",
      "verdict": "valid",
      "severity_adjustment": null,
      "duplicate_of": null,
      "critique": "2-3 sentences. Be specific — name the mechanism flaw, lens drift, or duplication.",
      "suggested_revision": null
    }}
  ],
  "panel_summary": "2-3 sentences: overall assessment — how many findings are genuinely distinct, what cross-specialist convergence patterns exist, what the panel missed"
}}

verdict must be one of: valid | overstated | understated | duplicate | mechanism_invalid
severity_adjustment must be one of: null | "upgrade" | "downgrade"
duplicate_of is null or the risk_index of the best surviving version of this risk
suggested_revision is null or a one-sentence reframe that restores lens specificity if the mechanism is salvageable"""

    try:
        thread = await client.create_thread(asst_id)
        response = await client.add_message(
            thread_id=thread.thread_id,
            content=prompt,
            llm_provider=llm_provider,
            model_name=llm_model,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return {
            "critiques": result.get("critiques", []),
            "panel_summary": result.get("panel_summary", ""),
        }
    except Exception as e:
        return {
            "critiques": [],
            "panel_summary": f"[peer review error: {e}]",
        }


def build_peer_review_block(peer_review: dict) -> str:
    """Build a text block for injection into the coordinator prompt."""
    if not peer_review or not peer_review.get("critiques"):
        return ""

    lines = ["PEER REVIEW CRITIQUE (adversarial specialist — treat as binding input):"]
    lines.append(f"Panel summary: {peer_review.get('panel_summary', '')}")
    lines.append("")

    for c in peer_review["critiques"]:
        verdict = c.get("verdict", "valid")
        adj = c.get("severity_adjustment")
        dup = c.get("duplicate_of")
        lines.append(
            f"  Risk {c.get('risk_index')} [{c.get('risk_title', '')}]: "
            f"verdict={verdict}"
            + (f" | severity_adjustment={adj}" if adj else "")
            + (f" | duplicate_of=risk_{dup}" if dup else "")
        )
        lines.append(f"    Critique: {c.get('critique', '')}")
        if c.get("suggested_revision"):
            lines.append(f"    Suggested revision: {c['suggested_revision']}")

    lines.append("")
    lines.append(
        "COORDINATOR INSTRUCTION: Where peer review marks a risk as 'duplicate', merge it with its twin. "
        "Where marked 'overstated', downgrade severity unless you have independent confirmation. "
        "Where marked 'mechanism_invalid', flag the risk as low-confidence unless validators confirmed it. "
        "Do not wholesale discard any risk — use critique to calibrate, not eliminate."
    )
    return "\n".join(lines)
