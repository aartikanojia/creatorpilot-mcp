"""
LangChain Azure OpenAI client for LLM invocations.

Uses AzureChatOpenAI from langchain-openai to interact with
Azure-hosted OpenAI models (e.g., gpt-4o-mini).
"""

import logging
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from config import config

logger = logging.getLogger(__name__)


class LangChainAzureClient:
    """
    Client for interacting with Azure OpenAI models via LangChain.
    """

    def __init__(self) -> None:
        """
        Initialize the LangChain Azure OpenAI client.
        Raises ValueError if required Azure configuration is missing.
        """
        if not config.llm.azure_openai_api_key:
            logger.error("AZURE_OPENAI_API_KEY not found in configuration")
            raise ValueError("AZURE_OPENAI_API_KEY is required")

        if not config.llm.azure_openai_endpoint:
            logger.error("AZURE_OPENAI_ENDPOINT not found in configuration")
            raise ValueError("AZURE_OPENAI_ENDPOINT is required")

        if not config.llm.azure_openai_deployment_name:
            logger.error("AZURE_OPENAI_DEPLOYMENT not found in configuration")
            raise ValueError("AZURE_OPENAI_DEPLOYMENT is required")

        self.deployment_name = config.llm.azure_openai_deployment_name

        # Initialize the LangChain Azure OpenAI chat model
        self.llm = AzureChatOpenAI(
            azure_endpoint=config.llm.azure_openai_endpoint,
            api_key=config.llm.azure_openai_api_key,
            api_version=config.llm.azure_openai_api_version,
            deployment_name=self.deployment_name,
            temperature=0.3,
            max_tokens=4096,
        )

        logger.info(
            f"Azure OpenAI client initialized with deployment: {self.deployment_name}"
        )

    def generate(self, prompt: str) -> str:
        """
        Generate a response using LangChain Azure OpenAI.

        Falls back to Gemini automatically if Azure's content filter
        blocks the response.

        Args:
            prompt: Input text prompt

        Returns:
            Generated text response
        """
        try:
            messages = [HumanMessage(content=prompt)]
            response = self.llm.invoke(messages)

            logger.debug(f"Azure LLM response type: {type(response)}")

            content = response.content

            # Handle different response formats from LangChain
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                    elif isinstance(part, str):
                        text_parts.append(part)
                result = "".join(text_parts)
                if not result:
                    logger.warning(
                        f"Azure LLM returned empty content from list: {content}"
                    )
                return result

            if not content:
                logger.warning("Azure LLM returned empty string content")
            return str(content) if content else ""

        except Exception as e:
            error_msg = str(e).lower()
            # Detect Azure content filter and fallback to Gemini
            if "content filter" in error_msg or "content_filter" in error_msg:
                logger.warning(
                    f"Azure content filter triggered, attempting Gemini fallback: {e}"
                )
                return self._gemini_fallback(prompt)

            logger.error(f"LangChain Azure OpenAI generation failed: {e}")
            return f"Error generating response: {str(e)}"

    def _gemini_fallback(self, prompt: str) -> str:
        """Retry the prompt using Gemini when Azure content filter blocks."""
        try:
            from llm.langchain_gemini import LangChainGeminiClient

            if not config.llm.gemini_api_key:
                logger.error("Gemini fallback unavailable: GEMINI_API_KEY not set")
                return (
                    "I couldn't analyze this content due to a safety filter. "
                    "Please try rephrasing your question."
                )

            gemini = LangChainGeminiClient()
            result = gemini.generate(prompt)
            logger.info("Gemini fallback succeeded after Azure content filter block")
            return result

        except Exception as fallback_err:
            logger.error(f"Gemini fallback also failed: {fallback_err}")
            return (
                "I couldn't analyze this content due to a safety filter. "
                "Please try rephrasing your question."
            )
