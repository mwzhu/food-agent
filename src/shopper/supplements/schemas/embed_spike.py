from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SupplementCheckoutEmbedSpikeRequest(BaseModel):
    store_domain: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplementCheckoutEmbedSpikeRead(BaseModel):
    store_domain: str
    query: str
    selected_product_title: Optional[str] = None
    selected_variant_id: Optional[str] = None
    checkout_url: Optional[str] = None
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    iframe_allowed: bool = False
    block_reason: Optional[str] = None
    x_frame_options: Optional[str] = None
    content_security_policy: Optional[str] = None
    frame_ancestors: list[str] = Field(default_factory=list)
    allowed_embed_origins: list[str] = Field(default_factory=list)
    error: Optional[str] = None

    model_config = ConfigDict(str_strip_whitespace=True)
