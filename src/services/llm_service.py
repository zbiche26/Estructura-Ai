"""
LLM Service - Wrapper unificado para múltiples proveedores de LLM

Soporta:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Modo de desarrollo (mock)
"""

from typing import List, Dict, Any, Optional, Literal
from abc import ABC, abstractmethod
import os
from datetime import datetime

from openai import OpenAI
from anthropic import Anthropic
import tiktoken

from src.core.logger import logger
from src.services.usage_tracker import APICallTracker

# ==================== TIPOS ====================

LLMProvider = Literal["openai", "anthropic", "mock"]


# ==================== BASE CLASSES ====================


class BaseLLMService(ABC):
    """Clase base para servicios LLM"""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Genera una respuesta del LLM

        Args:
            messages: Lista de mensajes en formato [{"role": "...", "content": "..."}]
            temperature: Temperatura de generación (0-1)
            max_tokens: Máximo de tokens a generar
            **kwargs: Parámetros adicionales específicos del proveedor

        Returns:
            Dict con:
                - content: str - Respuesta generada
                - tokens_used: int - Tokens utilizados
                - model: str - Modelo utilizado
                - finish_reason: str - Razón de finalización
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Cuenta tokens en un texto

        Args:
            text: Texto a contar

        Returns:
            Número de tokens
        """
        pass


# ==================== OPENAI SERVICE ====================


class OpenAIService(BaseLLMService):
    """Servicio para OpenAI (GPT-4, GPT-3.5)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[
            str
        ] = None,  # ✅ FIX: era str = "None" — ahora Optional[str] = None
        organization: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        # ✅ FIX: model=None activa el fallback a la variable de entorno
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.organization = organization

        if not self.api_key:
            raise ValueError("OpenAI API key no configurada")

        self.client = OpenAI(api_key=self.api_key, organization=self.organization)

        # Tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

        logger.info(f"OpenAI Service inicializado con modelo: {self.model}")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tenant_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Genera respuesta usando OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            choice = response.choices[0]

            result = {
                "content": choice.message.content,
                "tokens_used": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "model": response.model,
                "finish_reason": choice.finish_reason,
                "provider": "openai",
            }

            logger.debug(
                f"OpenAI response: {result['tokens_used']} tokens, "
                f"finish: {result['finish_reason']}"
            )

            # Track API call if tenant_id provided
            if tenant_id:
                try:
                    tracker = APICallTracker()
                    tracker.record_api_call(
                        tenant_id=tenant_id,
                        api_provider="openai",
                        endpoint="/v1/chat/completions",
                        tokens_used=response.usage.total_tokens,
                    )
                except Exception as track_err:
                    logger.warning(f"[USAGE] Error tracking API call: {track_err}")

            return result

        except Exception as e:
            logger.error(f"Error en OpenAI API: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """Cuenta tokens usando tiktoken"""
        return len(self.encoding.encode(text))

    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Cuenta tokens en una lista de mensajes

        Args:
            messages: Lista de mensajes

        Returns:
            Total de tokens
        """
        total = 0
        for message in messages:
            total += 4  # Tokens de formato
            total += self.count_tokens(message.get("role", ""))
            total += self.count_tokens(message.get("content", ""))
        total += 2  # Tokens finales
        return total


# ==================== ANTHROPIC SERVICE ====================


class AnthropicService(BaseLLMService):
    """Servicio para Anthropic (Claude)"""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "claude-3-sonnet-20240229"
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError("Anthropic API key no configurada")

        self.client = Anthropic(api_key=self.api_key)

        logger.info(f"Anthropic Service inicializado con modelo: {model}")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Genera respuesta usando Anthropic Claude"""
        try:
            system_message = None
            filtered_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    filtered_messages.append(msg)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=filtered_messages,
                **kwargs,
            )

            result = {
                "content": response.content[0].text,
                "tokens_used": response.usage.input_tokens
                + response.usage.output_tokens,
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "model": response.model,
                "finish_reason": response.stop_reason,
                "provider": "anthropic",
            }

            logger.debug(
                f"Anthropic response: {result['tokens_used']} tokens, "
                f"finish: {result['finish_reason']}"
            )

            return result

        except Exception as e:
            logger.error(f"Error en Anthropic API: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """Aproximación: ~4 caracteres = 1 token"""
        return len(text) // 4


# ==================== MOCK SERVICE ====================


class MockLLMService(BaseLLMService):
    """Servicio mock para desarrollo y testing"""

    def __init__(self, responses: Optional[List[str]] = None, **kwargs):
        self.responses = responses or [
            "¡Hola! ¿En qué puedo ayudarte?",
            "Entiendo. Déjame ayudarte con eso.",
            "¡Excelente! ¿Algo más en lo que pueda asistirte?",
        ]
        self.call_count = 0
        logger.info("Mock LLM Service inicializado")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Genera respuesta mock"""
        response_text = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1

        return {
            "content": response_text,
            "tokens_used": self.count_tokens(response_text) + 10,
            "prompt_tokens": 10,
            "completion_tokens": self.count_tokens(response_text),
            "model": "mock-model",
            "finish_reason": "stop",
            "provider": "mock",
        }

    def count_tokens(self, text: str) -> int:
        """Mock token counting"""
        return len(text.split())


# ==================== FACTORY ====================


class LLMServiceFactory:
    """Factory para crear servicios LLM"""

    @staticmethod
    def create(provider: LLMProvider = "openai", **kwargs) -> BaseLLMService:
        """
        Crea un servicio LLM

        Args:
            provider: Proveedor ("openai", "anthropic", "mock")
            **kwargs: Parámetros específicos del proveedor

        Returns:
            Instancia del servicio LLM
        """
        if provider == "openai":
            return OpenAIService(**kwargs)
        elif provider == "anthropic":
            return AnthropicService(**kwargs)
        elif provider == "mock":
            return MockLLMService(**kwargs)
        else:
            raise ValueError(f"Proveedor LLM desconocido: {provider}")


# ==================== UNIFIED LLM SERVICE ====================


class LLMService:
    """
    Servicio unificado de LLM con fallback automático.
    Intenta usar el proveedor principal, si falla usa el fallback.
    """

    def __init__(
        self,
        primary_provider: LLMProvider = "openai",
        fallback_provider: Optional[LLMProvider] = "mock",
        **kwargs,
    ):
        self.primary = LLMServiceFactory.create(primary_provider, **kwargs)
        self.fallback = (
            LLMServiceFactory.create(fallback_provider, **kwargs)
            if fallback_provider
            else None
        )

        logger.info(
            f"LLM Service inicializado: primary={primary_provider}, "
            f"fallback={fallback_provider}"
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        use_fallback_on_error: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Genera respuesta con fallback automático.
        """
        try:
            return await self.primary.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Error en primary LLM: {e}")

            if use_fallback_on_error and self.fallback:
                logger.warning("Usando fallback LLM")
                return await self.fallback.generate(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            else:
                raise

    def count_tokens(self, text: str) -> int:
        """Cuenta tokens usando el servicio principal"""
        return self.primary.count_tokens(text)
