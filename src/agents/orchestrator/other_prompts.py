from prompts.core import get_prompt_builder


prompt_builder = get_prompt_builder("src/prompts/config.yaml")

ENTRY_PROMPT_ORCHESTRATOR = prompt_builder.build_prompt(
    "src/prompts/orchestrator_input.yml"
)[0]

RESPONSE_PROMPT_ORCHESTRATOR = prompt_builder.build_prompt(
    "src/prompts/orchestrator_response.yml"
)[0]

VERIFICATION_PROMPT = prompt_builder.build_prompt(
    "src/prompts/orchestrator_verifier.yml"
)[0]


ENTRY_POINT_TEMPLATE = """
### The user's request is:
{user_request}"""

FINAL_ANSWER_TEMPLATE = """
### The user's request is:
{user_request}

---

### The "MANAGER OUTPUTS":
{manager_response}
"""

MANAGER_TEMPLATE = """
### The user's request is:
{user_request}

---

### Task Context:
{manager_response_context}
"""
