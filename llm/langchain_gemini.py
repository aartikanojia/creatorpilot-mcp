
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from typing import Optional
from config import config

logger = logging.getLogger(__name__)

class LangChainGeminiClient:
    """
    Client for interacting with Google's Gemini models via LangChain.
    """

    def __init__(self) -> None:
        """
        Initialize the LangChain Gemini client.
        Raises ValueError if API key is missing.
        """
        self.api_key = config.llm.gemini_api_key
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in configuration")
            raise ValueError("GEMINI_API_KEY is required")

        self.model_name = config.llm.gemini_model
        
        # Initialize the LangChain chat model
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.api_key,
            temperature=0.3,
            max_output_tokens=2048,  # Increased for longer responses
            convert_system_message_to_human=True  # Gemini sometimes needs this
        )
        
        logger.info(f"Initialized LangChain Gemini client with model: {self.model_name}")

    def generate(self, prompt: str) -> str:
        """
        Generate a response using LangChain.

        Args:
            prompt: Input text prompt

        Returns:
            Generated text response
        """
        try:
            messages = [HumanMessage(content=prompt)]
            response = self.llm.invoke(messages)
            
            # Debug logging to trace the response
            logger.debug(f"LLM response type: {type(response)}")
            logger.debug(f"LLM response content type: {type(response.content)}")
            logger.debug(f"LLM response content: {response.content[:500] if response.content else 'EMPTY'}")
            
            # Handle different response formats from LangChain
            content = response.content
            
            # If content is a list (new format), extract text from parts
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and 'text' in part:
                        text_parts.append(part['text'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                result = ''.join(text_parts)
                if not result:
                    logger.warning(f"LLM returned empty content from list format: {content}")
                return result
            
            # If content is already a string, return it directly
            if not content:
                logger.warning("LLM returned empty string content")
            return str(content) if content else ""
        except Exception as e:
            logger.error(f"LangChain Gemini generation failed: {e}")
            return f"Error generating response: {str(e)}"
