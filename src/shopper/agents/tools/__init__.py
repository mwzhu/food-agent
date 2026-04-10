from __future__ import annotations

from importlib import import_module

__all__ = [
    "BrowserCheckoutAgent",
    "ChatGPTInstacartCheckoutBackend",
    "BrowserUseCheckoutBackend",
    "CheckoutAutomationRouter",
    "CartVerifier",
    "RecipeSearchTool",
    "browser_use_runtime_status",
    "build_get_fridge_contents_tool",
    "nutrition_lookup",
]

_LAZY_IMPORTS = {
    "BrowserCheckoutAgent": ("shopper.agents.tools.browser_tools", "BrowserCheckoutAgent"),
    "ChatGPTInstacartCheckoutBackend": ("shopper.agents.tools.browser_tools", "ChatGPTInstacartCheckoutBackend"),
    "BrowserUseCheckoutBackend": ("shopper.agents.tools.browser_tools", "BrowserUseCheckoutBackend"),
    "CheckoutAutomationRouter": ("shopper.agents.tools.browser_tools", "CheckoutAutomationRouter"),
    "CartVerifier": ("shopper.agents.tools.cart_verifier", "CartVerifier"),
    "RecipeSearchTool": ("shopper.agents.tools.recipe_search", "RecipeSearchTool"),
    "browser_use_runtime_status": ("shopper.agents.tools.browser_tools", "browser_use_runtime_status"),
    "build_get_fridge_contents_tool": ("shopper.agents.tools.inventory_tools", "build_get_fridge_contents_tool"),
    "nutrition_lookup": ("shopper.agents.tools.nutrition_lookup", "nutrition_lookup"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

    module_path, attr_name = _LAZY_IMPORTS[name]
    module = import_module(module_path)
    attr = getattr(module, attr_name)
    globals()[name] = attr
    return attr
