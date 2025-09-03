from guardrails import OnFailAction
from guardrails.classes import FailResult
from pydantic import BaseModel

from agents.utils import get_logger

logger = get_logger("api.validations")


class SaveInput(BaseModel):
    """The output of the guardrails for the user input."""

    safe: bool
    error_message: str = ""


def validate_user_input(user_input: str) -> SaveInput:
    """Validate the user input using the guardrails library.

    The validation methods are:
    - unusual_prompt
    - llama_guard_7b:
        - POLICY__NO_CRIMINAL_PLANNING,
        - POLICY__NO_ENOURAGE_SELF_HARM,
        - POLICY__NO_GUNS_AND_ILLEGAL_WEAPONS,
        - POLICY__NO_ILLEGAL_DRUGS,
        - POLICY__NO_SEXUAL_CONTENT,
        - POLICY__NO_VIOLENCE_HATE,

    """
    logger.info("Validating user input.")
    try:
        from guardrails.hub import UnusualPrompt

        validator1 = UnusualPrompt(
            llm_callable="gpt-4o-mini", on_fail=OnFailAction.REFRAIN
        )
        output = validator1.validate(
            user_input,
            metadata={"pass_if_invalid": False},
        )

        if isinstance(output, FailResult):
            logger.warning(
                "Validation failed.",
                extra={
                    "validation_method": "unusual_prompt",
                    "error": output.error_message,
                },
            )
            return SaveInput(safe=False, error_message=output.error_message)
    except Exception as e:
        logger.warning(
            "Ignoring validating user input.",
            extra={"validation_method": "unusual_prompt", "error": str(e)},
        )

    try:
        from guardrails.hub import LlamaGuard7B

        validator2 = LlamaGuard7B(
            policies=[
                LlamaGuard7B.POLICY__NO_CRIMINAL_PLANNING,
                LlamaGuard7B.POLICY__NO_ENOURAGE_SELF_HARM,
                LlamaGuard7B.POLICY__NO_GUNS_AND_ILLEGAL_WEAPONS,
                LlamaGuard7B.POLICY__NO_ILLEGAL_DRUGS,
                LlamaGuard7B.POLICY__NO_SEXUAL_CONTENT,
                LlamaGuard7B.POLICY__NO_VIOLENCE_HATE,
            ],
            on_fail=OnFailAction.REFRAIN,
        )
        output = validator2.validate(user_input, metadata={"pass_if_invalid": False})
        if isinstance(output, FailResult):
            logger.warning(
                "Validation failed.",
                extra={
                    "validation_method": "llama_guard_7b",
                    "error": output.error_message,
                },
            )
            return SaveInput(safe=False, error_message=output.error_message)
    except Exception as e:
        logger.warning(
            "Ignoring validating user input.",
            extra={"validation_method": "llama_guard_7b", "error": str(e)},
        )
    logger.info("User input validated successfully.")
    return SaveInput(safe=True, error_message="")
