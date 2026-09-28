"""Interactive CLI. Usage: python -m app.main [--no-llm]"""

import sys
import uuid

from app.graph.graph import SupportAgent
from app.graph.nodes.handoff import render_summary
from app.logging_setup import configure_logging


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page
    configure_logging()
    agent = SupportAgent(use_llm=False if "--no-llm" in sys.argv else None)
    thread = uuid.uuid4().hex
    mode = "LLM + rules" if agent.deps.llm else "rules only"
    print(f"Customer support agent (customer {agent.customer_id}, triage: {mode}). Type 'quit' to exit.\n")
    seen_actions = 0
    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in ("quit", "exit"):
            break
        if not message:
            continue
        state = agent.chat(message, thread)
        actions = state.get("actions_taken", [])
        new_actions = actions[seen_actions:]
        for action in new_actions:
            print(f"  ✓ {action}")
        seen_actions = len(actions)
        print(f"\nAgent: {state['final_response']}\n")
        if "Escalated to human support" in new_actions and state.get("handoff_summary"):
            print("---- Handoff (visible to support team) ----")
            print(render_summary(state["handoff_summary"]))
            print("-------------------------------------------\n")


if __name__ == "__main__":
    main()
