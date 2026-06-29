"""
Fiscal scorecard: extracts and synthesizes dollar figures from policy text and
specialist analysis into a structured top-line balance sheet.

Returns None if the policy has no material fiscal commitments (e.g. regulatory-only
policies). This is intentional — don't fabricate numbers that aren't there.
"""

import json
import re


_FISCAL_PROMPT = """You are a Canadian fiscal analyst. Your task is to extract and synthesize ONLY the dollar figures explicitly stated or directly implied by the policy text and specialist analysis below. Do not invent numbers.

POLICY TEXT:
{policy_text}

SPECIALIST FINDINGS (fiscal-relevant excerpts):
{specialist_excerpt}

─────────────────────────────────────────────────────
INSTRUCTIONS:
1. Extract every dollar amount, percentage, or fiscal commitment mentioned.
   CRITICAL: Do NOT treat per-unit rates (e.g. "$80/tonne", "$15/hour", "$500/month subsidy per person") as total revenue or spend figures. A per-unit rate is NOT a total — it is a rate. List it under "revenue_sources" or "committed_spend" with amount_cad=0 and unit="per unit rate" and describe the rate in the item field. Only record a non-zero amount_cad when a total dollar figure is explicitly stated.
2. Classify each as: committed_spend (government outlay), revenue_source (levy/tax/fee income), or transfer (redistribution — neither net spend nor net revenue).
3. Sum them into a top-line balance. Use the stated implementation window. If no window is stated, use "not specified."
4. If the policy is purely regulatory with NO fiscal commitments, return null for all fields and set "has_fiscal_content": false.
5. Be honest about uncertainty. If a figure is a projection or estimate, say so.
6. Do NOT extrapolate beyond what is stated. If a cost is implied but not quantified, list it under "unquantified_items" as a string, not a number.

Return exactly this JSON (no markdown fences):
{{
  "has_fiscal_content": true,
  "implementation_window": "e.g. 5 years (2025–2030) or 'not specified'",
  "committed_spend": [
    {{"item": "description", "amount_cad": 0, "unit": "million|billion|per year|total", "certainty": "stated|estimated|implied", "source": "policy text or specialist name"}}
  ],
  "revenue_sources": [
    {{"item": "description", "amount_cad": 0, "unit": "million|billion|per year|total", "certainty": "stated|estimated|implied", "source": "policy text or specialist name"}}
  ],
  "transfers": [
    {{"item": "description", "amount_cad": 0, "unit": "million|billion|per year|total", "note": "who pays, who receives"}}
  ],
  "total_committed_spend_cad": 0,
  "total_revenue_cad": 0,
  "net_fiscal_position_cad": 0,
  "net_position_label": "net cost|net revenue|revenue-neutral|uncertain",
  "unquantified_items": ["list of costs/revenues mentioned but not given dollar figures"],
  "caveats": "1-2 sentences on key uncertainties in these numbers"
}}

If has_fiscal_content is false, return:
{{"has_fiscal_content": false}}
"""


def _extract_specialist_fiscal(specialist_results: list[dict], max_chars: int = 3000) -> str:
    """Pull fiscal-relevant text from specialist outputs."""
    fiscal_kw = ["$", "billion", "million", "cost", "revenue", "levy", "tax", "fund",
                 "budget", "fiscal", "spend", "grant", "subsidy", "rebate", "fee",
                 "credit", "transfer", "program cost", "administrative cost"]
    excerpts = []
    for sr in specialist_results:
        role = sr.get("specialist", sr.get("role", "specialist"))
        analysis = sr.get("analysis", "")
        if not analysis:
            continue
        # Split into sentences and keep only fiscal ones
        sentences = re.split(r'(?<=[.!?])\s+', analysis)
        fiscal_sentences = [s for s in sentences if any(kw in s.lower() for kw in fiscal_kw)]
        if fiscal_sentences:
            excerpts.append(f"[{role}] " + " ".join(fiscal_sentences[:8]))
    combined = "\n\n".join(excerpts)
    return combined[:max_chars] if combined else "No specialist fiscal analysis available."


async def run_fiscal_scorecard(
    client,
    asst_id: str,
    policy_text: str,
    specialist_results: list[dict],
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o",
) -> dict | None:
    """
    Run a single LLM call to extract and synthesize fiscal figures.
    Returns None if the policy has no fiscal content or the call fails.
    """
    specialist_excerpt = _extract_specialist_fiscal(specialist_results)

    # Quick pre-check: if no dollar figures anywhere, skip the LLM call entirely
    combined_text = policy_text + " " + specialist_excerpt
    has_any_dollar = any(kw in combined_text.lower() for kw in [
        "$", "billion", "million", " cost", "levy", "revenue", "grant", "fund", "budget"
    ])
    if not has_any_dollar:
        return {"has_fiscal_content": False}

    prompt = _FISCAL_PROMPT.format(
        policy_text=policy_text[:4000],
        specialist_excerpt=specialist_excerpt,
    )

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

        if not result.get("has_fiscal_content", True):
            return {"has_fiscal_content": False}

        # Recompute net position to override LLM arithmetic
        spend = result.get("total_committed_spend_cad") or 0
        revenue = result.get("total_revenue_cad") or 0
        net = revenue - spend
        result["net_fiscal_position_cad"] = round(net, 2)

        if spend == 0 and revenue == 0:
            result["net_position_label"] = "uncertain"
        elif abs(net) < 0.05 * max(abs(spend), abs(revenue), 1):
            result["net_position_label"] = "revenue-neutral"
        elif net > 0:
            result["net_position_label"] = "net revenue"
        else:
            result["net_position_label"] = "net cost"

        return result

    except Exception as e:
        return {"has_fiscal_content": False, "_error": str(e)}
