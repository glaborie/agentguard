#!/usr/bin/bash
# 1. Point to OpenRouter
export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
export ANTHROPIC_AUTH_TOKEN=$OPENROUTER_API_KEY

# 2. Crucial: Clear any local Anthropic keys to prevent conflicts
export ANTHROPIC_API_KEY=""

# 3. Map all internal tiers to MiniMax
# This prevents Claude from trying to find 'claude-3-5-sonnet' on OpenRouter
export ANTHROPIC_DEFAULT_SONNET_MODEL="minimax/minimax-m3"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="minimax/minimax-m2.5"
export ANTHROPIC_DEFAULT_OPUS_MODEL="minimax/minimax-m3"

# 4. Disable experimental betas (OpenRouter does not support these)
export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=true
claude --model minimax/minimax-m3
