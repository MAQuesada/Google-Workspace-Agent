from typing import Any, Union
from langchain_core.prompts import PromptTemplate
import yaml


class PromptError(Exception):
    pass


class YamlLoadError(PromptError):
    pass


class PromptBuilder:
    """Builds prompts based on a YAML config file."""

    def __init__(self, config_path: str):
        """Initialize PromptBuilder with a YAML config file.

        Args:
            config_path: Path to the YAML config file containing app-wide settings.
        """
        try:
            self.app_config = self.load_yaml(config_path)
        except YamlLoadError as e:
            print(f"Error loading YAML config: {e}")
            self.app_config = {}

    @staticmethod
    def _uppercase_first_char(text: str) -> str:
        """Uppercases the first character of a string.

        Args:
            text: Input string.

        Returns:
            The input string with the first character uppercased.
        """
        return text[0].upper() + text[1:] if text else text

    @staticmethod
    def _lowercase_first_char(text: str) -> str:
        """Lowercases the first character of a string.

        Args:
            text: Input string.

        Returns:
            The input string with the first character lowercased.
        """
        return text[0].lower() + text[1:] if text else text

    @staticmethod
    def load_yaml(file_path: str) -> dict[str, Any]:
        """Load a YAML file.

        Args:
            file_path: Path to the YAML file.

        Returns:
            A dictionary containing the file contents.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError as e:
            raise YamlLoadError("File not found.") from e
        except yaml.YAMLError as e:
            raise YamlLoadError("Error parsing YAML file.") from e
        except OSError as e:
            raise YamlLoadError("Error reading YAML file.") from e

    def _format_prompt_section(
        self, lead_in: str, value: Union[str, list[str | list]], space: str = ""
    ) -> str:
        """Format a prompt section.

        Args:
            lead_in: Section intro or empty string.
            value: Content as string or list.
            space: Indentation for nested sections.

        Returns:
            Formatted string with lead-in and content.
        """
        if isinstance(value, str):
            formatted_value = value
            if lead_in:
                return (
                    f"{space}{self._uppercase_first_char(lead_in)}\n{space}"
                    f"- {self._uppercase_first_char(formatted_value)}"
                )
            return f"{space}- {self._uppercase_first_char(formatted_value)}"
        else:
            output = ""
            if lead_in:
                output += f"{space}{self._uppercase_first_char(lead_in)}\n"

            for item in value:
                if isinstance(item, str):
                    output += f"{space}- {self._uppercase_first_char(item)}\n"
                else:
                    output += self._format_prompt_section(
                        lead_in="", value=item, space=space + "  "
                    )
            return output

    def _build_prompt(
        self, prompt_data: dict[str, Any], input_data: str = ""
    ) -> tuple[str, list[str]]:
        """Builds a complete prompt string based on a config dictionary.

        Args:
            prompt_data: Dictionary specifying prompt components.
            input_data: Content to be summarized or processed.

        Returns:
            A fully constructed prompt as a string and a list of input variables.

        Raises:
            PromptError: If the required 'instruction' field is missing.
        """
        prompt_parts = []

        if role := prompt_data.get("role"):
            prompt_parts.append(self._format_prompt_section("## ROLE:", role.strip()))

        if goal := prompt_data.get("goal"):
            prompt_parts.append(
                self._format_prompt_section(
                    "## Your goal is to achieve the following outcome:", goal
                )
            )

        instruction = prompt_data.get("instruction")
        if not instruction:
            raise PromptError("Missing required field: 'instruction'")
        prompt_parts.append(
            self._format_prompt_section("## Your task is as follows:", instruction)
        )

        if context := prompt_data.get("context"):
            prompt_parts.append(
                self._format_prompt_section(
                    "## Here's some background that may help you:", context
                )
            )

        if constraints := prompt_data.get("output_constraints"):
            prompt_parts.append(
                self._format_prompt_section(
                    "## Ensure your response follows these rules:", constraints
                )
            )

        if tone := prompt_data.get("style_or_tone"):
            prompt_parts.append(
                self._format_prompt_section(
                    "## Follow these style and tone guidelines:", tone
                )
            )

        if format_ := prompt_data.get("output_format"):
            prompt_parts.append(
                self._format_prompt_section(
                    "## Structure your response as follows:", format_
                )
            )

        if examples := prompt_data.get("examples"):
            prompt_parts.append("Here are some examples to guide your response:")
            if isinstance(examples, list):
                for i, example in enumerate(examples, 1):
                    prompt_parts.append(f"Example {i}:\n{example}")
            else:
                prompt_parts.append(str(examples))

        if input_data:
            prompt_parts.append(
                "Here is the content you need to work with:\n"
                "<<<BEGIN CONTENT>>>\n"
                "```\n" + input_data.strip() + "\n```\n<<<END CONTENT>>>"
            )

        reasoning_strategy = prompt_data.get("reasoning_strategy")
        if reasoning_strategy is not None and self.app_config:
            strategies = self.app_config.get("reasoning_strategies", {})
            if strategy_text := strategies.get(reasoning_strategy):
                prompt_parts.append(strategy_text.strip())

        prompt_parts.append("Now perform the task as instructed above.")

        input_variables = prompt_data.get("input_variables", [])
        if input_variables is None:
            input_variables = []
        if not isinstance(input_variables, list):
            raise PromptError("Input variables must be a list")

        return "\n\n".join(prompt_parts), input_variables

    def build_prompt(
        self, file_path: str, input_data: str = ""
    ) -> tuple[str, list[str]]:
        """Builds a complete prompt string based on a config file.

        Args:
            file_path: Path to the YAML config file containing prompt components.
            input_data: Content to be input to the prompt.

        Returns:
            A fully constructed prompt as a string and a list of input variables.

        Raises:
            PromptError: If an error occurs while building the prompt.
        """

        prompt_data = self.load_yaml(file_path)
        return self._build_prompt(prompt_data, input_data)

    def build_prompt_template(
        self, file_path: str, input_data: str = ""
    ) -> PromptTemplate:
        """Builds a prompt template based on a config file.

        Args:
            file_path: Path to the YAML config file containing prompt components.
            input_data: Content to be input to the prompt.

        Returns:
            A prompt template based on the config file.

        Raises:
            PromptError: If an error occurs while building the prompt template.
        """
        prompt, input_variables = self.build_prompt(file_path, input_data)
        try:
            prompt_template = PromptTemplate.from_template(prompt)
        except ValueError as e:
            raise PromptError("Error building prompt template.") from e
        if set(prompt_template.input_variables) != set(input_variables):
            print(prompt_template.input_variables)
            print(input_variables)
            raise PromptError(
                "Input variables in the template do not match the expected input variables"
            )
        return prompt_template
