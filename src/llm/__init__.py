"""LLM integration.

Public modules:
    base               — Event dataclasses + LLMProvider abstract base.
    anthropic_provider — Claude via the official `anthropic` SDK.
    ollama_provider    — Local Ollama via /api/chat.
    factory            — Pick a provider from settings.
    credentials        — Load/save API keys (keyring → env-var fallback).
    conversation       — Message history container + (de)serialization.
"""
